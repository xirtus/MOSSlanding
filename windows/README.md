# 🪟 Mosslanding for Windows

Native Windows desktop app for the MOSS-TTS voice synthesis model.

## Quick Start

```powershell
git clone https://github.com/xirtus/MOSSlanding
cd MOSSlanding\windows
powershell -ExecutionPolicy Bypass -File install.ps1
```

Then double-click `run.bat` or search "Mosslanding" in the Start Menu.

## Requirements

- Windows 10 22H2 or Windows 11
- NVIDIA GPU with 8 GB+ VRAM (RTX 2070 or better)
- Python 3.10 or later
- CUDA 12.8 (bundled with PyTorch wheels)

## Manual Install

If you prefer to set up manually:

```powershell
# Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install PyTorch with CUDA
pip install torch==2.9.1+cu128 torchaudio==2.9.1+cu128 --index-url https://download.pytorch.org/whl/cu128

# Install remaining dependencies
pip install transformers==5.0.0 accelerate safetensors numpy orjson PyYAML einops tiktoken tqdm psutil packaging ninja librosa soundfile scipy pydantic PySide6

# Launch
python -m src.main
```

## Troubleshooting

### "python not found"
Install Python 3.10+ from https://www.python.org/downloads/ and check "Add Python to PATH".

### "CUDA not available"
The PyTorch `cu128` wheel bundles CUDA 12.8. Make sure your NVIDIA driver is 560.76 or newer. Run `nvidia-smi` to verify.

### "ModuleNotFoundError: PySide6"
Install it manually: `pip install PySide6`

### Flash Attention 2
Flash Attention 2 has limited Windows support. The app falls back to PyTorch's SDPA backend automatically — no action needed.

### Windows Defender warnings
Windows Defender may warn about large PyTorch wheels downloaded via pip. This is safe — all packages come from official PyPI and PyTorch's index.
