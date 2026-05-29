@echo off
title Mosslanding
cd /d "%~dp0"

echo.
echo Starting Mosslanding...
echo.

REM Ensure venv exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo Please run install.ps1 first:
    echo   powershell -ExecutionPolicy Bypass -File install.ps1
    echo.
    pause
    exit /b 1
)

REM Activate venv and launch
call .\venv\Scripts\activate.bat
python -m src.main

REM If python exits with an error, show it
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Mosslanding exited with code %ERRORLEVEL%
    pause
)
