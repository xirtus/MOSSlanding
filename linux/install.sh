#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
YELLOW="\033[33m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}"
echo "╔══════════════════════════════════════════════╗"
echo "║         Mosslanding — Installer              ║"
echo "║   MOSS-TTS Voice Synthesis Desktop App       ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${RESET}"

echo -e "\n${BOLD}→ Checking system...${RESET}"
PYTHON=$(which python3 || which python)
echo "  Python: $($PYTHON --version 2>&1)"

if command -v nvidia-smi &>/dev/null; then
    GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "NVIDIA GPU")
    echo "  GPU: $GPU"
else
    echo -e "  ${YELLOW}⚠ No NVIDIA GPU detected — CPU fallback will be used${RESET}"
fi

echo -e "\n${BOLD}→ Creating Python virtual environment...${RESET}"
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "  ✓ venv created"
else
    echo "  venv already exists"
fi
source venv/bin/activate
pip install --quiet --upgrade pip

echo -e "\n${BOLD}→ Installing PyTorch (CUDA 12.8)...${RESET}"
pip install --quiet "torch==2.9.1+cu128" "torchaudio==2.9.1+cu128" \
    --index-url https://download.pytorch.org/whl/cu128
echo "  ✓ PyTorch installed"

echo -e "\n${BOLD}→ Installing ML dependencies...${RESET}"
pip install --quiet \
    "transformers==5.0.0" \
    "accelerate>=1.10.0" \
    "safetensors>=0.6.0" \
    "numpy>=2.0.0" \
    "orjson>=3.11.0" \
    "PyYAML>=6.0" \
    "einops>=0.8.0" \
    "tiktoken>=0.7.0" \
    "tqdm>=4.67.0" \
    "psutil>=5.9.0" \
    "packaging>=24.0" \
    "ninja>=1.11.0" \
    "librosa>=0.11.0" \
    "soundfile>=0.12.0" \
    "scipy>=1.14.0" \
    "pydantic>=2.0.0" \
    "PySide6>=6.5.0"
echo "  ✓ Dependencies installed"

echo -e "\n${BOLD}→ Installing Flash Attention 2...${RESET}"
pip install --quiet flash-attn 2>/dev/null && \
    echo "  ✓ Flash Attention 2 installed" || \
    echo "  ⚠ Flash Attention unavailable (SDPA fallback works fine)"

echo -e "\n${BOLD}→ Setting up desktop integration...${RESET}"

ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
for size in 32 48 64 128 256; do
    mkdir -p "$ICON_DIR/${size}x${size}/apps"
    cp "$APP_DIR/assets/icons/mosslanding_${size}.png" \
       "$ICON_DIR/${size}x${size}/apps/mosslanding.png" 2>/dev/null || true
done
mkdir -p "$ICON_DIR/scalable/apps"
cp "$APP_DIR/assets/icons/mosslanding.svg" \
   "$ICON_DIR/scalable/apps/mosslanding.svg" 2>/dev/null || true
echo "  ✓ Icons installed"

mkdir -p "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
sed "s|Exec=mosslanding|Exec=$APP_DIR/run.sh|g" \
    "$APP_DIR/mosslanding.desktop" > \
    "${XDG_DATA_HOME:-$HOME/.local/share}/applications/mosslanding.desktop"
echo "  ✓ Desktop entry created"

mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/mosslanding" << CLIEOF
#!/usr/bin/env bash
cd "$APP_DIR"
source venv/bin/activate
exec python -m src.main "\$@"
CLIEOF
chmod +x "$HOME/.local/bin/mosslanding"
echo "  ✓ CLI launcher installed (mosslanding)"

if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$ICON_DIR" 2>/dev/null || true
fi
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications" 2>/dev/null || true
fi

echo -e "\n${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════╗"
echo "║       Installation Complete!  🎉              ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Launch from terminal:                       ║"
echo "║    $ mosslanding                              ║"
echo "║  Or find 'Mosslanding' in your app menu      ║"
echo "║  First run downloads ~4-6 GB models           ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${RESET}"
