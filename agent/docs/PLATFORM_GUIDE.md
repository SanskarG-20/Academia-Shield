# Platform Guide: Windows & macOS

This guide covers building, signing, deploying, and running Academia Shield Local Agent on **Microsoft Windows** and **Apple macOS**.

---

## 1. Windows Platform Guide

### Requirements & Capabilities
- **Supported OS**: Windows 10 (1909+) & Windows 11 (x64 / ARM64).
- **Secure Storage**: Windows Credential Manager (`keyring`) with DPAPI fallback.
- **Process Monitoring**: `psutil`-based monitor with strict safety whitelisting (never kills system, accessibility, or security processes).
- **DNS Redirection**: Local DNS proxy on `127.0.0.1:5353`. Configured via `netsh` only after resolver health checks pass. Full pre-enforcement backup and restoration.
- **Compliance Reporting**: Windows App Control (WDAC), Microsoft Edge Enterprise Policy registry audit, and USB storage policy (`USBSTOR`).

### Production Packaging & Authenticode Signing
1. **PyInstaller Binary**:
   ```cmd
   python -m PyInstaller --onefile --name AcademiaShieldAgent agent/main.py
   ```
2. **Authenticode Digital Signing**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File agent/installers/windows/sign_authenticode.ps1 `
       -FilePath "dist\AcademiaShieldAgent.exe" `
       -CertificateThumbprint "<YOUR_AUTHENTICODE_THUMBPRINT>"
   ```
3. **MSI Installer (WiX Toolset)**:
   ```cmd
   candle.exe agent/installers/windows/AcademiaShieldAgent.wxs -dDistDir=dist
   light.exe AcademiaShieldAgent.wixobj -o dist/AcademiaShieldAgent.msi
   ```

---

## 2. macOS Platform Guide

### Requirements & Capabilities
- **Supported OS**: macOS 12 (Monterey), macOS 13 (Ventura), macOS 14 (Sonoma), macOS 15 (Sequoia).
- **Secure Storage**: macOS Keychain Services via `keyring` / `/usr/bin/security`.
- **Process Monitoring**: **Audit / Warn Mode Only**. Personal device privacy is respected; system and accessibility applications (`VoiceOver`, `WindowServer`, `Finder`) are protected.
- **DNS Redirection**: Managed via `/usr/sbin/networksetup` with pre-enforcement service backup.
- **Enterprise Controls**: Apple Network Extension Content Filter (`FilterDataProvider.swift`) and MDM Configuration Profiles (`com.apple.MCX`).

### Developer ID Signing, Hardened Runtime & Notarization
1. **Developer ID Signing**:
   ```bash
   bash agent/installers/macos/sign_notarize_macos.sh dist/AcademiaShieldAgent.app
   ```
2. **Build Signed .pkg Installer**:
   ```bash
   bash agent/installers/macos/build_pkg.sh
   ```
3. **launchd Service**:
   Installed into `~/Library/LaunchAgents/org.academiashield.agent.plist`.

---

## 3. CLI Quick Reference

```bash
# Check agent state and platform diagnostics
python -m agent.cli status
python -m agent.cli diagnostics

# Student authentication and device enrollment
python -m agent.cli login --email student@university.edu --password SecurePassword123
python -m agent.cli enroll

# Join scheduled examination session
python -m agent.cli join-session --session-id <SESSION_UUID>

# Leave session and cleanly restore network settings
python -m agent.cli leave-session

# Manual disable / emergency restoration
python -m agent.cli disable-enforcement

# Clean uninstallation
python -m agent.cli uninstall --purge
```
