#!/usr/bin/env python3
"""MOSSlanding HTTP API server - optimized for Apple Silicon (MPS)."""

# ── HuggingFace cache redirect — must happen before ANY hf/transformers import
import os, sys
from pathlib import Path
_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "MOSSlanding"
_MODELS_HUB  = _APP_SUPPORT / "models" / "hub"
_MODELS_HUB.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME",               str(_APP_SUPPORT / "models"))
os.environ.setdefault("HF_HUB_CACHE",          str(_MODELS_HUB))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(_MODELS_HUB))
os.environ.setdefault("TRANSFORMERS_CACHE",     str(_MODELS_HUB))

# If the default model is already cached, prefer local-only loads to avoid
# broken-pipe errors after sleep/wake. Downloads will temporarily bypass this.
_DEFAULT_MODEL_SLUG = "models--OpenMOSS-Team--MOSS-TTS-Local-Transformer"
_DEFAULT_MODEL_CACHED = (_MODELS_HUB / _DEFAULT_MODEL_SLUG).exists()

import asyncio
import gc
import importlib.util
import io
import json
import logging
import subprocess
import threading
import time
import uuid
from typing import Optional

import numpy as np
import soundfile as sf
import torch
import torchaudio
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mosslanding")

# ── paths ──────────────────────────────────────────────────────────────────
APP_SUPPORT = Path.home() / "Library" / "Application Support" / "MOSSlanding"
VOICES_DIR  = APP_SUPPORT / "voices"
MODELS_DIR  = APP_SUPPORT / "models"   # all HF model weights live here
OUTPUT_DIR  = Path.home() / "Desktop"  / "MOSSlanding"
for d in (VOICES_DIR, MODELS_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── available models catalogue (forward-thinking: add more here later) ──────
AVAILABLE_MODELS = {
    "moss-local-1.7b": {
        "id":          "OpenMOSS-Team/MOSS-TTS-Local-Transformer",
        "description": "MOSS TTS Local Transformer 1.7B — fast, M1-optimised",
        "size_gb":     3.5,
        "recommended": True,
    },
    "moss-v1.5-8b": {
        "id":          "OpenMOSS-Team/MOSS-TTS-v1.5",
        "description": "MOSS TTS v1.5 8B — highest quality, needs 16 GB+ RAM",
        "size_gb":     16.0,
        "recommended": False,
    },
}

# Allow the bundled MOSS-TTS repo to be found
MOSS_TTS_REPO = Path(os.environ.get("MOSS_TTS_REPO", Path.home() / "MOSS-TTS"))
if MOSS_TTS_REPO.exists() and str(MOSS_TTS_REPO) not in sys.path:
    sys.path.insert(0, str(MOSS_TTS_REPO))

# ── active model ─────────────────────────────────────────────────────────────
_DEFAULT_MODEL_KEY = "moss-local-1.7b"
_active_model_key = _DEFAULT_MODEL_KEY
_active_model_id = AVAILABLE_MODELS[_active_model_key]["id"]
INACTIVITY_TIMEOUT = int(os.environ.get("MOSS_TTS_INACTIVITY_TIMEOUT", "0"))  # seconds; 0 = never auto-unload

def get_active_model_id() -> str:
    return _active_model_id

def get_active_model_key() -> str:
    return _active_model_key


def is_model_cached(model_id: str) -> bool:
    """Check if model is fully cached (has valid snapshot with files)."""
    slug = "models--" + model_id.replace("/", "--")
    snapshots_dir = MODELS_DIR / "hub" / slug / "snapshots"
    if not snapshots_dir.exists():
        return False
    for snap in snapshots_dir.iterdir():
        if snap.is_dir() and any(snap.iterdir()):
            return True
    return False

# ── device setup ────────────────────────────────────────────────────────────
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


def detect_chip() -> str:
    """Detect Apple Silicon chip family from the Mac model identifier."""
    try:
        model = subprocess.run(["sysctl", "-n", "hw.model"],
                               capture_output=True, text=True).stdout.strip()
    except Exception:
        return "Apple Silicon"

    # Map Mac model identifiers to chip families
    chip_map = {
        "Mac17": "M5",
        "Mac16": "M4",
        "Mac15": "M3",
        "Mac14": "M2",
        "Mac13": "M2",
        "Mac12": "M1",
        "Mac11": "M1",
        "Mac10": "M1",
        "Mac9":  "M1",
    }
    for prefix, chip in chip_map.items():
        if model.startswith(prefix):
            # Detect Pro/Max/Ultra variants
            variants = {"Pro", "Max", "Ultra"}
            for v in variants:
                if v in model:
                    return f"{chip} {v}"
            return chip
    return model  # fallback: raw model identifier


# ── model state ─────────────────────────────────────────────────────────────
class ModelState:
    def __init__(self):
        self.model = None
        self.processor = None
        self.device: Optional[torch.device] = None
        self.dtype: Optional[torch.dtype] = None
        self.status = "idle"          # idle | loading | ready | error
        self.progress = 0             # 0-100
        self.progress_msg = ""
        self.error_msg = ""
        self.last_used = 0.0
        self.lock = threading.Lock()

    def is_loaded(self) -> bool:
        return self.model is not None and self.processor is not None

    def touch(self):
        self.last_used = time.monotonic()


_state = ModelState()


def _load_model():
    """Load model in a background thread."""
    from transformers import AutoModel, AutoProcessor

    _state.status = "loading"
    _state.progress = 0
    _state.progress_msg = "Initializing..."

    try:
        device = get_device()
        dtype = get_dtype(device)
        _state.device = device
        _state.dtype = dtype

        model_id = get_active_model_id()
        needs_download = not is_model_cached(model_id)
        action = "Downloading" if needs_download else "Loading"
        slug = "models--" + model_id.replace("/", "--")  # for progress monitor
        log.info(f"{action} model {model_id} on {device} ({dtype})")
        _state.progress = 5
        _state.progress_msg = f"{action} tokenizer from {model_id}..."

        # Disable CUDA-specific backends when not on CUDA
        if device.type != "cuda":
            torch.backends.cuda.enable_cudnn_sdp(False)

        def _load_pretrained(cls, model_id, **kwargs):
            """Load model. Temporarily enables online if model not cached."""
            hub_dir = MODELS_DIR / "hub"
            slug = "models--" + model_id.replace("/", "--")
            is_cached = is_model_cached(model_id)
            _prev_offline = os.environ.get("HF_HUB_OFFLINE")
            _prev_trans = os.environ.get("TRANSFORMERS_OFFLINE")
            if is_cached:
                # Force local-only to avoid network hangs (sleep/wake broken pipe)
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
            else:
                # Enable online access for downloading
                os.environ["HF_HUB_OFFLINE"] = "0"
                os.environ["TRANSFORMERS_OFFLINE"] = "0"
            try:
                log.info(f"{'Local cache' if is_cached else 'Downloading'}: {model_id}")
                return cls.from_pretrained(model_id, **kwargs)
            finally:
                # Restore previous env state
                if _prev_offline is not None:
                    os.environ["HF_HUB_OFFLINE"] = _prev_offline
                elif "HF_HUB_OFFLINE" in os.environ:
                    del os.environ["HF_HUB_OFFLINE"]
                if _prev_trans is not None:
                    os.environ["TRANSFORMERS_OFFLINE"] = _prev_trans
                elif "TRANSFORMERS_OFFLINE" in os.environ:
                    del os.environ["TRANSFORMERS_OFFLINE"]

        processor = _load_pretrained(
            AutoProcessor, get_active_model_id(),
            trust_remote_code=True,
        )
        _state.progress = 30
        _state.progress_msg = f"Tokenizer ready. {action} model weights..."

        # ── Loading progress monitor (works for both cached & downloading) ─
        _progress_stop = threading.Event()
        _model_size_gb = 0
        for _k, _info in AVAILABLE_MODELS.items():
            if _info["id"] == model_id:
                _model_size_gb = _info["size_gb"]
                break
        _progress_start = time.monotonic()

        def _monitor_progress():
            """Track loading/download progress by polling disk cache size."""
            blobs_dir = MODELS_DIR / "hub" / slug / "blobs"
            last_total = 0
            while not _progress_stop.is_set():
                try:
                    total = sum(
                        f.stat().st_size for f in blobs_dir.rglob("*")
                        if f.is_file()
                    ) if blobs_dir.exists() else 0
                    if needs_download and _model_size_gb > 0:
                        # Map download progress 30→85%
                        est_bytes = int(_model_size_gb * 1e9)
                        pct = min(85, 30 + int(55 * total / est_bytes))
                        _state.progress = pct
                        mb = total / 1e6
                        _state.progress_msg = (
                            f"Downloading weights ({mb:.0f} MB / ~{_model_size_gb:.1f} GB)…"
                        )
                    else:
                        # Cached model: advance smoothly toward 85% over time
                        elapsed = time.monotonic() - _progress_start
                        # Estimate: ~6s/GB for MPS fp16 loading from SSD (conservative)
                        est_seconds = max(15, _model_size_gb * 6) if _model_size_gb > 0 else 15
                        smooth_pct = min(85, 30 + int(55 * elapsed / est_seconds))
                        _state.progress = max(_state.progress, smooth_pct)
                        if total > last_total:
                            mb = total / 1e6
                            _state.progress_msg = (
                                f"Loading weights ({mb:.0f} MB loaded)…"
                            )
                        else:
                            _state.progress_msg = "Loading model weights into memory…"
                        last_total = total
                except Exception:
                    pass
                _progress_stop.wait(2)

        processor.audio_tokenizer = processor.audio_tokenizer.to(device)
        _state.progress = 40
        _state.progress_msg = "Audio tokenizer loaded. Loading LM weights..."

        # Start progress monitor AFTER setting progress to 40 (avoid race)
        _monitor_thread = threading.Thread(target=_monitor_progress, daemon=True)
        _monitor_thread.start()

        attn_impl = "eager"  # most compatible across devices
        if device.type == "cuda" and importlib.util.find_spec("flash_attn"):
            if dtype in (torch.float16, torch.bfloat16):
                major, _ = torch.cuda.get_device_capability()
                if major >= 8:
                    attn_impl = "flash_attention_2"

        model = _load_pretrained(
            AutoModel, get_active_model_id(),
            trust_remote_code=True,
            attn_implementation=attn_impl,
            torch_dtype=dtype,
        ).to(device)
        model.eval()

        _state.progress = 90
        _state.progress_msg = "Warming up — JIT compiling kernels…"

        # Warm-up inference to JIT-compile kernels
        try:
            with torch.no_grad():
                warm_conv = [processor.build_user_message(text="Hello.")]
                warm_batch = processor([warm_conv], mode="generation")
                warm_ids = warm_batch["input_ids"].to(device)
                warm_mask = warm_batch["attention_mask"].to(device)
                model.generate(warm_ids, attention_mask=warm_mask, max_new_tokens=64)
        except Exception as e:
            log.warning(f"Warm-up failed (non-fatal): {e}")

        _state.progress = 95
        _state.progress_msg = "Warm-up complete. Finalizing…"

        with _state.lock:
            _state.model = model
            _state.processor = processor
            _state.status = "ready"
            _state.progress = 100
            _state.progress_msg = "Ready"
            _state.touch()

        log.info("Model loaded and ready.")

    except Exception as exc:
        log.exception("Model loading failed")
        with _state.lock:
            _state.status = "error"
            _state.error_msg = str(exc)
            _state.progress = 0
            _state.model = None
            _state.processor = None

    finally:
        # Stop progress monitor
        _progress_stop.set()


def ensure_loaded():
    """Trigger model loading if not already loaded or loading."""
    with _state.lock:
        if _state.status in ("idle", "error"):
            _state.status = "loading"
            _state.progress = 0
            _state.progress_msg = "Starting…"
            _state.error_msg = ""
            t = threading.Thread(target=_load_model, daemon=True)
            t.start()


def _inactivity_watchdog():
    """Unload model after INACTIVITY_TIMEOUT seconds of no use.  0 = never auto-unload."""
    if INACTIVITY_TIMEOUT <= 0:
        log.info("Inactivity watchdog disabled (timeout=0). Model will stay loaded until explicit unload.")
        return
    while True:
        time.sleep(30)
        if not _state.is_loaded():
            continue
        idle = time.monotonic() - _state.last_used
        if idle >= INACTIVITY_TIMEOUT:
            log.info(f"Unloading model after {idle:.0f}s inactivity")
            with _state.lock:
                _state.model = None
                _state.processor = None
                _state.status = "idle"
                _state.progress = 0
            gc.collect()
            if torch.backends.mps.is_available():
                pass  # MPS doesn't have explicit cache clear API
            elif torch.cuda.is_available():
                torch.cuda.empty_cache()


threading.Thread(target=_inactivity_watchdog, daemon=True).start()


# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="MOSSlanding Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── request/response models ──────────────────────────────────────────────────
class SynthesizeRequest(BaseModel):
    text: str
    language: Optional[str] = None
    voice: Optional[str] = None          # filename of saved reference voice (no path)
    mode: str = "clone"                  # direct | clone | continue
    max_new_tokens: int = 4096
    duration_tokens: Optional[int] = None   # explicit duration control
    quality: int = 32                    # n_vq_for_inference: 4 | 8 | 16 | 32
    temperature: float = 1.7
    top_p: float = 0.8
    top_k: int = 25
    repetition_penalty: float = 1.0
    do_sample: bool = True


class StatusResponse(BaseModel):
    status: str
    progress: int
    message: str
    model_id: str
    device: str
    chip: str
    models_dir: str
    error: Optional[str] = None


# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/api/status", response_model=StatusResponse)
def get_status():
    device_str = str(_state.device) if _state.device else "unknown"
    chip_str = detect_chip()
    return StatusResponse(
        status=_state.status,
        progress=_state.progress,
        message=_state.progress_msg,
        model_id=get_active_model_id(),
        device=device_str,
        chip=chip_str,
        models_dir=str(MODELS_DIR),
        error=_state.error_msg or None,
    )


@app.get("/api/models")
def list_models():
    """Return model catalogue with download status for each."""
    hub_dir = MODELS_DIR / "hub"
    result = []
    for key, info in AVAILABLE_MODELS.items():
        hf_slug = "models--" + info["id"].replace("/", "--")
        downloaded = is_model_cached(info["id"])
        result.append({
            "key":         key,
            "id":          info["id"],
            "description": info["description"],
            "size_gb":     info["size_gb"],
            "recommended": info["recommended"],
            "downloaded":  downloaded,
            "active":      info["id"] == get_active_model_id(),
        })
    return {"models": result, "models_dir": str(MODELS_DIR)}


@app.post("/api/load")
def trigger_load():
    ensure_loaded()
    return {"ok": True}


@app.post("/api/unload")
def manual_unload():
    with _state.lock:
        if not _state.is_loaded():
            return {"ok": True, "message": "Model was not loaded."}
        _state.model = None
        _state.processor = None
        _state.status = "idle"
        _state.progress = 0
        _state.progress_msg = ""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    log.info("Model unloaded via /api/unload")
    return {"ok": True, "message": "Model unloaded."}


class SwitchModelRequest(BaseModel):
    model_key: str


@app.post("/api/switch-model")
def switch_model(req: SwitchModelRequest):
    """Switch the active model. Body: {"model_key": "moss-v1.5-8b"}"""
    global _active_model_key, _active_model_id
    model_key = req.model_key

    if not model_key or model_key not in AVAILABLE_MODELS:
        valid = ", ".join(AVAILABLE_MODELS.keys())
        raise HTTPException(400, f"Invalid model key. Choose from: {valid}")

    if model_key == _active_model_key and _state.status == "ready":
        return {"ok": True, "message": f"Model '{model_key}' is already active."}

    # Check if model is cached; if not, allow online download
    new_id = AVAILABLE_MODELS[model_key]["id"]
    slug = "models--" + new_id.replace("/", "--")
    is_cached = is_model_cached(new_id)

    # Unload current model
    with _state.lock:
        if _state.is_loaded():
            _state.model = None
            _state.processor = None
        _state.status = "idle"
        _state.progress = 0
        _state.progress_msg = ""
        _state.error_msg = ""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Switch the active model
    _active_model_key = model_key
    _active_model_id = new_id

    # Trigger load — _load_pretrained handles online/offline per-call
    ensure_loaded()

    msg = "Switching" if is_cached else "Downloading & switching"
    return {"ok": True, "message": f"{msg} to {model_key} ({new_id})."}


@app.post("/api/synthesize")
async def synthesize(req: SynthesizeRequest):
    if _state.status == "idle":
        ensure_loaded()
        return Response(
            content=json.dumps({"error": "Model loading started. Please retry in a moment."}),
            status_code=202,
            media_type="application/json",
        )
    if _state.status == "loading":
        raise HTTPException(503, f"Model loading ({_state.progress}%). Please wait.")
    if _state.status == "error":
        raise HTTPException(500, f"Model error: {_state.error_msg}")
    if not _state.is_loaded():
        raise HTTPException(503, "Model not ready")

    processor = _state.processor
    model = _state.model
    device = _state.device

    reference_paths: list[str] = []
    if req.voice and req.mode != "direct":
        vp = VOICES_DIR / req.voice
        if vp.exists():
            reference_paths = [str(vp)]

    msg_kwargs: dict = {}
    if req.language and req.language.lower() not in ("auto", ""):
        msg_kwargs["language"] = req.language
    if reference_paths:
        msg_kwargs["reference"] = reference_paths
    if req.duration_tokens:
        msg_kwargs["tokens"] = req.duration_tokens

    try:
        conversation = [processor.build_user_message(text=req.text, **msg_kwargs)]
        batch = processor([conversation], mode="generation")
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)

        quality = max(4, min(32, req.quality))

        gen_kwargs: dict = dict(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=req.max_new_tokens,
            do_sample=req.do_sample,
            temperature=req.temperature,
            top_p=req.top_p,
            top_k=req.top_k,
            repetition_penalty=req.repetition_penalty,
            n_vq_for_inference=quality,
        )

        # Run blocking generate() in a thread so the event loop stays alive
        _state.status = "generating"
        _state.progress_msg = "Generating audio…"
        loop = asyncio.get_event_loop()
        def _generate():
            with torch.no_grad():
                return model.generate(**gen_kwargs)
        try:
            outputs = await loop.run_in_executor(None, _generate)
        finally:
            _state.status = "ready"
            _state.progress_msg = "Ready"

        messages = processor.decode(outputs)
        if not messages:
            raise HTTPException(500, "No output from model")

        msg = messages[0]
        if not msg.audio_codes_list:
            raise HTTPException(500, "No audio codes in output")

        audio = msg.audio_codes_list[0]  # 1-D float32 waveform on CPU
        sr = processor.model_config.sampling_rate

        audio_np = audio.cpu().float().numpy()

        wav_buf = io.BytesIO()
        sf.write(wav_buf, audio_np, sr, format="WAV", subtype="PCM_16")
        wav_buf.seek(0)

        _state.touch()

        # Save to Desktop
        out_name = f"mosslanding_{uuid.uuid4().hex[:8]}.wav"
        out_path = OUTPUT_DIR / out_name
        sf.write(str(out_path), audio_np, sr, format="WAV", subtype="PCM_16")
        log.info(f"Saved {out_path}")

        return StreamingResponse(
            io.BytesIO(wav_buf.read()),
            media_type="audio/wav",
            headers={"X-Saved-Path": str(out_path), "X-Filename": out_name},
        )

    except Exception as exc:
        log.exception("Synthesis failed")
        raise HTTPException(500, str(exc))


