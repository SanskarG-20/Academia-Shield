@echo off
echo ===================================================
echo Academia Shield Agent - Windows Automated Installer
echo ===================================================

:: Check for Administrator privileges (required to set up a scheduled task)
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Administrator privileges confirmed.
) else (
    echo [ERROR] This installer must be run as Administrator.
    echo Please right-click this file and select "Run as administrator".
    pause
    exit /b 1
)

echo.
echo [1/3] Installing compilation tools (PyInstaller)...
pip install pyinstaller

echo.
echo [2/3] Compiling the Python script into a hidden background executable...
:: --noconsole prevents the black terminal window from showing up
:: --onefile packages everything into a single .exe
pyinstaller --noconfirm --noconsole --onefile agent.py

if not exist "dist\agent.exe" (
    echo [ERROR] Failed to compile agent.exe. Please check if Python is installed correctly.
    pause
    exit /b 1
)

echo.
echo [3/3] Installing to System and creating Startup Task...
:: Create a dedicated folder in Program Files
mkdir "C:\Program Files\AcademiaShield" 2>nul
copy /y "dist\agent.exe" "C:\Program Files\AcademiaShield\agent.exe"

:: Create a scheduled task that runs as the SYSTEM user on system startup with highest (Admin) privileges
schtasks /create /tn "AcademiaShieldAgent" /tr "\"C:\Program Files\AcademiaShield\agent.exe\"" /sc onstart /ru SYSTEM /rl highest /f

echo.
echo ===================================================
echo SUCCESS! Installation Complete.
echo ===================================================
echo The Academia Shield agent is now permanently installed.
echo It will start completely invisibly in the background 
echo every time this computer boots up.
echo.
echo Starting the agent right now so you don't have to restart...
start "" "C:\Program Files\AcademiaShield\agent.exe"
echo.
pause
