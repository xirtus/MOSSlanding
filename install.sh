#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "╔══════════════════════════════════════════╗"
echo "║     Mosslanding — Setup & Install        ║"
echo "║     MOSS-TTS Desktop Application         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Check Python ────────────────────────────────────────
echo "→ Checking Python ..."
PYTHON=$(which python3 || which python)
echo "  Using: $PYTHON ($($PYTHON --version 2>&1))"

# ── Check CUDA / GPU ────────────────────────────────────
echo ""
echo "→ Checking GPU ..."
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1 || echo "  nvidia-smi found but could not query"
else
    echo "  ⚠ nvidia-smi not found — GPU may not be available"
fi

# ── Create virtual environment ──────────────────────────
echo ""
echo "→ Creating virtual environment ..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "  ✓ venv created"
else
    echo "  venv already exists"
fi

source venv/bin/activate

# ── Install PyTorch ─────────────────────────────────────
echo ""
echo "→ Installing PyTorch with CUDA support ..."
pip install --quiet --upgrade pip

pip install --quiet \
    "torch==2.9.1+cu128" \
    "torchaudio==2.9.1+cu128" \
    --index-url https://download.pytorch.org/whl/cu128

echo "  ✓ PyTorch installed"

# ── Install transformers + dependencies ─────────────────
echo ""
echo "→ Installing transformers and ML dependencies ..."
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
    "pydantic>=2.0.0"

echo "  ✓ ML dependencies installed"

# ── Install Flash Attention (optional) ──────────────────
echo ""
echo "→ Installing Flash Attention 2 ..."
pip install --quiet flash-attn 2>/dev/null && echo "  ✓ Flash Attention 2 installed" || echo "  ⚠ Flash Attention 2 not available (will use SDPA fallback)"

# ── Create .desktop file ────────────────────────────────
echo ""
echo "→ Creating desktop entry ..."
mkdir -p ~/.local/share/applications

cat > ~/.local/share/applications/mosslanding.desktop << DESKEOF
[Desktop Entry]
Type=Application
Name=Mosslanding
Comment=MOSS-TTS Voice Synthesis Desktop App
Exec=bash -c "cd $APP_DIR && source venv/bin/activate && python src/main.py"
Icon=$APP_DIR/assets/icons/mosslanding.png
Terminal=false
Categories=Audio;Multimedia;
StartupWMClass=mosslanding
DESKEOF

echo "  ✓ Desktop entry created"

# ── Create run script ───────────────────────────────────
cat > "$APP_DIR/run.sh" << 'RUNEOF'
#!/usr/bin/env bash
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
source venv/bin/activate
exec python src/main.py
RUNEOF
chmod +x "$APP_DIR/run.sh"

# ── Generate app icon (simple SVG → PNG placeholder) ────
echo ""
echo "→ Generating app icon ..."
mkdir -p "$APP_DIR/assets/icons"

# Create a simple PNG icon using Python
source venv/bin/activate
python3 << 'ICONEOF'
from PySide6.QtGui import QPainter, QPixmap, QColor, QBrush, QFont, QLinearGradient, QPen
from PySide6.QtCore import Qt, QRect, QPointF

for size in [256, 128, 64, 48, 32]:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    # Background circle with teal gradient
    gradient = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    gradient.setColorAt(0.0, QColor("#0d9488"))
    gradient.setColorAt(1.0, QColor("#0f766e"))
    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.NoPen)

    margin = size * 0.08
    painter.drawRoundedRect(QRect(int(margin), int(margin), int(size - 2*margin), int(size - 2*margin)),
                           int(size * 0.22), int(size * 0.22))

    # "M" letter in white
    painter.setPen(QColor(255, 255, 255))
    font = QFont("SF Pro Display", int(size * 0.45))
    font.setWeight(QFont.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignCenter, "M")

    painter.end()
    pix.save(f"/home/xirtus_arch/Projects/Mosslanding/assets/icons/mosslanding_{size}.png", "PNG")

# Copy largest as default
import shutil
shutil.copy("/home/xirtus_arch/Projects/Mosslanding/assets/icons/mosslanding_256.png",
            "/home/xirtus_arch/Projects/Mosslanding/assets/icons/mosslanding.png")
print("  ✓ Icons generated")
ICONEOF

# ── Done ────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║          Installation Complete!           ║"
echo "╠══════════════════════════════════════════╣"
echo "║                                          ║"
echo "║  To launch:                              ║"
echo "║    $APP_DIR/run.sh                       ║"
echo "║                                          ║"
echo "║  Or find 'Mosslanding' in your app menu  ║"
echo "║                                          ║"
echo "║  First run will download models (~4-6GB) ║"
echo "╚══════════════════════════════════════════╝"
