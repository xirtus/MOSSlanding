#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LINUX_DIR="$PROJECT_DIR/linux"
BUILD_DIR="$SCRIPT_DIR/build"
APPDIR="$BUILD_DIR/Mosslanding.AppDir"
VERSION="${VERSION:-1.0.0}"
ARCH="${ARCH:-x86_64}"
MODE="${1:-portable}"
[ "$MODE" = "--appimage" ] && MODE="appimage"

echo "╔══════════════════════════════════════════╗"
echo "║   Mosslanding Builder v$VERSION            ║"
echo "╚══════════════════════════════════════════╝"

if [ "$MODE" = "appimage" ] && ! command -v appimagetool &>/dev/null; then
    echo "⚠ appimagetool not found. Falling back to portable."
    MODE="portable"
fi

rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR"

echo "→ Copying application..."
rsync -a --exclude='venv' --exclude='models' --exclude='__pycache__' \
      --exclude='*.pyc' "$LINUX_DIR/" "$APPDIR/"

echo "→ Bundling Python environment..."
if [ -d "$LINUX_DIR/venv" ]; then
    rsync -a "$LINUX_DIR/venv/" "$APPDIR/venv/"
else
    echo "  No venv — run install.sh in linux/ first"
    exit 1
fi

cat > "$APPDIR/AppRun" << 'APREOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
export PATH="$HERE/venv/bin:$PATH"
export PYTHONPATH="$HERE:$PYTHONPATH"
cd "$HERE"
source "$HERE/venv/bin/activate"
exec python -m src.main "$@"
APREOF
chmod +x "$APPDIR/AppRun"

cp "$APPDIR/assets/icons/mosslanding.svg" "$APPDIR/mosslanding.svg" 2>/dev/null || true
cp "$APPDIR/assets/icons/mosslanding_256.png" "$APPDIR/mosslanding.png" 2>/dev/null || true
cp "$APPDIR/assets/icons/mosslanding_256.png" "$APPDIR/.DirIcon" 2>/dev/null || true

cat > "$APPDIR/mosslanding.desktop" << DESKEOF
[Desktop Entry]
Type=Application
Name=Mosslanding
GenericName=MOSS-TTS Voice Synthesis
Comment=AI-powered text-to-speech with voice cloning and voice design
Icon=mosslanding
Exec=AppRun %U
Terminal=false
Categories=Audio;Multimedia;ArtificialIntelligence;
StartupWMClass=mosslanding
DESKEOF

echo "→ Cleaning up..."
find "$APPDIR/venv" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "$APPDIR/venv" -type f -name '*.pyc' -delete 2>/dev/null || true

OUTPUT_DIR="$PROJECT_DIR/dist"
mkdir -p "$OUTPUT_DIR"

if [ "$MODE" = "appimage" ]; then
    OUTPUT="$OUTPUT_DIR/Mosslanding-${VERSION}-${ARCH}.AppImage"
    echo "→ Building AppImage..."
    ARCH="$ARCH" appimagetool "$APPDIR" "$OUTPUT" 2>&1
else
    OUTPUT="$OUTPUT_DIR/Mosslanding-${VERSION}-${ARCH}.tar.xz"
    echo "→ Creating portable archive..."
    tar -cJf "$OUTPUT" -C "$BUILD_DIR" "Mosslanding.AppDir"
fi
echo -e "\n✓ Done:"
ls -lh "$OUTPUT"
