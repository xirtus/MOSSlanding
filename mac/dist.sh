#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP="$SCRIPT_DIR/MossTTS.app"
VERSION="1.0"
DMG_NAME="MossTTS-${VERSION}"
DMG_FINAL="$SCRIPT_DIR/dist/${DMG_NAME}.dmg"
STAGING="/tmp/mossTTS_dmg_staging_$$"
DMG_TMP="/tmp/${DMG_NAME}_rw.dmg"
BG_PATH="/tmp/mossTTS_dmg_bg.png"

echo "================================================="
echo "  MOSS TTS — Distribution Package"
echo "================================================="

mkdir -p "$SCRIPT_DIR/dist"

# ── 1. Build the app (icon + binary) ─────────────────────────────────────────
echo ""
echo "Step 1/5 — Building app..."

source "$SCRIPT_DIR/venv/bin/activate"

# Regenerate icon with Pillow
python3 "$SCRIPT_DIR/scripts/make_icon.py" "$APP/Contents/Resources/AppIcon.iconset"
iconutil -c icns "$APP/Contents/Resources/AppIcon.iconset" -o "$APP/Contents/Resources/AppIcon.icns"
echo "  Icon: OK"

# Recompile Swift binary
swiftc \
    "$SCRIPT_DIR/swift/MossTTSApp.swift" \
    -o "$APP/Contents/MacOS/MossTTS" \
    -framework AppKit -framework WebKit -framework Foundation \
    -O 2>&1 | grep -E "error:" || true
chmod +x "$APP/Contents/MacOS/MossTTS"

# Sync resources
cp -R "$SCRIPT_DIR/backend/" "$APP/Contents/Resources/backend/"
cp -R "$SCRIPT_DIR/webui/"   "$APP/Contents/Resources/webui/"
echo "  Binary + resources: OK"

# ── 2. Ad-hoc code-sign ───────────────────────────────────────────────────────
echo ""
echo "Step 2/5 — Signing app..."
codesign --force --deep --sign - "$APP" 2>&1 | grep -v "replacing existing signature" || true
echo "  Code-signed (ad-hoc)"

# ── 3. Create DMG background ─────────────────────────────────────────────────
echo ""
echo "Step 3/5 — Generating DMG background..."
python3 "$SCRIPT_DIR/scripts/make_dmg_bg.py" "$BG_PATH"

# ── 4. Assemble staging folder ────────────────────────────────────────────────
echo ""
echo "Step 4/5 — Creating DMG..."
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

# Create .background folder (hidden in Finder)
mkdir -p "$STAGING/.background"
cp "$BG_PATH" "$STAGING/.background/bg.png"

# ── 5. Build read-write DMG, style it, convert to compressed read-only ────────
rm -f "$DMG_TMP" "$DMG_FINAL"

hdiutil create \
    -srcfolder "$STAGING" \
    -volname "MOSS TTS" \
    -fs HFS+ \
    -fsargs "-c c=64,a=16,b=16" \
    -format UDRW \
    -size 800m \
    "$DMG_TMP"

# Mount it to default /Volumes/ location so Finder can see it
MOUNT_OUTPUT="$(hdiutil attach "$DMG_TMP" -noautoopen -noverify 2>&1)"
MOUNT_VOL="/Volumes/MOSS TTS"
echo "  Mounted at $MOUNT_VOL"
sleep 2

# Style the window with AppleScript
osascript << OSASCRIPT_EOF
tell application "Finder"
    set diskRef to disk "MOSS TTS"
    tell diskRef
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {100, 100, 700, 440}
        set theViewOptions to the icon view options of container window
        set arrangement of theViewOptions to not arranged
        set icon size of theViewOptions to 128
        set background picture of theViewOptions to file ".background:bg.png"
        set position of item "MossTTS.app" to {155, 225}
        set position of item "Applications" to {445, 225}
        close
        open
        update without registering applications
        delay 2
        close
    end tell
end tell
OSASCRIPT_EOF

# Force sync and detach
sync
sleep 1
hdiutil detach "$MOUNT_VOL" -quiet 2>/dev/null || \
    hdiutil detach "$(hdiutil info | grep -B5 'MOSS TTS' | grep '/dev/disk' | awk '{print $1}' | head -1)" -quiet 2>/dev/null || true

# Convert to compressed read-only DMG
hdiutil convert "$DMG_TMP" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$DMG_FINAL"

rm -f "$DMG_TMP"
rm -rf "$STAGING"

echo ""
echo "================================================="
printf "  DMG: dist/%s.dmg  (%s)\n" "$DMG_NAME" "$(du -sh "$DMG_FINAL" | cut -f1)"
echo ""
echo "  Double-click to open, drag to Applications."
echo "================================================="

# Open the dist folder
open "$SCRIPT_DIR/dist"
