#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP="$SCRIPT_DIR/MOSSlanding.app"
MACOS="$APP/Contents/MacOS"
RESOURCES="$APP/Contents/Resources"

echo "================================================="
echo "  Building MOSSlanding.app"
echo "================================================="

# ── Compile Swift binary ─────────────────────────────────────────────────────
echo ""
echo "Compiling Swift app..."
mkdir -p "$MACOS"

swiftc \
    swift/MossTTSApp.swift \
    -o "$MACOS/MOSSlanding" \
    -framework AppKit \
    -framework WebKit \
    -framework Foundation \
    -O \
    2>&1

echo "  Swift binary: $MACOS/MOSSlanding"

# ── Info.plist ────────────────────────────────────────────────────────────────
echo ""
echo "Writing Info.plist..."
cat > "$APP/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.mosslanding.app</string>
    <key>CFBundleName</key>
    <string>MOSSlanding</string>
    <key>CFBundleDisplayName</key>
    <string>MOSSlanding</string>
    <key>CFBundleExecutable</key>
    <string>MOSSlanding</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>MOSSlanding uses the microphone to record voice cloning samples.</string>
    <key>NSAppleScriptEnabled</key>
    <false/>
</dict>
</plist>
EOF

# ── Copy resources ─────────────────────────────────────────────────────────────
echo ""
echo "Copying resources..."
mkdir -p "$RESOURCES/backend" "$RESOURCES/webui"

cp -R backend/ "$RESOURCES/backend/"
cp -R webui/   "$RESOURCES/webui/"

echo "  Resources copied to $RESOURCES"

# ── Generate app icon ──────────────────────────────────────────────────────────
echo ""
echo "Generating app icon..."
ICONSET="$RESOURCES/AppIcon.iconset"
mkdir -p "$ICONSET"

VENV_DIR="$SCRIPT_DIR/venv"
[ ! -d "$VENV_DIR" ] && VENV_DIR="$(dirname "$SCRIPT_DIR")/venv"
if [ -f "$VENV_DIR/bin/python3" ] || [ -f "$VENV_DIR/bin/python" ]; then
    VENV_PY="$(ls "$VENV_DIR/bin/python"* | head -1)"
    "$VENV_PY" "$SCRIPT_DIR/scripts/make_icon.py" "$ICONSET" 2>/dev/null && \
        iconutil -c icns "$ICONSET" -o "$RESOURCES/AppIcon.icns" && \
        echo "  AppIcon.icns created (Pillow)" || echo "  WARNING: icon generation failed"
else
    echo "  Skipping icon (run setup.sh first for Pillow)"
fi

# ── chmod ─────────────────────────────────────────────────────────────────────
chmod +x "$MACOS/MOSSlanding"

echo ""
echo "================================================="
echo "  Build complete!"
echo ""
echo "  App bundle: $APP"
echo ""
echo "  To launch:"
echo "    open $APP"
echo ""
echo "  Or from Finder: double-click MOSSlanding.app"
echo "================================================="
