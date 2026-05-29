#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================="
echo "  MOSSlanding - macOS Setup (Apple Silicon / M1)"
echo "================================================="

# The venv lives in App Support so the app always finds it from /Applications
APP_SUPPORT="$HOME/Library/Application Support/MOSSlanding"
VENV_DIR="$APP_SUPPORT/venv"
mkdir -p "$APP_SUPPORT"

# Find Python 3.10+
PYTHON=""
for py in python3.12 python3.11 python3.10 python3.13 python3; do
    if command -v "$py" &>/dev/null; then
        PYTHON="$(command -v "$py")"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10+ required. Install via: brew install python@3.12"
    exit 1
fi

echo "Using: $PYTHON ($($PYTHON --version))"
echo "Venv:  $VENV_DIR"

# Create venv in App Support
if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

# Also keep a local ./venv symlink for dev convenience
if [ ! -e "$SCRIPT_DIR/venv" ]; then
    ln -s "$VENV_DIR" "$SCRIPT_DIR/venv"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet

echo ""
echo "Installing Python dependencies..."

pip install torch torchaudio torchcodec --quiet 2>/dev/null || pip install torch torchaudio --quiet
pip install pillow --quiet

pip install \
    fastapi \
    "uvicorn[standard]" \
    "transformers==5.0.0" \
    safetensors \
    numpy \
    scipy \
    soundfile \
    librosa \
    tqdm \
    pyyaml \
    einops \
    tiktoken \
    psutil \
    packaging \
    orjson \
    huggingface_hub \
    python-multipart \
    --quiet

echo ""
echo "Installing MOSS-TTS from local repo..."
MOSS_TTS_REPO="${MOSS_TTS_REPO:-$HOME/MOSS-TTS}"
if [ -d "$MOSS_TTS_REPO" ]; then
    pip install -e "$MOSS_TTS_REPO" --no-deps --quiet
    echo "  Installed from $MOSS_TTS_REPO"
else
    echo "  WARNING: MOSS-TTS repo not found at $MOSS_TTS_REPO"
    echo "  Clone it: git clone https://github.com/OpenMOSS/MOSS-TTS.git ~/MOSS-TTS"
fi

echo ""
echo "================================================="
echo "  Setup complete!"
echo ""
echo "  Venv installed at:"
echo "    $VENV_DIR"
echo ""
echo "  Next steps:"
echo "    1. bash build.sh        # build MOSSlanding.app"
echo "    2. bash dist.sh         # build DMG installer"
echo "    3. open MOSSlanding.app # launch"
echo ""
echo "  Or test the backend:"
echo "    source \"$VENV_DIR/bin/activate\""
echo "    python backend/server.py"
echo "    curl http://127.0.0.1:8765/api/status"
echo "================================================="
