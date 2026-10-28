@echo off
:: Academia Shield Windows Uninstaller Script
:: Restores DNS settings, stops and deletes service, and purges credentials.
echo [Academia Shield] Initiating uninstallation and policy restoration...

:: 1. Revert DNS and cleanup via CLI
python -m agent.cli disable-enforcement
python -m agent.cli uninstall

:: 2. Stop and remove Windows Service
sc.exe stop AcademiaShieldService >nul 2>&1
sc.exe delete AcademiaShieldService >nul 2>&1

echo [Academia Shield] Agent uninstalled cleanly. Original system settings restored.
pause
