# MOSSlanding

Native launchers and installers for [MOSS TTS](https://github.com/OpenMOSS/MOSS-TTS) — one per platform.

| Platform | Folder | Status |
|---|---|---|
| macOS (Apple Silicon) | [`mac/`](mac/) | ✅ Ready |
| Linux (NVIDIA / XPS 17) | [`linux/`](linux/) | 🔜 Coming soon |

---

## mac — Native macOS App

A native macOS menu bar app (Swift + WKWebView) backed by a local FastAPI server running the MOSS TTS 1.7B model on Apple Silicon via MPS.

**Requirements:** macOS 13+, M1/M2/M3, 16 GB RAM, Python 3.10+

```bash
cd mac
bash setup.sh    # create venv, install PyTorch + deps
bash build.sh    # compile Swift binary + generate .app bundle
open MossTTS.app
```

To build the DMG installer:
```bash
bash dist.sh     # produces dist/MossTTS-1.0.dmg
```

**Features**
- Menu bar icon, no dock clutter
- Web UI with waveform visualization and drag-drop voice cloning
- Model auto-unloads after 5 min inactivity (memory-safe on 16 GB)
- Audio saved to `~/Desktop/MossTTS/`
- Start-at-login toggle in the menu

---

## linux — CUDA / XPS 17

FastAPI server + launcher targeting NVIDIA GPU on the Dell XPS 17 r1.  
*(In progress)*
