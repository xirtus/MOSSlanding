#!/usr/bin/env python3
"""MOSS TTS HTTP API server - optimized for Apple Silicon (MPS)."""

import asyncio
import gc
import importlib.util
import io
import json
import logging
import os
import sys
import threading
import time
import uuid
from pathlib import Path
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
log = logging.getLogger("mosstts")

# ── paths ──────────────────────────────────────────────────────────────────
APP_SUPPORT = Path.home() / "Library" / "Application Support" / "MossTTS"
VOICES_DIR = APP_SUPPORT / "voices"
OUTPUT_DIR = Path.home() / "Desktop" / "MossTTS"
VOICES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Allow the bundled MOSS-TTS repo to be found
MOSS_TTS_REPO = Path(os.environ.get("MOSS_TTS_REPO", Path.home() / "MOSS-TTS"))
if MOSS_TTS_REPO.exists() and str(MOSS_TTS_REPO) not in sys.path:
    sys.path.insert(0, str(MOSS_TTS_REPO))

# ── model config ────────────────────────────────────────────────────────────
MODEL_ID = os.environ.get("MOSS_TTS_MODEL_ID", "OpenMOSS-Team/MOSS-TTS-Local-Transformer")
INACTIVITY_TIMEOUT = int(os.environ.get("MOSS_TTS_INACTIVITY_TIMEOUT", "300"))  # seconds

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

        log.info(f"Loading model {MODEL_ID} on {device} ({dtype})")
        _state.progress = 5
        _state.progress_msg = f"Loading tokenizer from {MODEL_ID}..."

        # Disable CUDA-specific backends when not on CUDA
        if device.type != "cuda":
            torch.backends.cuda.enable_cudnn_sdp(False)

        processor = AutoProcessor.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
        )
        _state.progress = 30
        _state.progress_msg = "Tokenizer ready. Loading model weights..."

        processor.audio_tokenizer = processor.audio_tokenizer.to(device)
        _state.progress = 40
        _state.progress_msg = "Audio tokenizer loaded. Loading LM weights..."

        attn_impl = "eager"  # most compatible across devices
        if device.type == "cuda" and importlib.util.find_spec("flash_attn"):
            if dtype in (torch.float16, torch.bfloat16):
                major, _ = torch.cuda.get_device_capability()
                if major >= 8:
                    attn_impl = "flash_attention_2"

        model = AutoModel.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
            attn_implementation=attn_impl,
            torch_dtype=dtype,
        ).to(device)
        model.eval()

        _state.progress = 90
        _state.progress_msg = "Warming up..."

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
        _state.status = "error"
        _state.error_msg = str(exc)
        _state.progress = 0


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
    """Unload model after INACTIVITY_TIMEOUT seconds of no use."""
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
app = FastAPI(title="MOSS TTS Server")

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
    max_new_tokens: int = 4096
    temperature: Optional[float] = None
    top_p: Optional[float] = None


class StatusResponse(BaseModel):
    status: str
    progress: int
    message: str
    model_id: str
    device: str
    error: Optional[str] = None


# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/api/status", response_model=StatusResponse)
def get_status():
    device_str = str(_state.device) if _state.device else "unknown"
    return StatusResponse(
        status=_state.status,
        progress=_state.progress,
        message=_state.progress_msg,
        model_id=MODEL_ID,
        device=device_str,
        error=_state.error_msg or None,
    )


@app.post("/api/load")
def trigger_load():
    """Manually trigger model loading."""
    ensure_loaded()
    return {"ok": True}


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
    if req.voice:
        vp = VOICES_DIR / req.voice
        if vp.exists():
            reference_paths = [str(vp)]

    kwargs = {}
    if req.language and req.language.lower() not in ("auto", ""):
        kwargs["language"] = req.language

    if reference_paths:
        kwargs["reference"] = reference_paths

    try:
        conversation = [processor.build_user_message(text=req.text, **kwargs)]
        batch = processor([conversation], mode="generation")
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)

        gen_kwargs = dict(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=req.max_new_tokens,
        )

        with torch.no_grad():
            outputs = model.generate(**gen_kwargs)

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
        out_name = f"mosstts_{uuid.uuid4().hex[:8]}.wav"
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
    log.info(f"Starting MOSS TTS server on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
