#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP="$SCRIPT_DIR/MossTTS.app"
MACOS="$APP/Contents/MacOS"
RESOURCES="$APP/Contents/Resources"

echo "================================================="
echo "  Building MossTTS.app"
echo "================================================="

# ── Compile Swift binary ─────────────────────────────────────────────────────
echo ""
echo "Compiling Swift app..."
mkdir -p "$MACOS"

swiftc \
    swift/MossTTSApp.swift \
    -o "$MACOS/MossTTS" \
    -framework AppKit \
    -framework WebKit \
    -framework Foundation \
    -O \
    2>&1

echo "  Swift binary: $MACOS/MossTTS"

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
    <string>com.mosstts.app</string>
    <key>CFBundleName</key>
    <string>MossTTS</string>
    <key>CFBundleDisplayName</key>
    <string>MOSS TTS</string>
    <key>CFBundleExecutable</key>
    <string>MossTTS</string>
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
    <string>MOSS TTS uses the microphone to record voice cloning samples.</string>
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

if [ -f "$SCRIPT_DIR/venv/bin/python3" ] || [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    VENV_PY="$(ls "$SCRIPT_DIR/venv/bin/python"* | head -1)"
    "$VENV_PY" "$SCRIPT_DIR/scripts/make_icon.py" "$ICONSET" 2>/dev/null && \
        iconutil -c icns "$ICONSET" -o "$RESOURCES/AppIcon.icns" && \
        echo "  AppIcon.icns created (Pillow)" || echo "  WARNING: icon generation failed"
else
    echo "  Skipping icon (run setup.sh first for Pillow)"
fi

# ── chmod ─────────────────────────────────────────────────────────────────────
chmod +x "$MACOS/MossTTS"

echo ""
echo "================================================="
echo "  Build complete!"
echo ""
echo "  App bundle: $APP"
echo ""
echo "  To launch:"
echo "    open $APP"
echo ""
echo "  Or from Finder: double-click MossTTS.app"
echo "================================================="
