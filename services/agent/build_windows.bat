@echo off
REM Academia Shield Agent — Windows Build Script
REM Bundles the Python agent into a standalone .exe for distribution

setlocal enabledelayedexpansion

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    exit /b 1
)

echo [*] Academia Shield Agent — Windows Build
echo [*] Installing PyInstaller...
pip install pyinstaller

echo [*] Building agent.exe...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "AcademiaShield" ^
    --icon=icon.ico ^
    --add-data ".env.production;." ^
    agent.py

if errorlevel 1 (
    echo [ERROR] Build failed
    exit /b 1
)

echo [*] Build complete!
echo [*] Output: dist/AcademiaShield.exe
echo.
echo [*] To create Windows Service, run:
echo     call install_windows.bat
