#!/usr/bin/env python3
"""MOSSlanding inference subprocess.

A long-running Python process driven over stdin/stdout with newline-delimited
JSON. The Swift host (Hummingbird) owns the HTTP surface; this process owns
only model loading and synthesis. Once the MOSS-TTS model is replaced with a
CoreML / MLX / candle pipeline, this file can be deleted.

Protocol
--------
Stdout — status and result messages, one JSON object per line:

  {"status": "starting"}
  {"status": "loading", "progress": 30, "message": "Loading tokenizer..."}
  {"status": "ready",   "model_id": "...", "device": "mps", "models_dir": "..."}
  {"status": "generating", "message": "Generating audio..."}
  {"status": "idle"}
  {"status": "error", "error": "..."}
  {"wav_path": "/Users/.../mosslanding_xxxx.wav",
   "filename": "mosslanding_xxxx.wav",
   "sample_rate": 22050,
   "duration": 3.2}
  {"error": "synthesis failed: ..."}

Stdin — one request object per line:

  {"op": "synthesize", "text": "...", "voice": "alice.wav", "mode": "clone",
   "quality": 32, "temperature": 1.7, ...}
  {"op": "load"}
  {"op": "unload"}
  {"op": "shutdown"}

Synthesize results are emitted in request order (FIFO). The host correlates
the next non-status response with the next outstanding request.
"""

from __future__ import annotations

# ── HuggingFace cache redirect (must precede any hf/transformers import) ───
import os
import sys
from pathlib import Path

