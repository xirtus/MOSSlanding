# 🔊 MOSSlanding

### The best voice-cloning TTS on the planet. Runs on your machine. Costs nothing.

> Clone any voice from a 5-second sample. Speak 31 languages. Zero cloud. Zero subscription. Zero compromise.

<div align="center">

**[⬇️ Download for macOS](https://github.com/xirtus/MOSSlanding/releases/latest)** &nbsp;·&nbsp; Linux coming soon

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
| **Apple Silicon native** | ✅ | — | — | — |

---

## What it can do

**🎤 Voice Cloning** — Drop in any 5–30 second audio clip and it instantly learns the voice. Accent, tone, cadence — all of it. Works on the first try.

**🌍 31 Languages** — English, Chinese, Japanese, French, Spanish, Arabic, Hindi, Korean and 23 more. Switch mid-sentence.

**🎯 Pinyin / IPA / Phoneme control** — Nail every pronunciation. Perfect for names, technical terms, multilingual scripts.

**⏸️ Explicit pause control** — `[pause 1.5s]` anywhere in your text. Precise timing, no guessing.

**⚡ Apple Silicon MPS** — Runs the full 1.7B model on M1/M2/M3 via Metal. No GPU required. No CUDA. Just your Mac.

**🔒 100% private** — The model runs on your machine. Your voice samples never leave your device.

---

## Platforms

| Platform | Folder | Download |
|---|---|---|
| macOS (Apple Silicon) | [`mac/`](mac/) | **[MossTTS-1.0.dmg](https://github.com/xirtus/MOSSlanding/releases/latest)** |
| Linux (NVIDIA / XPS 17) | [`linux/`](linux/) | 🔜 Coming soon |

---

## macOS — Install in 60 seconds

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

## Built on MOSS-TTS

This app is a native macOS/Linux launcher for the [MOSS-TTS family](https://github.com/OpenMOSS/MOSS-TTS) by OpenMOSS — a state-of-the-art open-source TTS system that outperforms closed-source models like Doubao and Gemini 2.5 Pro in subjective evaluations.

---

<div align="center">
<sub>Free. Open source. No accounts. No limits.</sub>
</div>
