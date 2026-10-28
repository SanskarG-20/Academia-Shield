# Academia Shield Managed Device & Enterprise Deployment Guide

## 1. Overview
This guide provides institutional IT administrators with standard procedures for deploying Academia Shield Student Agents across school-managed computer labs, 1:1 student laptops, and BYOD environments using Microsoft Intune, Group Policy (GPO), or standalone signed installers.

---

## 2. Deployment Architecture Options

### Option A: Microsoft Intune (MDM Deployment)
1. **Package Win32 App**:
   Use Microsoft Win32 Content Prep Tool (`IntuneWinAppUtil.exe`) to package `AcademiaShieldSetup.exe`.
2. **Install Command**:
   ```cmd
   AcademiaShieldSetup.exe /silent /institution="YourSchool" /enrollment_server="https://academiashield.school.edu"
   ```
3. **Uninstall Command**:
   ```cmd
   "C:\Program Files\AcademiaShield\unins000.exe" /silent
   ```
4. **Detection Rule**:
   - File Path: `C:\Program Files\AcademiaShield\AcademiaShieldAgent.exe`
   - Registry Key: `HKLM\SOFTWARE\AcademiaShield\Installed = 1`

### Option B: Windows Active Directory Group Policy (GPO)
1. Place `AcademiaShieldSetup.msi` / executable in the domain SYSVOL share.
2. In GPMC, create a GPO linked to Student Computer Organizational Units (OU):
   - **Computer Configuration > Policies > Software Settings > Software installation**.
3. Deploy pre-configured registry keys under `HKLM\SOFTWARE\Policies\AcademiaShield`:
   - `EnrollmentServer` = `https://academiashield.school.edu`
   - `AllowUSBBlocking` = `1` (or `0` if school policy disallows USB restrictions)

### Option C: Standalone Interactive Student Installer
1. Students log in to the web portal (`https://academiashield.school.edu/student/session`).
2. Download `AcademiaShieldSetup.exe` with a 1-click single-use enrollment token.
3. The wizard registers the student endpoint Ed25519 public key and completes setup automatically.

---

## 3. Network & Firewall Prerequisites

The student endpoint agent requires outbound HTTPS and WebSocket access to the institutional server:

| Port | Protocol | Destination | Purpose |
| :--- | :--- | :--- | :--- |
| **443** | TCP (HTTPS) | `academiashield.school.edu` | REST API, Policy Sync, Heartbeat |
| **443** | TCP (WSS) | `academiashield.school.edu/socket.io` | Real-time policy delivery & live monitor |
| **53** | UDP/TCP | `127.0.0.1` | Local DNS filter engine (managed on-device) |

---

## 4. Uninstallation & Emergency Recovery

### Institutional Clean Unblock Script
If an emergency unblock is required without server access, IT administrators can run the included recovery tool:
```powershell
.\clean_unblock_all.bat
```
This script immediately:
1. Strips all managed rules from `C:\Windows\System32\drivers\etc\hosts`.
2. Resets network adapter DNS to DHCP / Automatic.
3. Restores `USBSTOR` service start setting to `3` and resets `RemovableStorageDevices\Deny_All` to `0`.
4. Flushes the Windows DNS cache.
