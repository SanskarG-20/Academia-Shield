# Academia Shield Windows Local Agent & Installer Guide

## Overview

**Academia Shield** is a consent-based academic network governance and exam integrity agent for Windows.
The desktop agent is packaged as a single standalone installer executable:

```
dist/
  AcademiaShieldInstaller.exe
  AcademiaShieldInstaller.exe.sha256
  release-manifest.json
  release-manifest.sig
```

A student downloads this single EXE, explicitly approves installation, enrolls their device, and enters an active class session.
The agent activates website and application blocking **strictly when the student joins an active session started by their professor**, and **immediately restores all system settings when the session ends or student leaves**.

---

## 1. Security & Privacy Guarantees

| Security Pillar | Architectural Implementation |
|---|---|
| **Zero Hidden Persistence** | No hidden users, no hidden scheduled tasks, no stealth folders, no kernel drivers. |
| **No Inbound Connections** | Professors never directly connect to student laptops. All connections are outbound HTTPS/WebSocket to the Academia Shield backend. |
| **Consent Gate** | Clear privacy disclosure presented before installation; explicit user/admin approval required. |
| **Cryptographic Policy Verification** | Every policy payload is verified against the backend's Ed25519 public key and SHA-256 canonical hash. |
| **Protected Process Safety** | Windows Explorer, system services, security tools, and accessibility utilities (`osk.exe`, `narrator.exe`, `magnify.exe`) are permanently protected. |
| **Guaranteed Restoration** | Local DNS configuration is backed up prior to enforcement and automatically restored on session termination, policy expiry, student leave, or uninstall. |
| **Privacy Minimized** | No keystroke logging, no screen captures, no browser history scraping, and no memory inspection. |

---

## 2. Release Build Pipeline

### Prerequisites
- Python 3.10+ on Windows x64 or ARM64
- PyInstaller (`pip install pyinstaller`)
- Cryptography & psutil (`pip install cryptography psutil`)

### Building the Single-File Installer
Run the release build pipeline script:

```powershell
# Run from repository root
python agent/build_installer.py
```

Or via root helper:
```powershell
python scripts/build_release.py
```

### Build Pipeline Output
The pipeline produces 4 release artifacts:
1. `dist/AcademiaShieldInstaller.exe`: Standalone self-contained Windows executable bundling the agent daemon, GUI status app, CLI, DNS resolver, and policy engine.
2. `dist/AcademiaShieldInstaller.exe.sha256`: SHA-256 checksum for distribution integrity verification.
3. `dist/release-manifest.json`: Signed release metadata specifying version, platform, download URL, package hash, and OS compatibility.
4. `dist/release-manifest.sig`: Ed25519 digital signature over the release manifest.

The pipeline automatically synchronizes these files to `backend/installers/windows/` so that web clients can download the installer immediately.

---

## 3. Installation & Device Enrollment

### Interactive Graphical Setup
1. Double-click `AcademiaShieldInstaller.exe`.
2. Review the privacy notice and requested permissions.
3. Choose the install path (default: `C:\Program Files\AcademiaShield` if Admin, or `%LOCALAPPDATA%\AcademiaShield` for standard users).
4. Click **Approve & Install**.
5. Once complete, the **Sign In / Enroll Device** screen opens automatically.
6. Enter the **8-Character Enrollment Token** generated from the Student Dashboard (or log in with student email & password).
7. The agent generates a local Ed25519 keypair, registers the device with the backend, stores the session token in Windows Credential Manager / DPAPI, and enters `ENROLLED_IDLE` state.

### Command-Line / Unattended Setup
```powershell
# Silent install with automatic consent
AcademiaShieldInstaller.exe --yes --dir "C:\Program Files\AcademiaShield"

# Install and enroll immediately using single-use website token
AcademiaShieldInstaller.exe --yes --token "A1B2C3D4" --url "http://127.0.0.1:5000"

# Command-line status inspection
AcademiaShield.exe status

# Clean uninstallation and baseline recovery
AcademiaShieldInstaller.exe --uninstall --yes
```

---

## 4. Local Testing Procedure (Notepad & DNS Blocking)

To verify website and application blocking safely in a local environment:

