# 🔊 MOSSlanding

### The best voice-cloning TTS on the planet. Runs on your machine. Costs nothing.

> Clone any voice from a 5-second sample. Speak 31 languages. Zero cloud. Zero subscription. Zero compromise.

<div align="center">

**[⬇️ Download for macOS](https://github.com/xirtus/MOSSlanding/releases/latest)** &nbsp;·&nbsp; **[🐧 Linux](linux/)** &nbsp;·&nbsp; **[🪟 Windows](windows/)** &nbsp;·&nbsp; Free & Open Source

</div>

---

## Why MOSSlanding destroys the competition

Most "AI voice" tools make you pay $30/month, upload your audio to their servers, and still sound robotic. MOSSLanding runs entirely on your hardware, produces broadcast-quality speech, and clones voices with frightening accuracy — all from open-source models you own.

| | MOSSLanding | ElevenLabs | Murf | Play.ht |
|---|:---:|:---:|:---:|:---:|
| **Zero-shot voice cloning** | ✅ | ✅ | ❌ | ✅ |
| **Runs 100% offline** | ✅ | ❌ | ❌ | ❌ |
| **Free forever** | ✅ | ❌ | ❌ | ❌ |
| **31 languages** | ✅ | ✅ | ⚠️ | ⚠️ |
| **Your data stays private** | ✅ | ❌ | ❌ | ❌ |
| **Native desktop app** | ✅ | — | — | — |
| **Windows + Linux + NVIDIA support** | ✅ | — | — | — |

---

## What it can do

**🎤 Voice Cloning** — Drop in any 5–30 second audio clip and it instantly learns the voice. Accent, tone, cadence — all of it. Works on the first try.

**🌍 31 Languages** — English, Chinese, Japanese, French, Spanish, Arabic, Hindi, Korean and 23 more. Switch mid-sentence.

**🎯 Pinyin / IPA / Phoneme control** — Nail every pronunciation. Perfect for names, technical terms, multilingual scripts.

**⏸️ Explicit pause control** — `[pause 1.5s]` anywhere in your text. Precise timing, no guessing.

**⚡ Apple Silicon MPS** — Runs the full 1.7B model on M1/M2/M3 via Metal. No GPU required. No CUDA. Just your Mac.

**🪟🐧 Windows + Linux + NVIDIA** — Native PySide6 desktop app with Windows dark/light mode and KDE/GNOME theme integration. RTX 2070+ with bfloat16 precision.

**🔒 100% private** — The model runs on your machine. Your voice samples never leave your device.

---

## Platforms

| Platform | Folder | Download |
|---|---|---|
| macOS (Apple Silicon) | [`mac/`](mac/) | **[MossTTS-1.0.dmg](https://github.com/xirtus/MOSSlanding/releases/latest)** |
| Linux (NVIDIA GPU) | [`linux/`](linux/) | **[Install Guide](linux/#quick-start)** |
| Windows (NVIDIA GPU) | [`windows/`](windows/) | **[Install Guide](windows/#quick-start)** |

---

## macOS — Install in 60 seconds -- or use DMG

```bash
# 1. Download + drag MossTTS.app to /Applications
# 2. One-time setup:
cd ~/Projects/Mosslanding/mac && bash setup.sh

# 3. Launch — appears in your menu bar instantly
```

Or build from source:
```bash
git clone https://github.com/xirtus/MOSSlanding
cd MOSSlanding/mac
bash setup.sh   # installs Python deps
bash build.sh   # compiles the Swift app
open MossTTS.app
```

**Requirements:** macOS 13+, Apple Silicon, 16 GB RAM, Python 3.10+

---

## Linux — Install in 60 seconds

```bash
git clone https://github.com/xirtus/MOSSlanding
cd MOSSlanding/linux
./install.sh
```

Then launch from your app menu (search "Mosslanding") or terminal:

```bash
mosslanding
```

**Requirements:** Linux (KDE/GNOME/Qt), NVIDIA GPU 8GB+ VRAM (RTX 2070+), Python 3.10+

See [`linux/README.md`](linux/README.md) for manual install and AppImage build instructions.

---

## Windows — Install in 60 seconds

```powershell
git clone https://github.com/xirtus/MOSSlanding
cd MOSSlanding\windows
powershell -ExecutionPolicy Bypass -File install.ps1
```

Then double-click `run.bat` or search "Mosslanding" in the Start Menu.

**Requirements:** Windows 10/11, NVIDIA GPU 8GB+ VRAM (RTX 2070+), Python 3.10+

See [`windows/README.md`](windows/README.md) for manual install and troubleshooting.

---

## Built on MOSS-TTS

This app is a native macOS / Linux / Windows launcher for the [MOSS-TTS family](https://github.com/OpenMOSS/MOSS-TTS) by OpenMOSS — a state-of-the-art open-source TTS system that outperforms closed-source models like Doubao and Gemini 2.5 Pro in subjective evaluations.

---

<div align="center">
<sub>Free. Open source. No accounts. No limits.</sub>
</div>
