# PowerShell Authenticode Signing Script for Academia Shield Windows Distribution
param(
    [Parameter(Mandatory=$true)]
    [string]$FilePath,

    [Parameter(Mandatory=$false)]
    [string]$CertificateThumbprint,

    [Parameter(Mandatory=$false)]
    [string]$TimestampServer = "http://timestamp.digicert.com"
)

Write-Host "Authenticode Signing: $FilePath" -ForegroundColor Cyan

if (-not (Test-Path $FilePath)) {
    Write-Error "File not found: $FilePath"
    exit 1
}

# Calculate and display SHA-256 pre-signature hash
$sha256 = (Get-FileHash -Path $FilePath -Algorithm SHA256).Hash
Write-Host "File SHA-256: $sha256" -ForegroundColor Gray

if ($CertificateThumbprint) {
    Set-AuthenticodeSignature -FilePath $FilePath `
        -Certificate (Get-Item "Cert:\CurrentUser\My\$CertificateThumbprint") `
        -TimestampServer $TimestampServer `
        -HashAlgorithm "SHA256"
    
    $sig = Get-AuthenticodeSignature -FilePath $FilePath
    Write-Host "Signature Status: $($sig.Status)" -ForegroundColor Green
} else {
    Write-Warning "No CertificateThumbprint specified. Skipping live signature (Development Mode)."
}
