#!/usr/bin/env bash
# ============================================================================
# Mosslanding — Build all Linux packages (.deb, .pkg.tar.zst, .AppImage)
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$RELEASE_DIR/dist"
VERSION="${VERSION:-1.0.0}"
ARCH="${ARCH:-x86_64}"

mkdir -p "$DIST_DIR"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Mosslanding Package Builder v${VERSION}       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ──────────── Debian .deb ────────────
echo "→ Building Debian package (.deb)..."

DEB_ROOT="$SCRIPT_DIR/debian"
APP_ROOT="$DEB_ROOT/opt/mosslanding"
USR_BIN="$DEB_ROOT/usr/bin"
USR_SHARE_APPS="$DEB_ROOT/usr/share/applications"
USR_SHARE_ICONS="$DEB_ROOT/usr/share/icons/hicolor"

# Clean and recreate
rm -rf "$APP_ROOT" "$USR_BIN" "$USR_SHARE_APPS" "$USR_SHARE_ICONS" 2>/dev/null || true
mkdir -p "$APP_ROOT" "$USR_BIN" "$USR_SHARE_APPS"

# Copy app files
rsync -a --exclude='venv' --exclude='models' --exclude='__pycache__' --exclude='*.pyc' \
      "$RELEASE_DIR/linux/" "$APP_ROOT/"
mkdir -p "$APP_ROOT/models"

# Create CLI launcher
cat > "$USR_BIN/mosslanding" << 'CLIEOF'
#!/usr/bin/env bash
APP_DIR="/opt/mosslanding"
if [ ! -d "$APP_DIR/venv" ]; then
    echo "→ First run: setting up Python environment (1–2 min)..."
    /usr/bin/python3 -m venv "$APP_DIR/venv"
    source "$APP_DIR/venv/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet \
        "torch==2.9.1+cu128" "torchaudio==2.9.1+cu128" \
        --index-url https://download.pytorch.org/whl/cu128
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
    pip install --quiet flash-attn 2>/dev/null || true
    echo "✓ Setup complete. Launching..."
    echo ""
fi
cd "$APP_DIR"
source "$APP_DIR/venv/bin/activate"
exec python3 -m src.main "$@"
CLIEOF
chmod 755 "$USR_BIN/mosslanding"

# Desktop entry
cat > "$USR_SHARE_APPS/mosslanding.desktop" << DESKEOF
[Desktop Entry]
Type=Application
Name=Mosslanding
GenericName=MOSS-TTS Voice Synthesis
Comment=AI-powered text-to-speech with voice cloning and voice design
Icon=mosslanding
Exec=/usr/bin/mosslanding %U
Terminal=false
Categories=Audio;Multimedia;ArtificialIntelligence;
Keywords=TTS;voice;cloning;speech;synthesis;AI;MOSS;
StartupWMClass=mosslanding
StartupNotify=true
DESKEOF

# Icons
for size in 32 48 64 128 256; do
    mkdir -p "$USR_SHARE_ICONS/${size}x${size}/apps"
    cp "$APP_ROOT/assets/icons/mosslanding_${size}.png" \
       "$USR_SHARE_ICONS/${size}x${size}/apps/mosslanding.png" 2>/dev/null || true
done
mkdir -p "$USR_SHARE_ICONS/scalable/apps"
cp "$APP_ROOT/assets/icons/mosslanding.svg" \
   "$USR_SHARE_ICONS/scalable/apps/mosslanding.svg" 2>/dev/null || true

# Fix permissions
find "$DEB_ROOT" -type d -exec chmod 755 {} + 2>/dev/null || true
find "$DEB_ROOT/usr" -type f -exec chmod 644 {} + 2>/dev/null || true
find "$DEB_ROOT/opt" -type f -exec chmod 644 {} + 2>/dev/null || true
chmod 755 "$DEB_ROOT/DEBIAN/postinst" "$DEB_ROOT/DEBIAN/prerm" "$DEB_ROOT/DEBIAN"/* 2>/dev/null || true
find "$DEB_ROOT/opt" -name '*.sh' -exec chmod 755 {} + 2>/dev/null || true

# Build .deb
DEB_FILE="$DIST_DIR/mosslanding_${VERSION}_amd64.deb"
dpkg-deb --build "$DEB_ROOT" "$DEB_FILE" 2>&1
echo "✓ .deb built: $DEB_FILE"
ls -lh "$DEB_FILE"

# ──────────── Arch .pkg.tar.zst ────────────
echo ""
echo "→ Building Arch package (.pkg.tar.zst)..."

if command -v makepkg &>/dev/null; then
    ARCH_BUILD_DIR="$SCRIPT_DIR/arch/build"
    rm -rf "$ARCH_BUILD_DIR"
    mkdir -p "$ARCH_BUILD_DIR"

    # Copy PKGBUILD and related files
    cp "$SCRIPT_DIR/arch/PKGBUILD" "$ARCH_BUILD_DIR/"
    cp "$SCRIPT_DIR/arch/mosslanding.install" "$ARCH_BUILD_DIR/"

    cd "$ARCH_BUILD_DIR"

    # Since the source is a URL, we need to either download it or use local files.
    # For CI/local builds, we use the local release/linux/ files directly.
    # Create a modified PKGBUILD that uses local files instead of downloading.
    sed -i "s|source=.*|source=('local')|" PKGBUILD
    sed -i "s|sha256sums=.*|sha256sums=('SKIP')|" PKGBUILD
    sed -i "s|cp -r \"\${srcdir}/MOSSlanding-\${pkgver}/release/linux/\"\*|cp -r \"$RELEASE_DIR/linux/\"*|" PKGBUILD

    # Build
    PKGEXT='.pkg.tar.zst' makepkg -s --noconfirm 2>&1 || {
        echo "⚠ makepkg failed — this is OK if building on non-Arch system"
        echo "  Arch package must be built on Arch Linux with makepkg"
    }

    if ls *.pkg.tar.zst &>/dev/null; then
        cp *.pkg.tar.zst "$DIST_DIR/"
        echo "✓ Arch package built:"
        ls -lh "$DIST_DIR"/*.pkg.tar.zst 2>/dev/null
    fi

    cd "$SCRIPT_DIR"
else
    echo "⚠ makepkg not available — skipping Arch package (build on Arch Linux)"
fi

# ──────────── AppImage ────────────
echo ""
echo "→ Building AppImage..."

if [ -f "$RELEASE_DIR/appimage/build.sh" ]; then
    cd "$RELEASE_DIR/appimage"
    bash build.sh --appimage 2>&1 || bash build.sh 2>&1 || echo "⚠ AppImage build skipped"
    if ls "$RELEASE_DIR/dist/"*.AppImage &>/dev/null 2>&1; then
        cp "$RELEASE_DIR/dist/"*.AppImage "$DIST_DIR/" 2>/dev/null || true
    fi
    if ls "$RELEASE_DIR/dist/"*.tar.xz &>/dev/null 2>&1; then
        cp "$RELEASE_DIR/dist/"*.tar.xz "$DIST_DIR/" 2>/dev/null || true
    fi
else
    echo "⚠ No AppImage build script found — skipping"
fi

# ──────────── Summary ────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║            Build Complete!                    ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Output directory: $DIST_DIR"
echo "║"
ls -lh "$DIST_DIR/" 2>/dev/null | grep -v '^total' | while read -r line; do
    echo "║  $line"
done
echo "╚══════════════════════════════════════════════╝"
