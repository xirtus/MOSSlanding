# Mosslanding — Linux

Native Linux desktop app for MOSS-TTS voice synthesis.

## Quick Start

```bash
./install.sh    # one-time setup
mosslanding     # launch (or find in app menu)
```

## Requirements

- **Linux** with KDE Plasma, GNOME, or any Qt-compatible desktop
- **Python** 3.10+
- **NVIDIA GPU** with 8GB+ VRAM (RTX 2070 or better recommended)
- **CUDA driver** ≥ 12.x (backward compatible with CUDA 12.8 runtime)

## Features

| Mode | Description |
|------|-------------|
| 🎙 **Voice Cloning** | Upload a reference audio clip and clone any voice |
| 📝 **Direct Generation** | Generate speech from text without a reference |
| 🔄 **Continuation** | Continue speech from a reference audio clip |
| ✨ **Voice Design** | Describe a voice in natural language and generate it |

- 30+ languages with automatic detection
- GPU-accelerated with bfloat16 precision + SDPA attention
- Matches your KDE color scheme automatically
- Scrollable responsive layout for any window size

## Manual Install

```bash
# Create venv and install
python3 -m venv venv
source venv/bin/activate
pip install torch==2.9.1+cu128 torchaudio==2.9.1+cu128 \
    --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt

# Run
python -m src.main
```

## AppImage / Portable

```bash
cd ../appimage
./build.sh              # creates portable .tar.xz
./build.sh --appimage   # creates .AppImage (needs appimagetool)
```

## Models

On first launch, MOSS-TTS models are downloaded automatically from HuggingFace:
- `OpenMOSS-Team/MOSS-TTS-v1.5` (~4-6 GB)
- `OpenMOSS-Team/MOSS-VoiceGenerator` (~1-2 GB)

Models are cached in `./models/` for subsequent runs.
