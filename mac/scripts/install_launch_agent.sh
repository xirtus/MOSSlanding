#!/usr/bin/env bash
# Install or remove the MOSS TTS LaunchAgent for start-at-login

APP_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/MOSSlanding.app"
PLIST_NAME="com.mosslanding.launcher"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

usage() {
    echo "Usage: $0 [install|uninstall|status]"
    exit 1
}

install() {
    if [ ! -d "$APP_PATH" ]; then
        echo "ERROR: MOSSlanding.app not found at $APP_PATH"
        echo "Run build.sh first."
        exit 1
    fi

    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$PLIST_DEST" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$APP_PATH/Contents/MacOS/MOSSlanding</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>$(dirname "$APP_PATH")</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTORCH_MPS_HIGH_WATERMARK_RATIO</key>
        <string>0.0</string>
        <key>OMP_NUM_THREADS</key>
        <string>4</string>
    </dict>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/MOSSlanding.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/MOSSlanding.log</string>
</dict>
</plist>
PLISTEOF

    launchctl load "$PLIST_DEST" 2>/dev/null || launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || true
    echo "Installed: MOSSlanding will start at login."
    echo "Plist: $PLIST_DEST"
}

uninstall() {
    if [ -f "$PLIST_DEST" ]; then
        launchctl unload "$PLIST_DEST" 2>/dev/null || launchctl bootout "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || true
        rm "$PLIST_DEST"
        echo "Removed: MOSSlanding will no longer start at login."
    else
        echo "Not installed."
    fi
}

status() {
    if [ -f "$PLIST_DEST" ]; then
        echo "Installed at: $PLIST_DEST"
        launchctl list "$PLIST_NAME" 2>/dev/null || echo "(not currently loaded)"
    else
        echo "Not installed (start at login disabled)"
    fi
}

case "${1:-}" in
    install)   install ;;
    uninstall) uninstall ;;
    status)    status ;;
    *)         usage ;;
esac
