
@echo off
:: ============================================================
:: Academia Shield Agent — Windows Admin Launcher
:: 
:: Automatically re-launches itself as Administrator so the agent
:: can modify the hosts file for domain blocking.
::
:: Usage:
::   Double-click this file  — auto-elevates to Admin and runs agent
::   Or from terminal:        run_agent_admin.bat [enroll|run|status|logout]
:: ============================================================

:: Check if already running as Administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :run_agent
) else (
    echo [*] Requesting Administrator privileges...
    goto :elevate
)

:elevate
:: Re-launch self as admin using PowerShell UAC prompt
set "CMD_ARG=%~1"
if "%CMD_ARG%"=="" set "CMD_ARG=run"
powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList '%CMD_ARG%' -Verb RunAs"
exit /b

:run_agent
echo ============================================================
echo  ACADEMIA SHIELD AGENT  ^(Running as Administrator^)
echo ============================================================

:: Move to the agent directory
cd /d "%~dp0"

:: Load dev environment variables
set NODE_ENV=development
if exist ".env.development" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env.development") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

:: Override API_URL to correct port
set API_URL=http://127.0.0.1:8000

echo [+] Backend API: %API_URL%
echo [+] Enforcement: HOSTS (modifying C:\Windows\System32\drivers\etc\hosts)
echo [+] Admin:       YES - host file writes will succeed

:: Unlock hosts file permissions for current and future standard runs
attrib -R "%SystemRoot%\System32\drivers\etc\hosts" >nul 2>&1
icacls "%SystemRoot%\System32\drivers\etc\hosts" /grant "BUILTIN\Users:(M)" "Users:(M)" >nul 2>&1
echo.

set "PYTHON_EXE=python"
if exist "..\.venv\Scripts\python.exe" set "PYTHON_EXE=..\.venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

set "AGENT_CMD=%~1"
if "%AGENT_CMD%"=="" set "AGENT_CMD=run"

if "%AGENT_CMD%"=="run" (
    echo [*] Starting agent with command: run --enable-dns-adapter
    "%PYTHON_EXE%" agent.py run --enable-dns-adapter
) else (
    echo [*] Starting agent with command: %AGENT_CMD%
    "%PYTHON_EXE%" agent.py %AGENT_CMD%
)

if errorlevel 1 (
    echo.
    echo [ERROR] Agent exited with an error. Check agent.log for details.
) else (
    echo.
    echo [*] Agent stopped.
)

:: Safety guarantee: ensure all network adapters, hosts, and USB are cleanly unblocked
echo [*] Performing safety internet and USB restoration...
"%PYTHON_EXE%" -c "import os, sys; sys.path.insert(0, r'%~dp0'); from agent.platform import WindowsDNSAdapterManager, HostsEnforcementEngine, USBComplianceManager; [m.restore_rules() for m in [HostsEnforcementEngine()] if m]; [d.restore_original_dns() for d in [WindowsDNSAdapterManager()] if d]; [d.clean_stale_dns() for d in [WindowsDNSAdapterManager()] if d]; [u.restore_usb_storage_access() for u in [USBComplianceManager()] if u]" >nul 2>&1
echo [+] System restored to standard baseline.
pause
