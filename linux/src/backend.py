"""MOSS-TTS Model Backend — async wrapper around HuggingFace transformers pipeline."""

import functools
import importlib.util
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional, Callable

import numpy as np
import torch
from transformers import AutoModel, AutoProcessor

log = logging.getLogger(__name__)

# ── VRAM fragmentation workaround ────────────────────────────
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# ── Disable broken cuDNN SDPA backend ────────────────────────
torch.backends.cuda.enable_cudnn_sdp(False)
torch.backends.cuda.enable_flash_sdp(True)
torch.backends.cuda.enable_mem_efficient_sdp(True)
torch.backends.cuda.enable_math_sdp(True)

# ── App data directory ───────────────────────────────────────

def _get_app_data_dir() -> Path:
    """Platform-appropriate application data directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "Mosslanding"


APP_DIR = _get_app_data_dir()
MODELS_DIR = APP_DIR / "models"
os.environ.setdefault("HF_HOME", str(APP_DIR / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(MODELS_DIR))

# ── Model registry ───────────────────────────────────────────
MODEL_TTS = "OpenMOSS-Team/MOSS-TTS-v1.5"
MODEL_VOICE_GEN = "OpenMOSS-Team/MOSS-VoiceGenerator"

# ── Language tag choices ──────────────────────────────────────
LANGUAGE_TAGS = [
    "Chinese", "Cantonese", "English", "Arabic", "Czech", "Danish",
    "Dutch", "Finnish", "French", "German", "Greek", "Hebrew",
    "Hindi", "Hungarian", "Italian", "Japanese", "Korean",
    "Macedonian", "Malay", "Persian (Farsi)", "Polish",
    "Portuguese", "Romanian", "Russian", "Spanish", "Swahili",
    "Swedish", "Tagalog", "Thai", "Turkish", "Vietnamese",
]


def resolve_attn_implementation(device: torch.device, dtype: torch.dtype) -> str | None:
    """Choose best attention backend for the hardware."""
    if device.type != "cuda":
        return "eager"
    if (
        importlib.util.find_spec("flash_attn") is not None
        and dtype in {torch.float16, torch.bfloat16}
    ):
        major, _ = torch.cuda.get_device_capability(device)
        if major >= 8:
            return "flash_attention_2"
    return "sdpa"


def get_available_device() -> torch.device:
    """Return best available compute device."""
    if torch.cuda.is_available():
        return torch.device("cuda:0")
    return torch.device("cpu")


def gpu_info() -> dict:
    """Get diagnostic info about the GPU."""
    if not torch.cuda.is_available():
        return {"cuda": False, "device": "cpu"}
    props = torch.cuda.get_device_properties(0)
    free_bytes = props.total_memory - torch.cuda.memory_allocated()
    return {
        "cuda": True,
        "name": props.name,
        "vram_total_gb": props.total_memory / (1024**3),
        "vram_free_gb": free_bytes / (1024**3),
        "compute_capability": f"{props.major}.{props.minor}",
        "cuda_version": torch.version.cuda,
    }


def get_model_size_gb(model_name: str) -> Optional[float]:
    """Estimate download size for a HuggingFace model by checking
    its config / readme.  Returns None if unknown."""
    # Known sizes (rough safetensors + config)
    KNOWN_SIZES: dict[str, float] = {
        "OpenMOSS-Team/MOSS-TTS-v1.5": 4.2,
        "OpenMOSS-Team/MOSS-VoiceGenerator": 1.2,
    }
    return KNOWN_SIZES.get(model_name)


class MossTTSBackend:
    """Manages MOSS-TTS model lifecycle and inference."""

    def __init__(self):
        self._model = None
        self._processor = None
        self._device: Optional[torch.device] = None
        self._sample_rate: int = 24000
        self._loaded_model_name: Optional[str] = None
        self._progress_callback: Optional[Callable[[str], None]] = None

        # Ensure app directories exist
        APP_DIR.mkdir(parents=True, exist_ok=True)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Progress callback ─────────────────────────────────

    def set_progress_callback(self, cb: Callable[[str], None] | None):
        self._progress_callback = cb

    def _emit(self, msg: str):
        log.info(msg)
        if self._progress_callback:
            self._progress_callback(msg)

    # ── Model download (explicit, user-facing) ────────────

    def download_model(self, model_name: str) -> bool:
        """Explicitly download a model from HuggingFace into the app cache.

        This is the user-visible "Download" action.  It simply fetches
        the processor and model config/weights so that a later
        ``load_model()`` call is instant.
        """
        self._emit(f"Downloading {model_name} …")

        size_gb = get_model_size_gb(model_name)
        if size_gb:
            self._emit(f"  Expected download: ~{size_gb:.1f} GB")
        self._emit(f"  Cache: {MODELS_DIR}")

        try:
            self._emit("  Fetching processor …")
            AutoProcessor.from_pretrained(model_name, trust_remote_code=True)

            self._emit("  Fetching model weights …")
            dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
            AutoModel.from_pretrained(
                model_name, trust_remote_code=True, torch_dtype=dtype,
            )

            self._emit(f"✓ {model_name} downloaded successfully.")
            return True
        except Exception as exc:
            self._emit(f"✗ Download failed: {exc}")
            return False

    # ── Model loading / unloading ─────────────────────────

    def load_model(self, model_name: str = MODEL_TTS, force_reload: bool = False):
        """Load (or swap) a MOSS-TTS model onto GPU.

        If the model hasn't been downloaded yet, it will be pulled from the
        HuggingFace Hub automatically by ``from_pretrained()``.
        """
        if not force_reload and self._loaded_model_name == model_name:
            self._emit(f"Model '{model_name}' already loaded.")
            return

        self.unload()
        self._emit(f"Loading model: {model_name} …")

        device = get_available_device()
        dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
        attn = resolve_attn_implementation(device, dtype)

        self._emit(f"  Device: {device}, dtype: {dtype}, attn: {attn}")

        # --- Processor (keep on CPU to save VRAM) ------------
        self._emit("  Loading processor …")
        self._processor = AutoProcessor.from_pretrained(
            model_name, trust_remote_code=True
        )
        # The audio tokenizer stays on CPU — it only runs a few times per
        # generation and keeping it off-GPU saves 500 MB–1 GB VRAM.
        if hasattr(self._processor, "audio_tokenizer"):
            self._processor.audio_tokenizer = self._processor.audio_tokenizer.cpu()

        # --- Model ------------------------------------------
        self._emit("  Loading model weights …")
        model_kwargs: dict = {
            "trust_remote_code": True,
            "torch_dtype": dtype,
        }
        if attn and attn not in {"", "none"}:
            model_kwargs["attn_implementation"] = attn

        # Use device_map="auto" so that transformers can
        # intelligently place layers — helps avoid OOM on 8 GB cards.
        model_kwargs["device_map"] = "auto"

        self._model = AutoModel.from_pretrained(model_name, **model_kwargs)
        self._model.eval()
        self._device = device

        if hasattr(self._processor, "model_config"):
            self._sample_rate = int(getattr(self._processor.model_config, "sampling_rate", 24000))

        self._loaded_model_name = model_name

        vram_used = torch.cuda.memory_allocated() / (1024**3) if device.type == "cuda" else 0
        self._emit(f"✓ Model loaded. VRAM: {vram_used:.1f} GB | SR: {self._sample_rate} Hz")

    def unload(self):
        """Free GPU memory by unloading the model."""
        if self._model is not None:
            self._emit("Unloading model from GPU …")
            self._model.cpu()
            del self._model
            self._model = None
        if self._processor is not None:
            if hasattr(self._processor, "audio_tokenizer"):
                try:
                    self._processor.audio_tokenizer.cpu()
                except Exception:
                    pass
            self._processor = None
        self._loaded_model_name = None
        torch.cuda.empty_cache()
        self._emit("✓ GPU memory cleared.")

    # ── Convenience ───────────────────────────────────────

    def preload(self, model_name: str = MODEL_TTS):
        """Load model at startup."""
        self.load_model(model_name)

    # ── Properties ────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def current_model(self) -> str | None:
        return self._loaded_model_name

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def status(self) -> dict:
        return {
            "loaded": self.is_loaded,
            "model": self._loaded_model_name,
            "gpu": gpu_info(),
            "sample_rate": self._sample_rate,
        }

    # ── TTS Inference ─────────────────────────────────────

    def generate_tts(
        self,
        text: str,
        reference_audio: Optional[str] = None,
        mode: str = "clone",
        language_tag: Optional[str] = None,
        duration_tokens: Optional[int] = None,
        temperature: float = 1.7,
        top_p: float = 0.8,
        top_k: int = 25,
        repetition_penalty: float = 1.0,
        max_new_tokens: int = 4096,
    ) -> tuple[int, np.ndarray]:
        """Run TTS inference.  Returns (sample_rate_hz, audio_array_float32)."""
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        assert self._model is not None and self._processor is not None and self._device is not None

        started = time.monotonic()
        text = text.strip()
        if not text:
            raise ValueError("Text is empty.")

        self._emit(f"Synthesizing {len(text)} chars …")

        # Build conversation
        user_kwargs: dict = {"text": text}
        if language_tag and language_tag.strip():
            user_kwargs["language"] = language_tag.strip()
        if duration_tokens is not None:
            user_kwargs["tokens"] = int(duration_tokens)

        if not reference_audio:
            conversations = [[self._processor.build_user_message(**user_kwargs)]]
            inference_mode = "generation"
        elif mode == "clone":
            user_kwargs["reference"] = [reference_audio]
            conversations = [[self._processor.build_user_message(**user_kwargs)]]
            inference_mode = "generation"
        elif mode == "continue":
            conversations = [[
                self._processor.build_user_message(**user_kwargs),
                self._processor.build_assistant_message(audio_codes_list=[reference_audio]),
            ]]
            inference_mode = "continuation"
        elif mode == "continue_clone":
            user_kwargs["reference"] = [reference_audio]
            conversations = [[
                self._processor.build_user_message(**user_kwargs),
                self._processor.build_assistant_message(audio_codes_list=[reference_audio]),
            ]]
            inference_mode = "continuation"
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Tokenize
        batch = self._processor(conversations, mode=inference_mode)
        input_ids = batch["input_ids"].to(self._device)
        attention_mask = batch["attention_mask"].to(self._device)

        # Generate
        with torch.no_grad():
            outputs = self._model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=int(max_new_tokens),
                audio_temperature=float(temperature),
                audio_top_p=float(top_p),
                audio_top_k=int(top_k),
                audio_repetition_penalty=float(repetition_penalty),
            )

        # Decode
        messages = self._processor.decode(outputs)
        if not messages or messages[0] is None:
            raise RuntimeError("Model returned empty result.")

        audio = messages[0].audio_codes_list[0]
        if isinstance(audio, torch.Tensor):
            audio_np = audio.detach().float().cpu().numpy()
        else:
            audio_np = np.asarray(audio, dtype=np.float32)

        if audio_np.ndim > 1:
            audio_np = audio_np.reshape(-1)
        audio_np = audio_np.astype(np.float32, copy=False)

        elapsed = time.monotonic() - started
        duration_s = len(audio_np) / self._sample_rate
        self._emit(f"✓ Done in {elapsed:.1f}s | Audio: {duration_s:.1f}s | RTF: {elapsed/duration_s:.2f}x")

        return self._sample_rate, audio_np

    # ── Voice Generator Inference ─────────────────────────

    def generate_voice(
        self,
        text: str,
        instruction: str,
        temperature: float = 1.5,
        top_p: float = 0.6,
        top_k: int = 50,
        repetition_penalty: float = 1.1,
        max_new_tokens: int = 4096,
    ) -> tuple[int, np.ndarray]:
        """Design a voice from instruction + text."""
        if not self.is_loaded:
            raise RuntimeError("Model not loaded.")

        assert self._model is not None and self._processor is not None and self._device is not None

        started = time.monotonic()
        text = text.strip()
        instruction = instruction.strip()
        if not text:
            raise ValueError("Text is empty.")
        if not instruction:
            raise ValueError("Voice instruction is empty.")

        self._emit(f"Designing voice: '{instruction[:60]}…'")

        conversations = [[
            self._processor.build_user_message(text=text, instruction=instruction)
        ]]

        batch = self._processor(conversations, mode="generation")
        input_ids = batch["input_ids"].to(self._device)
        attention_mask = batch["attention_mask"].to(self._device)

        with torch.no_grad():
            outputs = self._model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=int(max_new_tokens),
                audio_temperature=float(temperature),
                audio_top_p=float(top_p),
                audio_top_k=int(top_k),
                audio_repetition_penalty=float(repetition_penalty),
            )

        messages = self._processor.decode(outputs)
        if not messages or messages[0] is None:
            raise RuntimeError("Model returned empty result.")

        audio = messages[0].audio_codes_list[0]
        if isinstance(audio, torch.Tensor):
            audio_np = audio.detach().float().cpu().numpy()
        else:
            audio_np = np.asarray(audio, dtype=np.float32)

        if audio_np.ndim > 1:
            audio_np = audio_np.reshape(-1)
        audio_np = audio_np.astype(np.float32, copy=False)

        elapsed = time.monotonic() - started
        duration_s = len(audio_np) / self._sample_rate
        self._emit(f"✓ Done in {elapsed:.1f}s | Audio: {duration_s:.1f}s | RTF: {elapsed/duration_s:.2f}x")

        return self._sample_rate, audio_np
