# 🪟 Mosslanding Windows Port — Handoff Document

**Date:** 2026-05-29
**Status:** Linux  ✅ complete · macOS  ✅ complete · Windows ⬜ planned

---

## Current State

The app is a **PySide6 desktop application** at `linux/src/`. It uses:
- `glass_window.py` — frameless window with theme detection
- `tts_panel.py` — voice cloning UI
- `voice_gen_panel.py` — voice design UI
- `settings_panel.py` — model manager + GPU monitor
- `backend.py` — MOSS-TTS HuggingFace pipeline

The Linux version detects KDE colors via `kreadconfig6`. The macOS version (`mac/`) is a separate SwiftUI app with a Python backend server.

---

## Windows Port Plan

### Architecture: Same as Linux

```
windows/
├── install.ps1                  ← PowerShell setup script
├── run.bat                      ← Double-click launcher
├── requirements.txt             ← Same as linux/
├── assets/
│   └── icons/
│       └── mosslanding.ico      ← Windows icon (convert from SVG)
└── src/
    ├── main.py                  ← Same
    ├── app.py                   ← 3-line change (theme detection)
    ├── backend.py               ← Same
    ├── widgets/
    │   ├── glass_window.py      ← ~20 lines changed (DWM shadow + Windows colors)
    │   ├── tts_panel.py         ← Same
    │   ├── voice_gen_panel.py   ← Same
    │   └── settings_panel.py    ← Same
    └── styles/
        └── theme.py             ← Same
```

### File Changes (Detailed)

#### 1. `glass_window.py` — ~20 lines to change

**Remove:**
- `kreadconfig6` subprocess calls
- `detect_kde_colors()` function
- `_kde_rgb_to_hex()` function

**Replace with:**

```python
import ctypes
from ctypes import wintypes

def detect_windows_theme() -> dict:
    """Read Windows dark/light mode from registry."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        use_light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        is_dark = (use_light == 0)
    except Exception:
        is_dark = True  # default dark

    if is_dark:
        return {
            "window_bg": "#1c1c1e",
            "window_fg": "#e8e8ec",
            "view_bg":   "#252528",
            "view_fg":   "#e8e8ec",
            "button_bg": "#333338",
            "button_fg": "#e8e8ec",
            "accent":    "#0d9488",
            "accent_fg": "#ffffff",
            "hover_bg":  "#3d3d42",
        }
    else:
        return {
            "window_bg": "#e8e8ec",
            "window_fg": "#1b1b1e",
            "view_bg":   "#f4f4f8",
            "view_fg":   "#1b1b1e",
            "button_bg": "#e0e0e5",
            "button_fg": "#1b1b1e",
            "accent":    "#0d9488",
            "accent_fg": "#ffffff",
            "hover_bg":  "#d4d4d9",
        }
```

**For DWM shadow (frameless window gets proper shadow on Windows):**

```python
# In GlassWindow.__init__, after setting window flags:
if sys.platform == "win32":
    # Enable DWM extended frame for shadow + resize
    hwnd = int(self.winId())
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 1
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
```

**Replace** `detect_kde_colors()` calls with `detect_windows_theme()`.

#### 2. `app.py` — 3 lines to change

Replace:
```python
from src.widgets.glass_window import GlassWindow
```

With:
```python
from src.widgets.glass_window import GlassWindow  # same import, different internals
```

(No actual code change needed — just make sure `glass_window.py` works on Windows.)

#### 3. `backend.py` — No changes

PyTorch + CUDA work identically on Windows. The `gpu_info()` function already uses `torch.cuda.get_device_properties()` which is platform-agnostic.

#### 4. New: `install.ps1`

