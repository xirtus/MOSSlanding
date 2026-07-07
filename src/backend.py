"""MOSS-TTS Model Backend — async wrapper around HuggingFace transformers pipeline."""

import functools
import importlib.util
import logging
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Optional, Callable

# ── MUST be set before import torch ───────────────────────────
# PyTorch reads these env vars at import time; setting them afterwards
# has zero effect.  expandable_segments prevents the "1 GiB reserved but
# unallocated" fragmentation that causes OOM on ≤8 GiB cards.
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"

import numpy as np
import torch
from transformers import AutoModel, AutoProcessor

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# ── File-based logging (catches GUI thread crashes) ──────────────

def setup_file_logging(log_dir: Path | None = None) -> Path:
    """Configure file-based logging so crashes inside QThreads are captured.

    Returns the path to the log file.
    """
    if log_dir is None:
        # Platform-appropriate app data dir (mirrors _get_app_data_dir)
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        log_dir = base / "Mosslanding"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "mosslanding.log"

    # Don't add duplicate handlers
    root = logging.getLogger()
    already_has = any(
        isinstance(h, logging.FileHandler) and
        os.path.normpath(getattr(h, 'baseFilename', '')) == os.path.normpath(str(log_path))
        for h in root.handlers
    )
    if already_has:
        return log_path

    fh = logging.FileHandler(str(log_path), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # Also keep console handler for stdout
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)-5s] %(name)s: %(message)s"))

    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(ch)

    # Capture unhandled exceptions
    def _excepthook(exc_type, exc_value, exc_tb):
        logging.critical(
            "Unhandled exception:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    logging.info("Mosslanding log started — %s", log_path)
    return log_path

# ── Disable broken cuDNN SDPA backend ────────────────────────
torch.backends.cuda.enable_cudnn_sdp(False)
torch.backends.cuda.enable_flash_sdp(True)
torch.backends.cuda.enable_mem_efficient_sdp(True)
torch.backends.cuda.enable_math_sdp(True)

# ── Patch torchaudio.load → soundfile (torchcodec broken) ────

def _patch_torchaudio():
    """Replace torchaudio.load / torchaudio.info with soundfile wrappers.

    torchaudio 2.9+ defaults to the ``torchcodec`` backend which requires
    FFmpeg shared libraries that are often missing.  Since we already ship
    ``soundfile``, this patch routes all torchaudio file I/O through
    soundfile — transparent to the MOSS-TTS processor.
    """
    try:
        import soundfile as sf
        import torchaudio as _ta

        def _sf_load(uri, *args, **kwargs):
            data_np, sr = sf.read(str(uri), dtype="float32", always_2d=False)
            if data_np.ndim == 1:
                data_np = data_np[:, None].T  # (samples,) → (1, samples)
            else:
                data_np = data_np.T  # (samples, ch) → (ch, samples)
            return torch.from_numpy(data_np.copy()), sr

        def _sf_info(uri, *args, **kwargs):
            info = sf.info(str(uri))
            class _Info: pass
            o = _Info()
            o.sample_rate = info.samplerate
            o.num_frames  = info.frames
            o.num_channels = info.channels
            return o

        _ta.load = _sf_load
        _ta.info = _sf_info
        log.debug("torchaudio.load/info patched → soundfile")
    except Exception:
        log.debug("torchaudio patch skipped (soundfile not available?)")

_patch_torchaudio()

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
    """Get diagnostic info about all GPUs."""
    if not torch.cuda.is_available():
        return {"cuda": False, "device": "cpu", "gpus": []}

    gpus = []
    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        # Per-device VRAM usage
        reserved = torch.cuda.memory_reserved(i)
        allocated = torch.cuda.memory_allocated(i)
        free_bytes = props.total_memory - allocated
        gpus.append({
            "index": i,
            "name": props.name,
            "vram_total_gb": props.total_memory / (1024**3),
            "vram_allocated_gb": allocated / (1024**3),
            "vram_reserved_gb": reserved / (1024**3),
            "vram_free_gb": free_bytes / (1024**3),
            "compute_capability": f"{props.major}.{props.minor}",
        })

    # Primary GPU (legacy compat)
    primary = gpus[0] if gpus else {}
    return {
        "cuda": True,
        "device": "cuda",
        "gpus": gpus,
        "num_gpus": len(gpus),
        "name": primary.get("name", ""),
        "vram_total_gb": primary.get("vram_total_gb", 0),
        "vram_free_gb": primary.get("vram_free_gb", 0),
        "compute_capability": primary.get("compute_capability", ""),
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
        import gc

        if not force_reload and self._loaded_model_name == model_name:
            self._emit(f"Model '{model_name}' already loaded.")
            return

        self.unload()
        gc.collect()  # sweep dangling Python refs before big alloc
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

        # --- VRAM budget for device_map ----------------------
        # On 8 GiB consumer GPUs the model weights alone can fill
        # the card, leaving zero room for the KV cache +
        # activations during generate().  We cap the GPU portion
        # with max_memory so the remaining layers spill to CPU.
        max_memory: dict | None = None
        total_gb: float | None = None
        if device.type == "cuda":
            total_gb = torch.cuda.get_device_properties(device).total_memory / (1024**3)
            if total_gb <= 8.5:
                inference_reserve_gb = 3.0
            elif total_gb <= 12.5:
                inference_reserve_gb = 2.5
            else:
                inference_reserve_gb = 2.0
            gpu_budget_gb = max(3.0, total_gb - inference_reserve_gb)
            max_memory = {
                device.index or 0: f"{gpu_budget_gb:.1f}GiB",
                "cpu": "32GiB",
            }
            self._emit(f"  VRAM budget: GPU ≤ {gpu_budget_gb:.1f} GiB "
                       f"(total {total_gb:.1f} GiB, reserving {inference_reserve_gb:.1f} GiB for inference)")

        # --- Model ------------------------------------------
        self._emit("  Loading model weights …")
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

        model_kwargs: dict = {
            "trust_remote_code": True,
            "torch_dtype": dtype,
            "low_cpu_mem_usage": True,
        }
        if attn and attn not in {"", "none"}:
            model_kwargs["attn_implementation"] = attn

        model_kwargs["device_map"] = "auto"
        if max_memory is not None:
            model_kwargs["max_memory"] = max_memory

        self._model = AutoModel.from_pretrained(model_name, **model_kwargs)
        self._model.eval()
        self._device = device

        if hasattr(self._processor, "model_config"):
            self._sample_rate = int(getattr(self._processor.model_config, "sampling_rate", 24000))

        # Flush transient loading buffers before reporting VRAM
        torch.cuda.empty_cache()
        gc.collect()

        self._loaded_model_name = model_name

        if device.type == "cuda":
            vram_used = torch.cuda.memory_allocated() / (1024**3)
            peak_gb = torch.cuda.max_memory_allocated(device) / (1024**3)
            free_gb = (torch.cuda.get_device_properties(device).total_memory - torch.cuda.memory_allocated()) / (1024**3)
            self._emit(f"✓ Model loaded. VRAM: {vram_used:.1f} GiB "
                       f"(peak {peak_gb:.1f} GiB, free {free_gb:.1f} GiB) "
                       f"| SR: {self._sample_rate} Hz")
        else:
            self._emit(f"✓ Model loaded. | SR: {self._sample_rate} Hz")
    def unload(self):
        """Free GPU memory by unloading the model."""
        if self._model is not None:
            self._emit("Unloading model from GPU …")
            try:
                # device_map="auto" may leave some params on "meta" device;
                # those can't be moved with .cpu().  Delete the model
                # directly and let Python GC handle cleanup.
                self._model.to("cpu")
            except NotImplementedError:
                # Meta tensors exist — just let GC clean up
                pass
            except Exception:
                pass
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
        max_new_tokens: int = 2048,
        quality: int = 32,
    ) -> tuple[int, np.ndarray]:
        """Run TTS inference.  Returns (sample_rate_hz, audio_array_float32).

        Parameters
        ----------
        quality : int
            Number of RVQ codebook layers for inference (4, 8, 16, or 32).
            32 = maximum fidelity, 4 = fastest.
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        assert self._model is not None and self._processor is not None and self._device is not None

        started = time.monotonic()
        text = text.strip()
        if not text:
            raise ValueError("Text is empty.")

        # Clamp quality to valid range
        quality = max(4, min(32, quality))

        self._emit(f"Synthesizing {len(text)} chars (quality={quality}×) …")

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

        # Generate — catch OOM with actionable advice
        try:
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
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            raise RuntimeError(
                "GPU out of memory during generation. "
                "Try reducing 'Max Tokens' (currently "
                f"{int(max_new_tokens)}) in the generation "
                "settings panel, or close other GPU applications."
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
        max_new_tokens: int = 2048,
        quality: int = 32,
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

        quality = max(4, min(32, quality))
        self._emit(f"Designing voice (quality={quality}×): '{instruction[:60]}…'")

        conversations = [[
            self._processor.build_user_message(text=text, instruction=instruction)
        ]]

        batch = self._processor(conversations, mode="generation")
        input_ids = batch["input_ids"].to(self._device)
        attention_mask = batch["attention_mask"].to(self._device)

        try:
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
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            raise RuntimeError(
                "GPU out of memory during voice generation. "
                "Try reducing 'Max Tokens' (currently "
                f"{int(max_new_tokens)}) in the generation "
                "settings, or reload with a smaller model."
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