@app.get("/api/voices")
def list_voices():
    voices = []
    for p in sorted(VOICES_DIR.iterdir()):
        if p.suffix.lower() in (".wav", ".mp3", ".m4a", ".flac", ".ogg"):
            voices.append({"name": p.stem, "filename": p.name, "size": p.stat().st_size})
    return {"voices": voices}


@app.post("/api/voices/upload")
async def upload_voice(file: UploadFile = File(...), name: Optional[str] = None):
    ext = Path(file.filename).suffix.lower() if file.filename else ".wav"
    if ext not in (".wav", ".mp3", ".m4a", ".flac", ".ogg"):
        raise HTTPException(400, "Unsupported audio format")

    stem = name or Path(file.filename).stem if file.filename else f"voice_{uuid.uuid4().hex[:6]}"
    # sanitize
    stem = "".join(c for c in stem if c.isalnum() or c in "_- ").strip()[:40] or f"voice_{uuid.uuid4().hex[:6]}"
    dest = VOICES_DIR / f"{stem}{ext}"

    data = await file.read()
    dest.write_bytes(data)
    log.info(f"Saved voice: {dest}")
    return {"ok": True, "filename": dest.name, "name": stem}


@app.delete("/api/voices/{filename}")
def delete_voice(filename: str):
    p = VOICES_DIR / filename
    if not p.exists():
        raise HTTPException(404, "Voice not found")
    # Safety: ensure within voices dir
    if VOICES_DIR not in p.parents:
        raise HTTPException(400, "Invalid path")
    p.unlink()
    return {"ok": True}


# ── serve web UI ─────────────────────────────────────────────────────────────
_webui_dir = Path(__file__).parent.parent / "webui"
if _webui_dir.exists():
    app.mount("/", StaticFiles(directory=str(_webui_dir), html=True), name="webui")


# ── entrypoint ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Eagerly start loading the model
    ensure_loaded()
    port = int(os.environ.get("MOSS_TTS_PORT", "8765"))
    log.info(f"Starting MOSSlanding server on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
