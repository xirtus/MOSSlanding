#!/usr/bin/env bash
# ============================================================================
# Mosslanding APT Repository Setup
#
# Run this script to generate an APT repository in the ./repo/ directory.
# Push the entire repo/ folder to the gh-pages branch of your GitHub repo.
#
# Users will then be able to:
#   echo "deb [trusted=yes] https://xirtus.github.io/MOSSlanding/apt/ ./" | \
#     sudo tee /etc/apt/sources.list.d/mosslanding.list
#   sudo apt update
#   sudo apt install mosslanding
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR/repo/apt"
DIST_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/dist"
VERSION="${1:-1.0.0}"
ARCH="amd64"

mkdir -p "$REPO_DIR/pool/main/m/mosslanding"

echo "→ Setting up APT repository..."
echo "  Version: $VERSION"
echo "  Repo dir: $REPO_DIR"

# Copy .deb into pool
DEB_FILE="$DIST_DIR/mosslanding_${VERSION}_${ARCH}.deb"
if [ -f "$DEB_FILE" ]; then
    cp "$DEB_FILE" "$REPO_DIR/pool/main/m/mosslanding/"
    echo "  ✓ Copied $DEB_FILE"
else
    echo "  ⚠ No .deb found at $DEB_FILE"
    echo "  Run build_all.sh first to create the .deb"
    exit 1
fi

# Generate Packages file
cd "$REPO_DIR"
dpkg-scanpackages --multiversion pool/ > dists/stable/main/binary-amd64/Packages.tmp 2>/dev/null || {
    # Manual approach if dpkg-scanpackages not available
    mkdir -p dists/stable/main/binary-amd64
    cat > dists/stable/main/binary-amd64/Packages << PACKEOF
Package: mosslanding
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: amd64
Maintainer: xirtus <xirtus@github.com>
Homepage: https://github.com/xirtus/MOSSlanding
Filename: pool/main/m/mosslanding/mosslanding_${VERSION}_amd64.deb
Size: $(stat -c%s "$REPO_DIR/pool/main/m/mosslanding/mosslanding_${VERSION}_amd64.deb" 2>/dev/null || echo 0)
SHA256: $(sha256sum "$REPO_DIR/pool/main/m/mosslanding/mosslanding_${VERSION}_amd64.deb" 2>/dev/null | cut -d' ' -f1 || echo 'SKIP')
Description: AI-powered offline text-to-speech with voice cloning
 MOSSlanding is a native desktop application for the MOSS-TTS family
 of models.  It runs entirely on your hardware — zero cloud, zero
 subscription, zero limits.
PACKEOF
    echo "  ✓ Generated Packages file manually"
}

# Create Release file
cat > dists/stable/Release << RELEOF
Origin: Mosslanding
Label: Mosslanding
Suite: stable
Codename: stable
Version: ${VERSION}
Architectures: amd64
Components: main
Description: Mosslanding — AI-powered offline TTS with voice cloning
Date: $(date -u +"%a, %d %b %Y %H:%M:%S UTC")
RELEOF

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   APT Repository Ready!                   ║"
echo "╠══════════════════════════════════════════╣"
echo "║                                          ║"
echo "║  To deploy:                              ║"
echo "║    git checkout gh-pages                 ║"
echo "║    cp -r $REPO_DIR/* .                   ║"
echo "║    git add . && git commit -m 'apt repo' ║"
echo "║    git push origin gh-pages              ║"
echo "║                                          ║"
echo "║  Users install with:                     ║"
echo "║    curl -fsSL https://xirtus.github.io/  ║"
echo "║      MOSSlanding/install.sh | sudo bash  ║"
echo "║                                          ║"
echo "║  Or manually:                            ║"
echo "║    echo 'deb [trusted=yes] ...' >> ...   ║"
echo "║    sudo apt update                       ║"
echo "║    sudo apt install mosslanding          ║"
echo "╚══════════════════════════════════════════╝"
