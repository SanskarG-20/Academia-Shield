# Academia Shield — Windows Local Agent & Safe Enforcement System (v2.3.0)

Academia Shield Windows Local Agent is a production-grade, privacy-respecting client for personal test devices (Development Mode) and institution-managed Windows devices (Managed Mode).

It integrates with the authenticated backend (`/api/v1/agent/...`), batch memberships, student manual session join flow, signed active-policy API, real-time presence heartbeat, and idempotent telemetry pipeline.

---

## 🛡️ Safety & Privacy Guarantees

- **No Stealth or Invasive Behavior**: Zero keyloggers, zero screen captures, zero browser history scrapes, zero anti-debugging hacks, zero silent privilege escalations, and zero custom kernel drivers.
- **No Hidden Accounts or Services**: Operates transparently as a standard user process (or approved administrator task). Creates no hidden services or secret accounts.
- **Explicit Consent & Transparency**: Prompts with full permission disclosures before privileged configuration.
- **Protected System Processes**: Hardcoded allowlist protects Windows shell (`explorer.exe`), system processes (`svchost.exe`, `lsass.exe`, `csrss.exe`, `services.exe`, `winlogon.exe`, `taskmgr.exe`), security suites (`MsMpEng.exe`, `SecurityHealthService.exe`), accessibility tools (`magnify.exe`, `narrator.exe`, `osk.exe`), browser recovery tools, and Academia Shield itself (`agent.exe`, `python.exe`).
- **Safe Network & DNS Handling**: Never modifies `C:\Windows\System32\drivers\etc\hosts` or firewall rules. Backs up adapter DNS settings before modification and restores them on disable, session end, or uninstallation.
- **Secure Credentials**: Tokens and Ed25519 cryptographic keypairs are stored exclusively via Windows Credential Manager / DPAPI.

---

## 🎯 Operating Modes

1. **`AUDIT` (Default)**
   - Observes process activity and DNS queries against active policy rules.
   - Dispatches health and policy-match telemetry without terminating applications or blocking web access.

2. **`DEVELOPMENT_ENFORCEMENT`**
   - Enabled explicitly by local administrator action (`enable-development-mode`).
   - Executes safe process warn/close actions (with grace periods and cooldowns) during active professor sessions.
   - Runs socket DNS resolver on port 5353 with optional adapter redirection.
   - Reports `usb_storage_restricted: false` (displays: `"USB restriction requires managed-device policy"`).
   - Displays a visible status banner: `*** ENFORCEMENT ACTIVE (DEV) ***`.

3. **`MANAGED_ENFORCEMENT`**
   - Requires device-management compliance confirmation from backend.
   - Coordinates with college MDM/GPO policies for application control, network DNS settings, and removable-storage restrictions.

---

## 🚀 Building Standalone Installer (PyInstaller)

To generate standalone single-file Windows executables:

```cmd
cd agent
python build_installer.py
```

This generates:
- `dist\AcademiaShieldInstaller.exe` (Standalone interactive installer & enrollment wizard)
- `dist\AcademiaShieldAgent.exe` (Standalone local agent runtime daemon)

---

## 📦 Installation & Enrollment

### Interactive Installation
Run the installer executable or Python script:

```cmd
python installer.py
```

Options:
- Displays permissions disclosure and requests explicit user consent.
- Installs agent files into `%LOCALAPPDATA%\AcademiaShield` (or custom directory via `--dir`).
- Optional approved Windows startup shortcut creation (`--startup`).
- Performs student account authentication and Ed25519 device registration (`POST /api/v1/agent/devices/register`).

### Unattended / Scripted Installation
```cmd
python installer.py --yes --url http://127.0.0.1:8000 --email student@university.edu --password SecurePassword123!
```

---

## 💻 CLI Commands Reference

| Command | Description |
|---|---|
| `python agent.py login` | Authenticates student, generates Ed25519 keypair, and enrolls device |
| `python agent.py logout` | Revokes backend session and securely wipes DPAPI credentials |
| `python agent.py status` | Displays mode, health status, active policy, DNS adapter backup state, and USB compliance |
| `python agent.py enable-development-mode` | Administrator action enabling `DEVELOPMENT_ENFORCEMENT` mode |
| `python agent.py disable-enforcement` | Reverts mode to `AUDIT`, stops app enforcement, and restores original DNS settings |
| `python agent.py uninstall` | Restores network DNS settings, cleans local DB/config, and removes startup shortcuts |
| `python agent.py run` | Runs local background polling loop (policy sync, DNS resolver, process monitor, heartbeat) |

---

## ⚙️ Safe Application & DNS Control

### Application Control
- Implements `log`, `warn`, and `close` actions.
- Visibly warns before terminating non-protected processes, utilizing a configurable grace period.
- Enforces per-rule cooldowns (e.g. 30s) to prevent spamming notifications or repeated terminations.
- Start initial testing safely with `notepad.exe`.

### DNS Resolver & Adapter Redirection
- **Local DNS Resolver**: Listens on UDP port 5353, parses DNS packets manually, synthesizes `NXDOMAIN` for blocked domains, and forwards allowed queries to approved upstream DNS (e.g., `8.8.8.8`).
- **Adapter Redirection**: When elevated and requested (`--enable-dns-adapter`), backs up original IPv4 DNS to `%LOCALAPPDATA%\AcademiaShield\dns_adapter_backup.json` before configuring adapter DNS to `127.0.0.1`.
- **Restoration**: Automatically restores original DNS settings on session end, agent shutdown, `disable-enforcement`, or `uninstall`.

### Emergency DNS Recovery
If an unexpected shutdown occurs while adapter DNS was redirected:

```cmd
python agent.py disable-enforcement
```
Or manually reset network adapter DNS via PowerShell:
```powershell
Get-NetAdapter | Where-Object Status -eq 'Up' | Set-DnsClientServerAddress -ResetServerAddresses
```

---

## 🏛️ College IT / MDM Setup for Managed Mode

For college-managed deployments (Intune, Group Policy, or MECM):
1. **Application Whitelisting / AppLocker**: Deploy standard AppLocker / Windows Defender Application Control (WDAC) XML policies.
2. **Removable Storage Restriction (GPO)**:
   - Path: `Computer Configuration -> Administrative Templates -> System -> Removable Storage Access`
   - Policy: `All Removable Storage classes: Deny all access` = **Enabled**
   - Windows Registry: `HKLM\SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices -> Deny_All = 1`
   - The agent's `USBComplianceManager` checks this key to confirm compliance.
3. **Enterprise DNS / Umbrella**: Deploy approved DNS over HTTPS / secure enterprise DNS profile via MDM.

---

## 🧪 Running Automated Tests

Run the complete test suite (58 unit and integration tests):

```cmd
cd agent
python -m pytest tests
```

To run only the safety and enforcement verification tests:

```cmd
python -m pytest tests/test_safety_and_enforcement.py -v
```
