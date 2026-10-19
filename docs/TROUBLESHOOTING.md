# Troubleshooting

## macOS says the app is damaged or cannot be opened

The v1.0 macOS build is **ad-hoc signed, not notarized**. This is a known issue
(#1), not a corrupted download.

1. Verify the SHA-256 of the DMG you downloaded:
   `a75c32b005b7461ddf589ddd2a41ae5ff29a8f9b1f8f239fdf51d26414930d02`
2. Open **System Settings → Privacy & Security** and choose **Open Anyway** for
   MOSSlanding.
3. Or right-click the app in Finder, choose **Open**, and confirm.

Do not disable Gatekeeper globally. A Developer ID-signed and notarized build
is the next release task.

## “Server offline”

The app starts a local Python server and downloads the model on first run.
Check:

- You have at least 16 GB of RAM and enough free disk for the model (several GB).
- Python 3.10+ is installed (`python3 --version`).
- The setup script completed: `cd mac && bash setup.sh`.
- The model download finished; see the app’s model/settings screen.

## Linux / Windows

There are no prebuilt Linux or Windows binaries yet. Build from source:

- Linux: `cd linux && bash install.sh` — see `linux/README.md`
- Windows: `powershell -ExecutionPolicy Bypass -File windows/install.ps1` — see `windows/README.md`

## Still stuck?

Open an issue with your OS version, chip/GPU, Python version, the exact command
you ran, and the last 30 lines of the log. Do not paste API keys or personal
audio.
