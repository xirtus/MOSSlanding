# Mosslanding — Windows Installer
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "=================================" -ForegroundColor DarkCyan
Write-Host "  Mosslanding — Windows Installer" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor DarkCyan
Write-Host ""

# ── Locate Python ──────────────────────────────────────

$python = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $v = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $python = $cmd
            break
        }
    } catch {}
}

if (-not $python) {
    Write-Host "ERROR: Python 3.10+ not found." -ForegroundColor Red
    Write-Host "Install from https://www.python.org/downloads/ (check 'Add to PATH')" -ForegroundColor Yellow
    exit 1
}

$pyVer = & $python --version 2>&1
Write-Host "[OK] $pyVer" -ForegroundColor Green

# ── Virtual environment ─────────────────────────────────

if (-not (Test-Path "venv")) {
    Write-Host ""
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    & $python -m venv venv
    Write-Host "[OK] venv created" -ForegroundColor Green
} else {
    Write-Host "[OK] venv already exists" -ForegroundColor Green
}

# ── Activate & install dependencies ─────────────────────

Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
. .\venv\Scripts\Activate.ps1

Write-Host "Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip --quiet

Write-Host ""
Write-Host "Installing PyTorch with CUDA support..." -ForegroundColor Cyan
python -m pip install torch==2.9.1+cu128 torchaudio==2.9.1+cu128 `
    --index-url https://download.pytorch.org/whl/cu128

Write-Host ""
Write-Host "Installing HuggingFace + audio libraries..." -ForegroundColor Cyan
python -m pip install transformers==5.0.0 accelerate safetensors numpy orjson PyYAML `
    einops tiktoken tqdm psutil packaging ninja librosa soundfile scipy pydantic PySide6

Write-Host ""
Write-Host "[OK] All dependencies installed" -ForegroundColor Green

# ── Create Start Menu shortcut ──────────────────────────

Write-Host ""
Write-Host "Creating Start Menu shortcut..." -ForegroundColor Cyan

$InstallDir = Get-Location
$StartMenu = [Environment]::GetFolderPath("StartMenu") + "\Programs\Mosslanding.lnk"

try {
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut($StartMenu)
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoLogo -Command `"cd '$InstallDir'; .\venv\Scripts\Activate.ps1; python -m src.main`""
    $Shortcut.IconLocation = "$InstallDir\assets\icons\mosslanding.ico"
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Save()
    Write-Host "[OK] Shortcut created: $StartMenu" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Could not create Start Menu shortcut: $_" -ForegroundColor Yellow
    Write-Host "You can still launch via run.bat or manually." -ForegroundColor Yellow
}

# ── Done ─────────────────────────────────────────────────

Write-Host ""
Write-Host "=================================" -ForegroundColor DarkCyan
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "To launch Mosslanding:" -ForegroundColor White
Write-Host "  1. Double-click run.bat" -ForegroundColor Cyan
Write-Host "  2. Or search 'Mosslanding' in the Start Menu" -ForegroundColor Cyan
Write-Host "  3. Or run:  .\run.bat  from this folder" -ForegroundColor Cyan
Write-Host ""