```powershell
# Mosslanding Windows Installer
Write-Host "Mosslanding — Windows Installer" -ForegroundColor Cyan

# Check Python
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
Write-Host "Python: $(python --version)"

# Create venv
if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "venv created" -ForegroundColor Green
}

# Activate and install
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install torch==2.9.1+cu128 torchaudio==2.9.1+cu128 --index-url https://download.pytorch.org/whl/cu128
pip install transformers==5.0.0 accelerate safetensors numpy orjson PyYAML einops tiktoken tqdm psutil packaging ninja librosa soundfile scipy pydantic PySide6

# Create Start Menu shortcut
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Mosslanding.lnk")
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-Command `"cd '$PWD'; .\venv\Scripts\Activate.ps1; python -m src.main`""
$Shortcut.IconLocation = "$PWD\assets\icons\mosslanding.ico"
$Shortcut.Save()

Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "Launch from Start Menu: Mosslanding"
```

#### 5. New: `run.bat`

```batch
@echo off
cd /d "%~dp0"
call .\venv\Scripts\activate.bat
python -m src.main
pause
```

#### 6. New: `mosslanding.ico`

Generate from `mosslanding.svg` using:
```python
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
# Render SVG at 256x256, save as .ico
```

### Files That Stay Identical (copy directly from `linux/src/`)

| File | Reason |
|------|--------|
| `backend.py` | Pure PyTorch/HuggingFace — platform agnostic |
| `tts_panel.py` | Pure PySide6 widgets |
| `voice_gen_panel.py` | Pure PySide6 widgets |
| `settings_panel.py` | Pure PySide6 + PyTorch queries |
| `theme.py` | Design tokens only — no platform code |
| `main.py` | Just imports and runs app |
| `requirements.txt` | Same packages on Windows (PyTorch has Windows CUDA wheels) |

### Repo Structure After

```
MOSSlanding/
├── README.md
├── linux/           ← Done ✅
├── mac/             ← Done ✅
├── windows/         ← Build this
│   ├── install.ps1
│   ├── run.bat
│   ├── mosslanding.ico
│   ├── requirements.txt
│   ├── assets/icons/...
│   └── src/
│       ├── main.py
│       ├── app.py
│       ├── backend.py
│       ├── widgets/
│       │   ├── glass_window.py     ← Modified: Windows theme + DWM
│       │   ├── tts_panel.py        ← Identical
│       │   ├── voice_gen_panel.py  ← Identical
│       │   └── settings_panel.py   ← Identical
│       └── styles/
│           └── theme.py            ← Identical
└── appimage/
    └── build.sh
```

### Estimated Time

| Task | Minutes |
|------|---------|
| Copy shared files from `linux/src/` | 5 |
| Modify `glass_window.py` (theme + DWM) | 20 |
| Create `install.ps1` | 15 |
| Create `run.bat` | 5 |
| Generate `.ico` from SVG | 5 |
| Test on Windows VM/physical | 20 |
| Commit + push + update README | 10 |
| **Total** | **~80 min** |

### Notes

- Windows CUDA is slightly different from Linux — use PyTorch `cu128` index URL (same as Linux)
- Flash Attention 2 has limited Windows support — SDPA fallback works fine on RTX 3070
- Windows Defender may flag `pip install` of large packages — user may need to allow
- Python's `os.tempdir` already returns correct path on Windows for audio playback temp files
- The `QMediaPlayer` backend on Windows uses Windows Media Foundation — works out of box

---

## Prompt for Next Session

Copy-paste this into a new Claude session:

```
I'm continuing work on the MOSSlanding project at /home/xirtus_arch/Projects/Mosslanding/release/.
The repo is at https://github.com/xirtus/MOSSlanding with linux/ and mac/ folders already complete.

Read HANDOFF_WINDOWS.md in the repo root for the full plan.

I need you to:
1. Create the windows/ folder with a complete Windows port of the Linux PySide6 app
2. The only file that needs code changes is glass_window.py — replace KDE color
   detection with Windows registry dark/light mode detection + DWM shadow for frameless window
3. All other .py files are identical to linux/src/ — copy them directly
4. Create install.ps1 (PowerShell one-command setup), run.bat (double-click launcher)
5. Generate mosslanding.ico from the SVG icon in linux/assets/icons/
6. Update README.md to show Windows as available (not "coming soon")
7. Commit and push to GitHub

The Linux source is in linux/src/. The vendor comparison table in README.md should
get a Windows column too.
```
