@REM Academia Shield Agent — Windows Service Installer
@REM Installs the agent as a Windows Service that runs on startup

@echo off
setlocal enabledelayedexpansion

REM Check if running as administrator
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This script must be run as Administrator
    echo Please right-click and select "Run as administrator"
    pause
    exit /b 1
)

set INSTALL_DIR=C:\Program Files\AcademiaShield
set SERVICE_NAME=AcademiaShield
set AGENT_EXE=%INSTALL_DIR%\agent.exe

echo [*] Academia Shield Agent — Windows Service Installer
echo.

REM Create installation directory
if not exist "%INSTALL_DIR%" (
    echo [*] Creating installation directory: %INSTALL_DIR%
    mkdir "%INSTALL_DIR%"
)

REM Copy agent executable
if exist "dist\AcademiaShield.exe" (
    echo [*] Copying agent executable...
    copy "dist\AcademiaShield.exe" "%AGENT_EXE%"
) else (
    echo [ERROR] dist\AcademiaShield.exe not found
    echo [*] Run build_windows.bat first
    pause
    exit /b 1
)

REM Copy configuration
if exist ".env.production" (
    echo [*] Copying .env.production...
    copy ".env.production" "%INSTALL_DIR%\.env"
) else (
    echo [WARNING] .env.production not found
)

REM Install NSSM (Non-Sucking Service Manager) if needed
if not exist "%INSTALL_DIR%\nssm.exe" (
    echo [*] Downloading NSSM service manager...
    REM Option: Download and unzip NSSM
    REM For now, assume user has nssm in PATH or will download manually
    echo [!] Please install NSSM from: https://nssm.cc/
    echo [!] And add it to PATH, or place nssm.exe in %INSTALL_DIR%
)

REM Install service using NSSM
echo [*] Installing Windows Service...
nssm install %SERVICE_NAME% "%AGENT_EXE%"

if errorlevel 1 (
    echo [ERROR] Failed to install service
    pause
    exit /b 1
)

REM Configure service to start automatically
echo [*] Configuring service startup...
nssm set %SERVICE_NAME% AppDirectory "%INSTALL_DIR%"
nssm set %SERVICE_NAME% AppStdout "%INSTALL_DIR%\agent.log"
nssm set %SERVICE_NAME% AppStderr "%INSTALL_DIR%\agent.log"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START

REM Start the service
echo [*] Starting service...
nssm start %SERVICE_NAME%

echo.
echo [SUCCESS] Academia Shield Agent installed as Windows Service!
echo.
echo [*] Service Details:
echo     Name: %SERVICE_NAME%
echo     Executable: %AGENT_EXE%
echo     Config: %INSTALL_DIR%\.env
echo     Logs: %INSTALL_DIR%\agent.log
echo.
echo [*] To check status:
echo     nssm status %SERVICE_NAME%
echo.
echo [*] To stop service:
echo     nssm stop %SERVICE_NAME%
echo.
echo [*] To uninstall service:
echo     nssm remove %SERVICE_NAME% confirm
echo.

pause
