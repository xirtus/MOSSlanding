#!/usr/bin/env bash
# ============================================================================
# Mosslanding — One-liner APT install
#
# Usage:
#   curl -fsSL https://xirtus.github.io/MOSSlanding/install-apt.sh | sudo bash
#
# This adds the Mosslanding APT repo and installs the package.
# ============================================================================
set -euo pipefail

REPO_URL="https://xirtus.github.io/MOSSlanding/apt"
LIST_FILE="/etc/apt/sources.list.d/mosslanding.list"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     Mosslanding APT Repository Setup         ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Must be root
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run as root (use sudo)."
    exit 1
fi

# Detect distro
if command -v lsb_release &>/dev/null; then
    DISTRO="$(lsb_release -si) $(lsb_release -sr)"
else
    DISTRO="Linux"
fi
echo "→ Detected: $DISTRO"
echo ""

# Add repository
echo "→ Adding Mosslanding repository..."
echo "deb [trusted=yes] ${REPO_URL}/ ./" | tee "$LIST_FILE" > /dev/null
echo "  ✓ Repository added"

# Update and install
echo ""
echo "→ Updating package lists..."
apt-get update -qq 2>&1 | tail -1 || {
    echo "  ⚠ Could not update. You may need to install manually:"
    echo "    sudo dpkg -i mosslanding_*.deb"
    exit 1
}

echo ""
echo "→ Installing Mosslanding..."
apt-get install -y mosslanding 2>&1 || {
    echo ""
    echo "⚠ Package installation failed."
    echo "  Try manual install:"
    echo "  wget ${REPO_URL}/pool/main/m/mosslanding/mosslanding_latest_amd64.deb"
    echo "  sudo dpkg -i mosslanding_latest_amd64.deb"
    exit 1
}

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     Mosslanding Installed! 🎉                 ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  Launch:                                     ║"
echo "║    $ mosslanding                              ║"
echo "║                                              ║"
echo "║  First run auto-sets up Python (~2 min).     ║"
echo "║  Then downloads AI models (~4-6 GB).         ║"
echo "╚══════════════════════════════════════════════╝"
