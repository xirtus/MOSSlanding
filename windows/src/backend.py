"""MOSS-TTS Model Backend — async wrapper around HuggingFace transformers pipeline."""

import functools
import importlib.util
import logging
import os
import time
from pathlib import Path
from typing import Optional, Callable

import numpy as np
import torch
from transformers import AutoModel, AutoProcessor

log = logging.getLogger(__name__)

# ── Disable broken cuDNN SDPA backend ──────────────────────
torch.backends.cuda.enable_cudnn_sdp(False)
torch.backends.cuda.enable_flash_sdp(True)
torch.backends.cuda.enable_mem_efficient_sdp(True)
torch.backends.cuda.enable_math_sdp(True)

# ── Model registry ─────────────────────────────────────────
MODEL_TTS = "OpenMOSS-Team/MOSS-TTS-v1.5"
MODEL_VOICE_GEN = "OpenMOSS-Team/MOSS-VoiceGenerator"

CACHE_DIR = Path(__file__).resolve().parent.parent / "models"
os.environ.setdefault("HF_HUB_CACHE", str(CACHE_DIR))

# ── Language tag choices ────────────────────────────────────
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
    return {
        "cuda": True,
        "name": props.name,
        "vram_total_gb": props.total_memory / (1024**3),
        "vram_free_gb": (
            props.total_memory - torch.cuda.memory_allocated()
        ) / (1024**3),
        "compute_capability": f"{props.major}.{props.minor}",
        "cuda_version": torch.version.cuda,
    }


class MossTTSBackend:
    """Manages MOSS-TTS model lifecycle and inference."""

    def __init__(self):
        self._model = None
        self._processor = None
        self._device: Optional[torch.device] = None
        self._sample_rate: int = 24000
        self._loaded_model_name: Optional[str] = None
        self._progress_callback: Optional[Callable[[str], None]] = None

    def set_progress_callback(self, cb: Callable[[str], None] | None):
        self._progress_callback = cb

    def _emit(self, msg: str):
        log.info(msg)
        if self._progress_callback:
            self._progress_callback(msg)

    def load_model(self, model_name: str = MODEL_TTS, force_reload: bool = False):
        """Load (or swap) a MOSS-TTS model onto GPU."""
        if not force_reload and self._loaded_model_name == model_name:
            self._emit(f"Model '{model_name}' already loaded.")
            return

        self.unload()
        self._emit(f"Loading model: {model_name} ...")

        device = get_available_device()
        dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
        attn = resolve_attn_implementation(device, dtype)

        self._emit(f"  Device: {device}, dtype: {dtype}, attn: {attn}")

        self._processor = AutoProcessor.from_pretrained(
            model_name, trust_remote_code=True
        )

        # Move audio tokenizer to GPU if present
        if hasattr(self._processor, "audio_tokenizer"):
            self._processor.audio_tokenizer = self._processor.audio_tokenizer.to(device)

        model_kwargs = {
            "trust_remote_code": True,
            "torch_dtype": dtype,
        }
        if attn and attn not in {"", "none"}:
            model_kwargs["attn_implementation"] = attn

        self._model = AutoModel.from_pretrained(model_name, **model_kwargs).to(device)
        self._model.eval()
        self._device = device

        if hasattr(self._processor, "model_config"):
            self._sample_rate = int(getattr(self._processor.model_config, "sampling_rate", 24000))

        self._loaded_model_name = model_name

        vram_used = torch.cuda.memory_allocated() / (1024**3) if device.type == "cuda" else 0
        self._emit(f"Model loaded. VRAM used: {vram_used:.1f} GB | Sample rate: {self._sample_rate} Hz")

    def unload(self):
        """Free GPU memory by unloading the model."""
        if self._model is not None:
            self._emit("Unloading model from GPU ...")
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
        self._emit("GPU memory cleared.")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def current_model(self) -> str | None:
        return self._loaded_model_name

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    # ── TTS Inference ───────────────────────────────────

    def generate_tts(
        self,
        text: str,
        reference_audio: Optional[str] = None,
        mode: str = "clone",       # "direct", "clone", "continue", "continue_clone"
        language_tag: Optional[str] = None,
        duration_tokens: Optional[int] = None,
        temperature: float = 1.7,
        top_p: float = 0.8,
        top_k: int = 25,
        repetition_penalty: float = 1.0,
        max_new_tokens: int = 4096,
    ) -> tuple[int, np.ndarray]:
        """
        Run TTS inference.

        Returns (sample_rate_hz, audio_array_float32).
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        assert self._model is not None and self._processor is not None and self._device is not None

        started = time.monotonic()
        text = text.strip()
        if not text:
            raise ValueError("Text is empty.")

        self._emit(f"Synthesizing {len(text)} chars ...")

        # Build conversation
        user_kwargs = {"text": text}
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
        self._emit(f"Done in {elapsed:.1f}s | Audio: {duration_s:.1f}s | RTF: {elapsed/duration_s:.2f}x")

        return self._sample_rate, audio_np

    # ── Voice Generator Inference ───────────────────────

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

        self._emit(f"Designing voice: '{instruction[:60]}...'")

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
        self._emit(f"Done in {elapsed:.1f}s | Audio: {duration_s:.1f}s | RTF: {elapsed/duration_s:.2f}x")

        return self._sample_rate, audio_np

    # ── Helpers ─────────────────────────────────────────

    def preload(self, model_name: str = MODEL_TTS):
        """Convenience: load model at startup."""
        self.load_model(model_name)

    def status(self) -> dict:
        return {
            "loaded": self.is_loaded,
            "model": self._loaded_model_name,
            "gpu": gpu_info(),
            "sample_rate": self._sample_rate,
        }
