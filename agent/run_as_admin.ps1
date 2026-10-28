# Academia Shield Agent — PowerShell Admin Runner
# RIGHT-CLICK THIS FILE and select "Run with PowerShell" or "Run as administrator"
# This will start the agent with full Administrator privileges for live hosts file blocking.

$AgentDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Not running as Administrator. Re-launching with UAC elevation..." -ForegroundColor Yellow
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell"
    $psi.Arguments = "-NoExit -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    $psi.Verb = "runas"
    $psi.WorkingDirectory = $AgentDir
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    exit
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ACADEMIA SHIELD AGENT (Administrator)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

Set-Location $AgentDir

# Set environment
$env:API_URL = "http://127.0.0.1:8000"
$env:ENFORCEMENT_MODE = "HOSTS"
$env:POLL_INTERVAL = "8"

Write-Host "[+] API URL:    $env:API_URL" -ForegroundColor Green
Write-Host "[+] Mode:       HOSTS (writes to C:\Windows\System32\drivers\etc\hosts)" -ForegroundColor Green
Write-Host "[+] Admin:      YES - live blocking enabled" -ForegroundColor Green
Write-Host ""
Write-Host "[*] Starting agent... Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

python agent.py run

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Agent crashed. Check agent.log for details." -ForegroundColor Red
    Read-Host "Press Enter to exit"
}
