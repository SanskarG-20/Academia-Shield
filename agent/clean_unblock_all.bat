@echo off
:: ============================================================
:: Academia Shield — Complete Unblock & Internet Restoration
:: ============================================================

net session >nul 2>&1
if %errorLevel% == 0 (
    goto :unblock
) else (
    echo [*] Requesting Administrator privileges to unblock websites and restore DNS...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:unblock
echo ============================================================
echo  1. CLEANING WINDOWS HOSTS FILE
echo ============================================================
python -c "import os; p=os.path.expandvars(r'%%SystemRoot%%\System32\drivers\etc\hosts'); (lambda: [open(p,'w',encoding='utf-8').writelines([l for l in open(p,'r',encoding='utf-8',errors='ignore').readlines() if not any(x in l for x in ['ACADEMIA SHIELD','youtube.com','facebook.com','instagram.com','reddit.com','chatgpt.com','openai.com'])]) if os.path.exists(p) else None])()" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$path = [Environment]::ExpandEnvironmentVariables('%%SystemRoot%%\System32\drivers\etc\hosts'); if (Test-Path $path) { Set-ItemProperty -Path $path -Name IsReadOnly -Value $false -ErrorAction SilentlyContinue; $lines = [System.IO.File]::ReadAllLines($path); $clean = New-Object System.Collections.Generic.List[string]; $skip = $false; foreach ($l in $lines) { if ($l -like '*ACADEMIA SHIELD MANAGED BLOCKLIST START*') { $skip = $true; continue }; if ($l -like '*ACADEMIA SHIELD MANAGED BLOCKLIST END*') { $skip = $false; continue }; if (-not $skip -and $l -notmatch 'youtube\.com|facebook\.com|instagram\.com|reddit\.com|chatgpt\.com|openai\.com|discord\.com|telegram\.org') { $clean.Add($l) } }; [System.IO.File]::WriteAllLines($path, $clean); Write-Host '[+] Hosts file cleaned successfully!' }"

echo.
echo ============================================================
echo  2. RESETTING WI-FI AND ETHERNET DNS TO DHCP / AUTOMATIC
echo ============================================================
netsh interface ipv4 set dnsservers name="Wi-Fi" source=dhcp
netsh interface ipv4 set dnsservers name="Ethernet" source=dhcp
powershell -NoProfile -Command "Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses -ErrorAction SilentlyContinue }"

echo.
echo ============================================================
echo  3. FLUSHING DNS RESOLVER CACHE
echo ============================================================
ipconfig /flushdns
powershell -NoProfile -Command "Clear-DnsClientCache -ErrorAction SilentlyContinue"

echo.
echo ============================================================
echo  4. RESTORING USB / PEN DRIVE STORAGE ACCESS
echo ============================================================
powershell -NoProfile -Command "Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\USBSTOR' -Name 'Start' -Value 3 -ErrorAction SilentlyContinue; Remove-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices' -Name 'Deny_All' -ErrorAction SilentlyContinue; Remove-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices' -Recurse -ErrorAction SilentlyContinue; Write-Host '[+] USB Removable Storage access restored to normal.'"

echo.
echo ============================================================
echo  [+] ALL WEBSITES UNBLOCKED, INTERNET & USB RESTORED!
echo ============================================================
echo.
pause
