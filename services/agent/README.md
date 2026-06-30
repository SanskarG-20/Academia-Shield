# Academia Shield — Desktop Agent

The Academia Shield Desktop Agent is a lightweight background service that runs on student devices (currently Windows-only). It enforces website blocks in real-time when a professor starts a class session.

## Architecture

The agent supports two enforcement engines:
1. **HOSTS Mode** (Default/Prototype): Modifies the `C:\Windows\System32\drivers\etc\hosts` file to block domains.
2. **DNS Mode** (Production): Runs a local UDP DNS resolver on `127.0.0.1:53`. Blocked domains resolve to `127.0.0.1`, while all other traffic is forwarded to the system's upstream DNS. The agent redirects the system's DNS to itself via `netsh` during an active session and restores it immediately upon session end or service crash.

## Real-Time Communication

The agent connects to the Academia Shield backend via **Socket.IO** (if `python-socketio` is installed) to receive instant `SESSION_STARTED` and `SESSION_ENDED` events. 

If the Socket.IO connection drops or is unavailable, the agent falls back to an **HTTP Polling** loop (every 5–10 seconds), ensuring high availability even in degraded network conditions.

## Safety & Crash Recovery

- **Hosts Backup**: A one-time backup of the hosts file is taken before any modifications are ever made.
- **DNS Backup**: Original system DNS settings are saved to `dns_backup.json` and restored via an `atexit` emergency handler if the agent crashes.
- **Windows Service**: The agent runs as a native Windows Service (`AcademiaShieldAgent`). If the service crashes, Windows is configured to automatically restart it within 60 seconds.

## Installation (Windows)

The agent must be installed as Administrator. The installer will automatically compile the Python code into a native `.exe`, register the Windows Service, and configure auto-restart on failure.

1. Ensure Python 3.9+ is installed and in your system PATH.
2. Right-click `install_windows.bat` and select **Run as administrator**.

The agent will now run silently in the background on every boot. Logs can be found at `C:\Program Files\AcademiaShield\agent.log`.

## Development & Testing

To run the agent locally without installing it as a service:

```bash
# Optional: Install Socket.IO support for instant push events
pip install python-socketio[client]

# Run the agent in test mode
set TEST_MODE=true
set ENFORCEMENT_MODE=DNS
python agent.py
```
