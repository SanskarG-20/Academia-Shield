@echo off
:: ============================================================
:: Academia Shield — Grant Hosts File Modify Permission
::
:: Configures write permissions on C:\Windows\System32\drivers\etc\hosts
:: for standard users, allowing Academia Shield agent to enforce
:: website blocklists without requiring elevation every time.
:: ============================================================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [*] Requesting Administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================================
echo  ACADEMIA SHIELD -- HOSTS FILE PERMISSION CONFIGURATOR
echo ============================================================
echo.
set "HOSTS_FILE=%SystemRoot%\System32\drivers\etc\hosts"

if not exist "%HOSTS_FILE%" (
    echo [!] Hosts file not found at %HOSTS_FILE%
    pause
    exit /b 1
)

echo [*] Removing Read-Only attribute...
attrib -R "%HOSTS_FILE%" 2>nul

echo [*] Granting Modify permissions to Users group...
icacls "%HOSTS_FILE%" /grant "BUILTIN\Users:(M)" /grant "Users:(M)" >nul 2>&1

if %errorLevel% equ 0 (
    echo.
    echo [OK] Permissions successfully granted!
    echo [OK] Standard user processes can now update the hosts file.
    echo [OK] Academia Shield agent website blocking is fully enabled.
) else (
    echo.
    echo [!] Warning: Failed to set permissions automatically.
)

echo.
echo Press any key to close this window...
pause >nul
