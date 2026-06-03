# 🔊 MOSSlanding

### The best voice-cloning TTS on the planet. Runs on your machine. Costs nothing.

> Clone any voice from a 5-second sample. Speak 31 languages. Zero cloud. Zero subscription. Zero compromise.

<div align="center">

[![Linux](https://img.shields.io/badge/Linux-FCC624?logo=linux&logoColor=black)](#-linux)
[![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white)](#-macos)
[![Windows](https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white)](#-windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## 🚀 Quick Install

### Debian / Ubuntu (APT)

```bash
# One command:
curl -fsSL https://xirtus.github.io/MOSSlanding/install-apt.sh | sudo bash
mosslanding
```

Or manually:

```bash
wget https://github.com/xirtus/MOSSlanding/releases/latest/download/mosslanding_latest_amd64.deb
sudo dpkg -i mosslanding_latest_amd64.deb
mosslanding
```

### Arch Linux (Pacman)

```bash
# Option 1: Download from GitHub Releases
wget https://github.com/xirtus/MOSSlanding/releases/latest/download/mosslanding-1.0.0-1-x86_64.pkg.tar.zst
sudo pacman -U mosslanding-1.0.0-1-x86_64.pkg.tar.zst
mosslanding

# Option 2: Build from AUR (coming soon — PKGBUILD in packaging/arch/)
# git clone https://aur.archlinux.org/mosslanding.git
# cd mosslanding && makepkg -si
```

### macOS

```bash
# Download DMG from Releases
open https://github.com/xirtus/MOSSlanding/releases/latest
# Drag Mosslanding.app to /Applications
```

### Windows

```powershell
# Download and run installer from Releases
Invoke-WebRequest -Uri "https://github.com/xirtus/MOSSlanding/releases/latest/download/Mosslanding-Setup.exe" -OutFile "Mosslanding-Setup.exe"
.\Mosslanding-Setup.exe
```

---

## 📦 Package Formats

| Format | System | Install Command | Status |
|--------|--------|----------------|--------|
| `.deb` | Debian / Ubuntu / Mint / Pop!_OS | `sudo dpkg -i mosslanding_*.deb` | ✅ Available |
| `.pkg.tar.zst` | Arch Linux / Manjaro / EndeavourOS | `sudo pacman -U mosslanding-*.pkg.tar.zst` | ✅ Available |
| `.dmg` | macOS (Apple Silicon) | Download & drag to Applications | ✅ Available |
| `.exe` / `.ps1` | Windows 10/11 | Run installer | ✅ Available |
| `.AppImage` | Any Linux | Download & run | ✅ Available |
| APT Repo | Debian/Ubuntu | `sudo apt install mosslanding` | 🚧 Setup required |

---

## 🎯 Features

**🎤 Voice Cloning** — Drop in any 5–30 second audio clip and it instantly learns the voice. Accent, tone, cadence — all of it.

**🌍 31 Languages** — English, Chinese, Japanese, French, Spanish, Arabic, Hindi, Korean and 23 more. Switch mid-sentence.

**🎯 Pinyin / IPA / Phoneme control** — Nail every pronunciation. Perfect for names, technical terms, multilingual scripts.

**⏸️ Pause control** — `[pause 1.5s]` anywhere in your text. Precise timing.

**⚡ GPU Accelerated** — NVIDIA RTX 2070+ with bfloat16 precision. Apple Silicon via Metal MPS.

**🔒 100% Private** — Everything runs on your machine. Your voice samples never leave your device.

---

## 🖥️ Platforms

| Platform | GPU | Status |
|----------|-----|--------|
| Linux (Debian/Ubuntu) | NVIDIA RTX 2070+ | ✅ |
| Linux (Arch) | NVIDIA RTX 2070+ | ✅ |
| Linux (AppImage) | NVIDIA RTX 2070+ | ✅ |
| macOS (Apple Silicon) | M1/M2/M3/M4 | ✅ |
| Windows 10/11 | NVIDIA RTX 2070+ | ✅ |

**Requirements:** 8GB+ VRAM, 16GB system RAM, Python 3.10+

---

## 🔧 Build from Source

```bash
git clone https://github.com/xirtus/MOSSlanding
cd MOSSlanding

# Linux
cd release/linux && ./install.sh && mosslanding

# Build packages
cd release/packaging && ./build_all.sh
# Output in release/dist/
```

---

## 📁 Repository Structure

```
release/
├── linux/          # Linux app source + install scripts
├── mac/            # macOS SwiftUI app + DMG builder
├── windows/        # Windows app + PowerShell installer
├── appimage/       # AppImage builder
├── packaging/      # Native package builders
│   ├── arch/       # PKGBUILD for Arch Linux / pacman
│   ├── debian/     # DEBIAN/ control files for .deb
│   ├── apt-repo/   # APT repository generator + one-liner installer
│   └── build_all.sh # Build everything in one shot
└── dist/           # Built packages output
```

---

## 🏗️ Built on MOSS-TTS

This app is a native desktop launcher for the [MOSS-TTS family](https://github.com/OpenMOSS/MOSS-TTS) by OpenMOSS — state-of-the-art open-source TTS that outperforms closed-source models like Doubao and Gemini 2.5 Pro in subjective evaluations.

**Models used:**
- `OpenMOSS-Team/MOSS-TTS-v1.5` (~4-6 GB) — voice cloning & direct generation
- `OpenMOSS-Team/MOSS-VoiceGenerator` (~1-2 GB) — voice design from text descriptions
- `OpenMOSS-Team/MOSS-Audio-Tokenizer` (~1 GB) — audio encoding/decoding

---

## 🚢 Creating a Release

1. Push a version tag:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. GitHub Actions automatically builds `.deb` and `.pkg.tar.zst` and attaches them to the release.

3. (Optional) Deploy APT repo to GitHub Pages:
   ```bash
   cd release/packaging/apt-repo
   ./setup-repo.sh 1.0.0
   git checkout gh-pages
   cp -r repo/* .
   git add . && git commit -m "apt repo v1.0.0" && git push
   ```

4. (Optional) Submit PKGBUILD to AUR for `yay -S mosslanding` support.

---

<div align="center">
<sub>Free. Open source. No accounts. No limits.</sub>
</div>
