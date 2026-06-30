@echo off
echo ===================================================
echo Academia Shield Agent - Windows Service Installer
echo ===================================================

:: Check for Administrator privileges
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
echo [1/3] Installing dependencies...
pip install pyinstaller pywin32 python-socketio[client]

:: Run PyWin32 post-install script just in case
python -c "from win32com.server.register import UseCommandLine; UseCommandLine()" >nul 2>&1

echo.
echo [2/3] Compiling Windows Service executable...
:: Compile the service wrapper. We need hidden imports for pywin32 to work compiled.
pyinstaller --noconfirm --hidden-import win32timezone --hidden-import servicemanager --hidden-import win32serviceutil --hidden-import win32service --hidden-import win32event --onefile service\windows_service.py

if not exist "dist\windows_service.exe" (
    echo [ERROR] Failed to compile windows_service.exe.
    pause
    exit /b 1
)

echo.
echo [3/3] Installing and starting the Windows Service...
mkdir "C:\Program Files\AcademiaShield" 2>nul

:: Stop and remove old service if it exists
"C:\Program Files\AcademiaShield\windows_service.exe" stop >nul 2>&1
"C:\Program Files\AcademiaShield\windows_service.exe" remove >nul 2>&1
:: Also remove the old scheduled task if upgrading from prototype
schtasks /delete /tn "AcademiaShieldAgent" /f >nul 2>&1

:: Copy the new executable
copy /y "dist\windows_service.exe" "C:\Program Files\AcademiaShield\windows_service.exe"

:: Install and start the new service
"C:\Program Files\AcademiaShield\windows_service.exe" install
"C:\Program Files\AcademiaShield\windows_service.exe" start

:: Set recovery options (restart service on failure)
sc failure AcademiaShieldAgent reset= 86400 actions= restart/60000/restart/60000/restart/60000

echo.
echo ===================================================
echo SUCCESS! Installation Complete.
echo ===================================================
echo The Academia Shield agent is now running as a permanent Windows Service.
echo It will run automatically in the background on system boot.
echo.
echo You can check the logs at: C:\Program Files\AcademiaShield\agent.log
echo.
pause