### Step 1: Start Backend & Frontend
```powershell
# Terminal 1: Start Backend API
cd backend
python -m uvicorn app.main:app --port 5000 --reload

# Terminal 2: Start Frontend Web UI
cd frontend
npm run dev
```

### Step 2: Create a Batch Session with Policy Rules
1. Log in to the Academia Shield Professor Dashboard (`http://localhost:5173`).
2. Create a Batch (e.g. `CS-101`) and add a Session Rule:
   - **Application Rule**: `notepad.exe` -> Action: `Warn` or `Close`
   - **Website Rule**: `gaming.com` / `youtube.com` -> Action: `Block`
3. Start the Session in the Professor Dashboard.

### Step 3: Student Joins Session
1. In the Student Dashboard (`http://localhost:5173/student`), click **Device Protection Agent**.
2. Click **Generate Enrollment Token** and pair the local agent.
3. Click **Join Session**.
4. The Agent state transitions: `ENROLLED_IDLE` -> `POLICY_RECEIVED` -> `ENFORCING`.

### Step 4: Verify Enforcement
1. **Application Rule Test**: Launch `notepad.exe`.
   - The agent detects `notepad.exe`.
   - In `warn` mode, a visible desktop notification is displayed.
   - In `close` mode, a visible warning is issued and the application is terminated after the grace period.
2. **Protected App Safety Test**: Launch Windows Explorer or task manager. Notice they are permanently protected and never closed.
3. **DNS Rule Test**: Run `nslookup gaming.com 127.0.0.1 -port=5353`. The resolver returns `NXDOMAIN` and emits `dns_blocked` telemetry.
4. **End Session Test**: Professor clicks **End Session**.
   - Agent state machine transitions: `ENFORCING` -> `RESTORING` -> `ENROLLED_IDLE`.
   - DNS settings and application permissions return to baseline unrestricted status.

---

## 5. Signed Production Release Process

For official institutional deployments:

1. **Authenticode Code Signing**:
   - Install institutional Code Signing Certificate into Windows Certificate Store (`Cert:\CurrentUser\My`) or specify Hardware Security Module (HSM) token.
   - The build pipeline automatically signs `AcademiaShieldInstaller.exe` using timestamped Authenticode signatures via Digicert / Sectigo timestamp authority.

2. **Backend Ed25519 Signing Key**:
   - Set `RELEASE_SIGNING_PRIVATE_KEY` in `backend/.env`.
   - Public key is published via `GET /api/v1/agent/verification-key` and embedded in the agent binary.

3. **Verify Integrity Before Distribution**:
   ```powershell
   # Verify SHA-256 hash matches
   Get-FileHash -Algorithm SHA256 dist\AcademiaShieldInstaller.exe
   Get-Content dist\AcademiaShieldInstaller.exe.sha256
   ```

---

## 6. Backend Environment Variables

| Variable | Description | Default |
|---|---|---|
| `CURRENT_AGENT_VERSION` | Current desktop agent release version | `2.3.0` |
| `WINDOWS_MIN_OS` | Minimum required Windows build | `Windows 10 Build 19041+` |
| `PUBLIC_BASE_URL` | Public server URL for installer downloads | `http://127.0.0.1:5000` |
| `RELEASE_SIGNING_PRIVATE_KEY` | Hex-encoded Ed25519 private key for signing manifests | Generated from `JWT_SECRET` if empty |
| `JWT_SECRET` | Cryptographic secret for server tokens | Required in production |

---

## 7. College MDM Requirements for Strict USB Controls

Academia Shield **does not install custom kernel-mode drivers** on personal student laptops.
For strict removable-storage restrictions:

- **Personal Student Laptops**:
  - The Agent audits registry compliance (`USBSTOR` service start value).
  - Reports status as `Personal Device (Standard)`.
  - Displays: *"USB restriction requires college-managed device policy."*

- **College-Managed Lab Computers**:
  - Removable USB storage is restricted through Microsoft Intune / Group Policy Object (GPO) with `HKLM\SYSTEM\CurrentControlSet\Services\USBSTOR\Start = 4` or Windows App Control (WDAC).
  - The Agent verifies and reports active hardware compliance directly to the Professor Live Monitor.