_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "MOSSlanding"
_MODELS_DIR  = _APP_SUPPORT / "models"
_MODELS_HUB  = _MODELS_DIR / "hub"
_VOICES_DIR  = _APP_SUPPORT / "voices"
_OUTPUT_DIR  = Path.home() / "Desktop" / "MOSSlanding"
for _d in (_MODELS_DIR, _MODELS_HUB, _VOICES_DIR, _OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("HF_HOME",                str(_MODELS_DIR))
os.environ.setdefault("HF_HUB_CACHE",           str(_MODELS_HUB))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE",  str(_MODELS_HUB))
os.environ.setdefault("TRANSFORMERS_CACHE",     str(_MODELS_HUB))

_DEFAULT_MODEL_ID   = "OpenMOSS-Team/MOSS-TTS-Local-Transformer"
_DEFAULT_MODEL_SLUG = "models--" + _DEFAULT_MODEL_ID.replace("/", "--")
if (_MODELS_HUB / _DEFAULT_MODEL_SLUG).exists():
    os.environ.setdefault("HF_HUB_OFFLINE",       "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Bundled MOSS-TTS source repo, if present
_MOSS_TTS_REPO = Path(os.environ.get("MOSS_TTS_REPO", Path.home() / "MOSS-TTS"))
if _MOSS_TTS_REPO.exists() and str(_MOSS_TTS_REPO) not in sys.path:
    sys.path.insert(0, str(_MOSS_TTS_REPO))

# ── stdlib imports ─────────────────────────────────────────────────────────
import gc
import importlib.util
import json
import threading
import traceback
import uuid
from typing import Any, Optional

# ── heavy imports (after env is set) ──────────────────────────────────────
import numpy as np
import soundfile as sf
import torch


MODEL_ID = os.environ.get("MOSS_TTS_MODEL_ID", _DEFAULT_MODEL_ID)


# ── stdout helper (line-buffered JSON) ─────────────────────────────────────
_emit_lock = threading.Lock()


def emit(obj: dict) -> None:
    """Write one JSON line to stdout, flushed."""
    line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    with _emit_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def log(msg: str) -> None:
    """Write a diagnostic line to stderr (consumed by the Swift host's logger)."""
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# ── device selection ───────────────────────────────────────────────────────
def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def get_dtype(device: torch.device) -> torch.dtype:
    if device.type == "mps":
        return torch.float16
    if device.type == "cuda":
        return torch.bfloat16
    return torch.float32


# ── model state ────────────────────────────────────────────────────────────
class ModelState:
    def __init__(self) -> None:
        self.model = None
        self.processor = None
        self.device: Optional[torch.device] = None
        self.dtype: Optional[torch.dtype] = None
        self.status: str = "idle"
        self.progress: int = 0
        self.message: str = ""
        self.error: str = ""
        self.lock = threading.Lock()

    def is_loaded(self) -> bool:
        return self.model is not None and self.processor is not None

    def emit_status(self) -> None:
        payload: dict[str, Any] = {
            "status":     self.status,
            "progress":   self.progress,
            "message":    self.message,
            "model_id":   MODEL_ID,
            "device":     str(self.device) if self.device else "unknown",
            "models_dir": str(_MODELS_DIR),
        }
        if self.error:
            payload["error"] = self.error
        emit(payload)


_state = ModelState()


def _set_status(status: str, progress: int = 0, message: str = "", error: str = "") -> None:
    with _state.lock:
        _state.status = status
        _state.progress = progress
        _state.message = message
        _state.error = error
    _state.emit_status()


def _load_model() -> None:
    """Background load. Emits progressive status messages."""
    from transformers import AutoModel, AutoProcessor

    try:
        device = get_device()
        dtype = get_dtype(device)
        _state.device = device
        _state.dtype = dtype

        _set_status("loading", 5, f"Loading tokenizer from {MODEL_ID}...")

        # Disable CUDA-specific backends when not on CUDA
        if device.type != "cuda":
            torch.backends.cuda.enable_cudnn_sdp(False)

        processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
        _set_status("loading", 30, "Tokenizer ready. Loading audio tokenizer...")

        processor.audio_tokenizer = processor.audio_tokenizer.to(device)
        _set_status("loading", 40, "Audio tokenizer loaded. Loading LM weights...")

        attn_impl = "eager"
        if device.type == "cuda" and importlib.util.find_spec("flash_attn"):
            if dtype in (torch.float16, torch.bfloat16):
                major, _minor = torch.cuda.get_device_capability()
                if major >= 8:
                    attn_impl = "flash_attention_2"

        model = AutoModel.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
            attn_implementation=attn_impl,
            torch_dtype=dtype,
        ).to(device)
        model.eval()

        _set_status("loading", 90, "Warming up...")

        # JIT warm-up; non-fatal if it fails
        try:
            with torch.no_grad():
                warm = [processor.build_user_message(text="Hello.")]
                batch = processor([warm], mode="generation")
                model.generate(
                    batch["input_ids"].to(device),
                    attention_mask=batch["attention_mask"].to(device),
                    max_new_tokens=64,
                )
        except Exception as exc:
            log(f"warm-up failed (non-fatal): {exc}")

        with _state.lock:
            _state.model = model
            _state.processor = processor

        _set_status("ready", 100, "Ready")
        log(f"Model loaded on {device} ({dtype})")

    except Exception as exc:
        log("Model loading failed:\n" + traceback.format_exc())
        with _state.lock:
            _state.model = None
            _state.processor = None
        _set_status("error", 0, "Model load failed", error=str(exc))


def ensure_loaded() -> None:
    with _state.lock:
        if _state.status in ("idle", "error"):
            _state.status = "loading"
            _state.progress = 0
            _state.message = "Starting..."
            _state.error = ""
            t = threading.Thread(target=_load_model, daemon=True)
            t.start()


def unload() -> None:
    with _state.lock:
        _state.model = None
        _state.processor = None
        _state.status = "idle"
        _state.progress = 0
        _state.message = ""
        _state.error = ""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    _state.emit_status()


# ── synthesis ───────────────────────────────────────────────────────────────
def _synthesize(req: dict) -> dict:
    """Run synthesis for a request. Returns the response dict to emit."""
    if _state.status == "idle":
        ensure_loaded()
        return {"error": "Model loading started. Retry shortly."}
    if _state.status == "loading":
        return {"error": f"Model loading ({_state.progress}%). Please wait."}
    if _state.status == "error":
        return {"error": f"Model error: {_state.error}"}
    if not _state.is_loaded():
        return {"error": "Model not ready"}

    processor = _state.processor
    model = _state.model
    device = _state.device

    text = req.get("text", "")
    if not text:
        return {"error": "text is required"}

    voice = req.get("voice")
    mode  = req.get("mode", "clone")
    language = req.get("language")
    duration_tokens = req.get("duration_tokens")

    reference_paths: list[str] = []
    if voice and mode != "direct":
        vp = _VOICES_DIR / voice
        if vp.exists():
            reference_paths = [str(vp)]

    msg_kwargs: dict[str, Any] = {}
    if language and str(language).lower() not in ("auto", ""):
        msg_kwargs["language"] = language
    if reference_paths:
        msg_kwargs["reference"] = reference_paths
    if duration_tokens:
        msg_kwargs["tokens"] = int(duration_tokens)

    quality = max(4, min(32, int(req.get("quality", 32))))

    conversation = [processor.build_user_message(text=text, **msg_kwargs)]
    batch = processor([conversation], mode="generation")
    input_ids = batch["input_ids"].to(device)
    attention_mask = batch["attention_mask"].to(device)

    gen_kwargs = dict(
        input_ids=input_ids,
        attention_mask=attention_mask,
        max_new_tokens=int(req.get("max_new_tokens", 4096)),
        do_sample=bool(req.get("do_sample", True)),
        temperature=float(req.get("temperature", 1.7)),
        top_p=float(req.get("top_p", 0.8)),
        top_k=int(req.get("top_k", 25)),
        repetition_penalty=float(req.get("repetition_penalty", 1.0)),
        n_vq_for_inference=quality,
    )

    _set_status("generating", 0, "Generating audio...")
    try:
        with torch.no_grad():
            outputs = model.generate(**gen_kwargs)
    finally:
        _set_status("ready", 100, "Ready")

    messages = processor.decode(outputs)
    if not messages:
        return {"error": "No output from model"}
    msg = messages[0]
    if not msg.audio_codes_list:
        return {"error": "No audio codes in output"}

    audio = msg.audio_codes_list[0].cpu().float().numpy()
    sr    = int(processor.model_config.sampling_rate)

    out_name = f"mosslanding_{uuid.uuid4().hex[:8]}.wav"
    out_path = _OUTPUT_DIR / out_name
    sf.write(str(out_path), audio, sr, format="WAV", subtype="PCM_16")
    duration = float(len(audio)) / sr

    return {
        "wav_path":    str(out_path),
        "filename":    out_name,
        "sample_rate": sr,
        "duration":    duration,
    }


# ── main loop ──────────────────────────────────────────────────────────────
def main() -> None:
    emit({"status": "starting"})
    ensure_loaded()

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            emit({"error": f"invalid JSON: {exc}"})
            continue

        op = req.get("op", "synthesize")

        if op == "shutdown":
            log("Shutdown requested")
            return
        if op == "load":
            ensure_loaded()
            continue
        if op == "unload":
            unload()
            continue
        if op == "status":
            _state.emit_status()
            continue
        if op == "synthesize":
            try:
                emit(_synthesize(req))
            except Exception as exc:
                log("Synthesis failed:\n" + traceback.format_exc())
                emit({"error": str(exc)})
                _set_status("ready", 100, "Ready")
            continue

        emit({"error": f"unknown op: {op}"})


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        log("Fatal:\n" + traceback.format_exc())
        emit({"status": "error", "error": str(exc)})
        sys.exit(1)
