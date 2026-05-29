# 🤖 Mosslanding — Next-Session Handoff

**Date:** 2026-05-29
**Status:** App runs, model loads, TTS generates audio. Some rough edges remain.

---

## What's Working

- Model loads at **5.91 GB VRAM** on RTX 3070 8GB (was OOM at 7.18 GB before fixes)
- TTS generation produces clean audio (float32, 24 kHz)
- CPU audio tokenizer saves 1.3 GB VRAM
- `device_map="auto"` handles layer placement
- `expandable_segments:True` fixes VRAM fragmentation (was 1.16 GB wasted → 0.01 GB)
- torchcodec crash patched — torchaudio.load/info routes through soundfile
- Model downloader UI — paste any HuggingFace model ID, download, then load
- App data dir at `~/.local/share/Mosslanding/models/`
- Token presets (256/512/1024/2048/4096) for Duration Control
- Windows port complete (glass_window.py with DWM shadow + registry theme)
- macOS port complete (SwiftUI app)

## Key Files (active install)

The user runs from `/home/xirtus_arch/Projects/Mosslanding/` (NOT the `release/` subdir).

| File | Location |
|------|----------|
| `backend.py` | `src/backend.py` |
| `tts_panel.py` | `src/widgets/tts_panel.py` |
| `settings_panel.py` | `src/widgets/settings_panel.py` |
| `glass_window.py` | `src/widgets/glass_window.py` |
| venv | `venv/` (Python 3.14, torch 2.9.1+cu128) |
| models | `models/` (6.7 GB cached) |

**Repo root** (for git): `/home/xirtus_arch/Projects/Mosslanding/release/`

## Critical Gotchas Fixed

1. **CUDA alloc conf ordering** — MUST set `os.environ["PYTORCH_CUDA_ALLOC_CONF"]` BEFORE `import torch`. PyTorch reads it at import time; setting it after is a silent no-op.

2. **cache_dir removed** — transformers v5 dropped the `cache_dir` kwarg from `from_pretrained()`. Use `os.environ["HF_HUB_CACHE"]` instead.

3. **torchcodec crash** — torchaudio 2.9+ defaults to torchcodec backend which requires specific FFmpeg .so versions. Patched via monkey-patch in backend.py that replaces `torchaudio.load/info` with soundfile wrappers.

4. **Audio tokenizer on CPU** — Moving the processor's audio_tokenizer to GPU wastes 1+ GB VRAM. Keep it on CPU.

## Current Environment

```
GPU:  NVIDIA GeForce RTX 3070 Laptop GPU (8 GB VRAM, CUDA 13.2)
CPU:  x86_64
OS:   Arch Linux (rolling)
Python: 3.14.4
torch: 2.9.1+cu128
torchaudio: 2.9.1+cu128
transformers: 5.0.0
PySide6: 6.11.1
FFmpeg: 8.1.1
```

## Remaining Issues / Next Steps

1. **Voice cloning not tested** — the "Clone Voice" mode with reference audio hasn't been end-to-end tested. The user never reported whether uploading a reference clip and cloning works.

2. **MOSS-VoiceGenerator model** — `OpenMOSS-Team/MOSS-VoiceGenerator` is listed but hasn't been downloaded or tested. Unknown if it fits in 8 GB VRAM.

3. **GUI crash logging** — when the app crashes in a QThread, errors may not be visible. Consider adding a log file (`~/.local/share/Mosslanding/mosslanding.log`).

4. **QMediaPlayer audio playback** — audio plays via `QMediaPlayer` → temp WAV file. On some Linux systems this needs `gstreamer` or `qt6-multimedia-ffmpeg` backend. Confirm playback works.

5. **Multi-GPU support** — `device_map="auto"` can split across GPUs but only GPU 0 is queried for VRAM stats. The settings panel should show all GPUs.

6. **No voice cloning reference samples** — the `assets/audio/` directory is referenced but may be empty. Users need sample clips for testing.

7. **Windows not tested** — the `windows/` folder exists and code is complete, but it has never been run on an actual Windows machine.

## Prompt for Next Session

```
I'm continuing work on the Mosslanding project at
/home/xirtus_arch/Projects/Mosslanding/release/.
The active install is at /home/xirtus_arch/Projects/Mosslanding/
(venv, models, src/ are there — NOT inside release/).

Read HANDOFF_NEXT.md in the repo root for context on what's been fixed
and what remains.

Key things to verify:
1. Voice cloning mode with a real reference audio file
2. Audio playback through QMediaPlayer works
3. MOSS-VoiceGenerator model downloads and loads
4. GUI doesn't silently crash — add file-based logging
5. Any regression from the CUDA alloc conf fix
```
