"""
Academia Shield Agent — Main Orchestrator (v1.0.0)

This is the entry point for the agent. It selects the appropriate
enforcement engine (Hosts or DNS) based on configuration, polls the
backend for active sessions, and applies/restores blocking rules.

Usage:
    python agent.py

Environment Variables:
    API_URL                 — Full API URL (e.g., https://academia-shield-api.onrender.com)
    TEST_MODE               — "true" for local development
    SERVER_IP               — Backend API IP address (fallback if API_URL not set)
    SERVER_PORT             — Backend API port (default 5000)
    STUDENT_SAP_ID          — Student SAP ID for log attribution
    AGENT_SHARED_SECRET     — Sent as X-Agent-Secret on /api/agent/* calls
    PAIRING_ALLOWED_ORIGINS — Comma-separated web origins allowed to pair this machine
    POLL_INTERVAL           — Polling interval in seconds (clamped to 5-300, default 8)
    ENFORCEMENT_MODE        — "HOSTS" (default) or "DNS"
    SOCKET_ENABLED          — "true" to enable Socket.IO push (requires python-socketio)

See config.py for the full list of configuration options.
"""

import os
import sys

# Ensure the agent directory is on sys.path so our sibling modules import
# correctly regardless of the working directory the agent was launched from.
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)


def _force_utf8_console():
    """
    Make stdout/stderr UTF-8 tolerant.

    The default Windows console codepage (cp1252) cannot encode the check and
    cross marks used in the status output, which otherwise raises
    UnicodeEncodeError and kills the process. errors="replace" keeps the agent
    alive on any codepage.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


_force_utf8_console()

# Populate os.environ from the .env files BEFORE importing config, because
# config.py reads os.environ at import time.
import env_loader

env_loader.load_env()

import ctypes
import json
import platform
import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# Imported as a module (not `from config import ...`) so that the SAP ID set
# at runtime by the local pairing server is visible to every reader.
import config
from config import (
    AGENT_ID,
    ENFORCEMENT_MODE,
    POLL_INTERVAL,
    SERVER_IP,
    SERVER_PORT,
    SOCKET_ENABLED,
    SOCKET_URL,
    TEST_MODE,
)
from logger import setup_logger
from comms import fetch_config_with_retry, report_to_server, send_heartbeat
from comms import http_client
from enforcement import get_engine, normalize_domain_list
from activity import get_activity_tracker

LOGGER = setup_logger()

# ---------------------------------------------------------------------------
# Local Identity Server (Allows Web App to set SAP ID seamlessly)
# ---------------------------------------------------------------------------
SAP_ID_PATTERN = re.compile(r"^\d{12}$")


class LocalAgentHandler(BaseHTTPRequestHandler):
    """
    Accepts the pairing handshake from the web app on 127.0.0.1:49494.

    This endpoint decides which student every subsequent report and heartbeat is
    attributed to, so it is origin-checked rather than left open. CORS headers alone
    would not be enough: a simple cross-origin POST still reaches the handler even
    though the browser hides the response, so the Origin is validated before any
    state changes.
    """

    def _resolve_origin(self):
        """Return (origin_header, is_allowed) for the current request."""
        origin = (self.headers.get('Origin') or '').strip().rstrip('/')
        if not origin:
            # Not a browser. The socket is bound to loopback, so the caller is
            # already a local process with at least this much privilege.
            return '', True
        return origin, origin.lower() in config.PAIRING_ALLOWED_ORIGINS

    def _respond(self, status, body=b'', origin=''):
        self.send_response(status)
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self):
        origin, allowed = self._resolve_origin()
        if not allowed:
            LOGGER.warning(f"Rejected pairing preflight from disallowed origin: {origin}")
            self._respond(403, b'{"error":"origin not allowed"}')
            return

        self.send_response(204)
        if origin:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Access-Control-Request-Private-Network')
        self.send_header('Access-Control-Max-Age', '600')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        origin, allowed = self._resolve_origin()
        if not allowed:
            LOGGER.warning(f"Rejected pairing request from disallowed origin: {origin}")
            self._respond(403, b'{"error":"origin not allowed"}')
            return

        if self.path != '/identify':
            self._respond(404, b'{"error":"not found"}', origin)
            return

        try:
            content_length = int(self.headers.get('Content-Length', 0) or 0)
        except ValueError:
            content_length = 0

        if 0 < content_length <= 4096:
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                sap_id = str(data.get('sapId') or '').strip()
                if SAP_ID_PATTERN.match(sap_id):
                    config.STUDENT_SAP_ID = sap_id
                    LOGGER.info(f"Agent successfully paired with SAP ID: {sap_id}")
                    self._respond(200, b'{"status":"ok"}', origin)
                    return
            except Exception as e:
                LOGGER.error(f"Error parsing identify payload: {e}")

        self._respond(400, b'{"error":"invalid request"}', origin)

    def log_message(self, format, *args):
        pass # Suppress HTTP access logs

def start_local_server():
    try:
        server = HTTPServer(('127.0.0.1', 49494), LocalAgentHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        LOGGER.info("Local identity server listening on 127.0.0.1:49494")
    except Exception as e:
        LOGGER.error(f"Failed to start local identity server: {e}")

# ---------------------------------------------------------------------------
# Globals & State
# ---------------------------------------------------------------------------
SYNC_EVENT = threading.Event()
RUNNING = True
LAST_APPLIED_DOMAINS = None
LAST_STATE = None
HEARTBEAT_INTERVAL = 15  # seconds between heartbeats
ACTIVITY_REPORT_INTERVAL = 10  # seconds between activity batch reports
activity_tracker = None


# ---------------------------------------------------------------------------
# Foreground window detection (Windows / Linux / macOS)
# ---------------------------------------------------------------------------
def get_active_window_title():
    """Return the title of the currently focused window, or 'Unknown'."""
    try:
        if platform.system() == "Windows":
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return buf.value or "Unknown"
            return "Desktop"
        elif platform.system() == "Linux":
            import subprocess
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip() or "Unknown"
        elif platform.system() == "Darwin":
            import subprocess
            script = 'tell application "System Events" to get name of first application process whose frontmost is true'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip() or "Unknown"
    except Exception:
        pass
    return "Unknown"


# ---------------------------------------------------------------------------
# Heartbeat telemetry loop (runs in a daemon thread)
# ---------------------------------------------------------------------------
def heartbeat_loop():
    """Send periodic heartbeats with the foreground window title."""
    while RUNNING:
        try:
            if LAST_STATE in ("ACTIVE", "ERROR"):
                title = get_active_window_title()
                send_heartbeat(active_app=title, status="online")
            else:
                send_heartbeat(active_app="Idle", status="idle")
        except Exception as err:
            LOGGER.debug("Heartbeat error (non-fatal): %s", err)

        # Sleep in small increments so we can detect RUNNING=False quickly
        for _ in range(HEARTBEAT_INTERVAL):
            if not RUNNING:
                return
            time.sleep(1)


def activity_report_loop(tracker):
    """Periodically flush and send batched activity events to the backend."""
    while RUNNING:
        for _ in range(ACTIVITY_REPORT_INTERVAL * 10):
            if not RUNNING:
                return
            time.sleep(0.1)
        
        events = tracker.flush()
        if events:
            http_client.send_activity_batch(events)
            LOGGER.debug("Sent %d activity events", len(events))


# ---------------------------------------------------------------------------
# Admin rights check
# ---------------------------------------------------------------------------
def is_admin():
    """Check if the agent is running with administrator privileges."""
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Sync cycle
# ---------------------------------------------------------------------------
def sync_once(engine):
    """Single polling cycle: fetch config → apply or restore rules."""
    remote_config = fetch_config_with_retry()
    if not remote_config:
        LOGGER.warning("No config available from server or cache; retrying in %ss", POLL_INTERVAL)
        return

    should_block = bool(remote_config.get("active", remote_config.get("blocking_active", False)))
    domains_to_block = sorted(
        set(
            str(d).strip().lower()
            for d in remote_config.get("blockedDomains", remote_config.get("domains", []))
            if str(d).strip()
        )
    )

    LOGGER.info(
        "Fetch response | active=%s sessions=%s domains=%s test_mode=%s engine=%s",
        should_block,
        len(remote_config.get("active_sessions", [])),
        len(domains_to_block),
        remote_config.get("test_mode", TEST_MODE),
        engine.name,
    )

    if domains_to_block:
        LOGGER.info("Blocked domain set from API: %s", ", ".join(domains_to_block))

    global LAST_APPLIED_DOMAINS, LAST_STATE

    if should_block:
        normalized = normalize_domain_list(domains_to_block)
        current_domains_set = set(normalized)
        
        if activity_tracker:
            activity_tracker.set_blocked_domains(domains_to_block)

        if LAST_STATE != "ACTIVE" or LAST_APPLIED_DOMAINS != current_domains_set:
            LOGGER.info("Applying blocking rules for %s domains via %s", len(normalized), engine.name)
            
            success = engine.apply_rules(normalized)
            if success:
                report_to_server("BLOCK_APPLIED", normalized)
                LAST_STATE = "ACTIVE"
                LAST_APPLIED_DOMAINS = current_domains_set
            else:
                LOGGER.error("Failed to apply blocking rules (run as Administrator to block domains). Activity monitoring remains active.")
                LAST_STATE = "ERROR"
                LAST_APPLIED_DOMAINS = current_domains_set
        else:
            LOGGER.debug("Blocking rules unchanged; skipping enforcement update")
    else:
        if LAST_STATE != "STANDBY":
            LOGGER.info("STANDBY | no active blocking session")
            engine.restore_rules()
            report_to_server("BLOCK_REMOVED")
            LAST_STATE = "STANDBY"
            LAST_APPLIED_DOMAINS = set()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    start_local_server()
    LOGGER.info("=" * 50)
    LOGGER.info("ACADEMIA SHIELD AGENT")
    LOGGER.info("=" * 50)
    LOGGER.info("Server:           http://%s:%s", SERVER_IP, SERVER_PORT)
    LOGGER.info("Agent ID:         %s", AGENT_ID)
    LOGGER.info("Enforcement mode: %s", ENFORCEMENT_MODE)
    LOGGER.info("Test mode:        %s", TEST_MODE)
    LOGGER.info("Poll interval:    %ss", POLL_INTERVAL)
    LOGGER.info("Socket.IO:        %s", "enabled" if SOCKET_ENABLED else "disabled")
    LOGGER.info("Student SAP ID:   %s", config.STUDENT_SAP_ID or "(not set - logs will use agent hostname)")

    # Admin check
    if is_admin():
        LOGGER.info("Privileges:       Administrator ✓")
    else:
        LOGGER.warning("Privileges:       Standard user ✗")
        LOGGER.warning("The agent requires administrator/root privileges to modify")
        LOGGER.warning("the hosts file or DNS settings. Enforcement may fail.")
        LOGGER.warning("Please restart as administrator for full functionality.")

    LOGGER.info("=" * 50)

    # Select engine
    engine = get_engine()
    LOGGER.info("Active engine:    %s", engine.name)

    # Socket.IO setup (optional push channel; HTTP polling works regardless)
    agent_socket = None
    if SOCKET_ENABLED:
        def on_socket_event(data):
            LOGGER.info("Socket event received — forcing immediate sync")
            SYNC_EVENT.set()

        from comms import AgentSocketClient

        agent_socket = AgentSocketClient(
            server_url=SOCKET_URL,
            agent_id=AGENT_ID,
            on_session_started=on_socket_event,
            on_session_ended=on_socket_event,
        )
        agent_socket.connect()

    # Start heartbeat thread (daemon so it auto-stops with the process)
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
    heartbeat_thread.start()
    LOGGER.info("Heartbeat:        every %ss", HEARTBEAT_INTERVAL)

    # Start activity tracker
    global activity_tracker
    activity_tracker = get_activity_tracker()
    activity_tracker.start()
    LOGGER.info("Activity tracker: %s", activity_tracker.__class__.__name__)

    activity_thread = threading.Thread(target=activity_report_loop, args=(activity_tracker,), daemon=True, name="activity-reporter")
    activity_thread.start()

    # Main polling loop. The first iteration runs immediately so that a
    # restart re-applies any in-progress session without waiting a full cycle.
    global RUNNING
    first_cycle = True

    while RUNNING:
        try:
            if first_cycle:
                first_cycle = False
            else:
                # Wait for either POLL_INTERVAL seconds or an immediate socket event
                SYNC_EVENT.wait(POLL_INTERVAL)
                SYNC_EVENT.clear()

            if not RUNNING:
                break

            sync_once(engine)

        except PermissionError:
            LOGGER.error("Permission denied while updating system configuration.")
            LOGGER.error("Run as administrator to apply blocking")
            SYNC_EVENT.wait(POLL_INTERVAL)
            SYNC_EVENT.clear()
        except KeyboardInterrupt:
            LOGGER.info("Interrupted (KeyboardInterrupt).")
            break
        except Exception as err:
            LOGGER.exception("Unexpected runtime error: %s", err)
            SYNC_EVENT.wait(POLL_INTERVAL)
            SYNC_EVENT.clear()

    # Graceful shutdown (reached via KeyboardInterrupt or RUNNING=False)
    RUNNING = False
    LOGGER.info("Restoring original system state before shutdown...")
    try:
        if activity_tracker:
            # Final flush
            events = activity_tracker.flush()
            if events:
                http_client.send_activity_batch(events)
            activity_tracker.stop()
        engine.shutdown()
        report_to_server("BLOCK_REMOVED")
    finally:
        if agent_socket:
            agent_socket.disconnect()
        LOGGER.info("Agent stopped.")


# ---------------------------------------------------------------------------
# Auto-startup: Install / Uninstall / Status
# ---------------------------------------------------------------------------
INSTALL_DIR = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "AcademiaShield")
INSTALL_EXE = os.path.join(INSTALL_DIR, "AcademiaShield.exe")
INSTALL_ENV = os.path.join(INSTALL_DIR, ".env.production")
TASK_NAME = "AcademiaShieldAgent"


def _get_current_exe():
    """Return the path to the currently running .exe (or .py during dev)."""
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle
        return sys.executable
    else:
        # Running as a Python script (dev mode)
        return os.path.abspath(__file__)


def _is_admin():
    """Check admin privileges (needed for install)."""
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return os.geteuid() == 0
    except Exception:
        return False


def do_install():
    """
    Install the agent for auto-startup:
    1. Copy the .exe to C:\\ProgramData\\AcademiaShield\\
    2. Write a .env.production with the student's SAP ID
    3. Create a Windows Scheduled Task to run at logon with admin rights
    """
    if platform.system() != "Windows":
        print("[ERROR] Auto-install is only supported on Windows.")
        return 1

    if not _is_admin():
        print("[ERROR] Installation requires Administrator privileges.")
        print("        Right-click your terminal and select 'Run as administrator'.")
        return 1

    print()
    print("=" * 55)
    print("  Academia Shield Agent — Installer")
    print("=" * 55)
    print()

    # 2. Create install directory. The SAP ID is intentionally left blank —
    #    the web app pairs it at runtime via the local identity server.
    os.makedirs(INSTALL_DIR, exist_ok=True)

    # 3. Copy the exe
    current_exe = _get_current_exe()
    if current_exe.endswith('.py'):
        print("[WARNING] Running from source — skipping .exe copy.")
        print("          Build with PyInstaller first, then run the .exe with --install.")
    else:
        if os.path.normpath(current_exe) != os.path.normpath(INSTALL_EXE):
            print(f"  [1/3] Copying agent to {INSTALL_DIR}...")
            shutil.copy2(current_exe, INSTALL_EXE)
        else:
            print("  [1/3] Agent already in install directory.")

    # 4. Write .env.production
    print("  [2/3] Saving configuration...")
    env_content = """# Academia Shield Agent — Auto-generated configuration
NODE_ENV=production
TEST_MODE=false
API_URL=https://academia-shield.onrender.com
POLL_INTERVAL=30
REQUEST_TIMEOUT=10
RETRY_ATTEMPTS=5
ENFORCEMENT_MODE=HOSTS
SOCKET_ENABLED=false
STUDENT_SAP_ID=
"""
    with open(INSTALL_ENV, "w", encoding="utf-8") as f:
        f.write(env_content)

    # 5. Create Scheduled Task
    print("  [3/3] Registering auto-start task...")

    # Remove existing task if present
    subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, check=False,
    )

    # Create new task: run at logon, with highest privileges, no time limit
    exe_path = INSTALL_EXE if not current_exe.endswith('.py') else current_exe
    result = subprocess.run(
        [
            "schtasks", "/create",
            "/tn", TASK_NAME,
            "/tr", f'"{exe_path}"',
            "/sc", "ONLOGON",
            "/rl", "HIGHEST",         # Run with admin privileges
            "/f",                      # Force overwrite
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"[ERROR] Failed to create scheduled task: {result.stderr.strip()}")
        return 1

    # Also start the agent now
    print()
    print("=" * 55)
    print("  ✅ Installation Complete!")
    print("=" * 55)
    print()
    print(f"  SAP ID:     (Auto-detected via Web App)")
    print(f"  Install:    {INSTALL_DIR}")
    print(f"  Auto-start: Enabled (runs at logon as Administrator)")
    print()
    print("  The agent will now start automatically every time you")
    print("  log into Windows. No further action is needed.")
    print()
    print("  To uninstall:  AcademiaShield.exe --uninstall")
    print("  To check:      AcademiaShield.exe --status")
    print()

    # Start the agent immediately
    print("  Starting agent now...")
    print()
    return None  # Signal to continue into main()


def do_uninstall():
    """Remove the scheduled task and optionally the install directory."""
    if platform.system() != "Windows":
        print("[ERROR] Auto-uninstall is only supported on Windows.")
        return 1

    if not _is_admin():
        print("[ERROR] Uninstallation requires Administrator privileges.")
        return 1

    print()
    print("  Academia Shield Agent — Uninstaller")
    print()

    # 1. Remove scheduled task
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("  [✓] Auto-start task removed.")
    else:
        print("  [—] No auto-start task found (already removed).")

    # 2. Remove install directory
    if os.path.exists(INSTALL_DIR):
        try:
            # Don't delete the exe if we're running from it
            current_exe = _get_current_exe()
            if os.path.normpath(current_exe) == os.path.normpath(INSTALL_EXE):
                # We're running from install dir — just remove env and task
                if os.path.exists(INSTALL_ENV):
                    os.remove(INSTALL_ENV)
                print("  [✓] Configuration removed.")
                print(f"  [!] Delete {INSTALL_DIR} manually (agent is running from there).")
            else:
                shutil.rmtree(INSTALL_DIR, ignore_errors=True)
                print(f"  [✓] Removed {INSTALL_DIR}")
        except Exception as e:
            print(f"  [!] Could not fully remove install dir: {e}")
    else:
        print("  [—] Install directory not found.")

    print()
    print("  ✅ Uninstallation complete. Agent will no longer auto-start.")
    print()
    return 0


def do_status():
    """Show installation status."""
    print()
    print("  Academia Shield Agent — Status")
    print()

    # Check install directory
    if os.path.exists(INSTALL_EXE):
        print(f"  Install:    {INSTALL_EXE} ✓")
    else:
        print("  Install:    Not installed")

    # Check env file
    if os.path.exists(INSTALL_ENV):
        with open(INSTALL_ENV, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("STUDENT_SAP_ID="):
                    sap = line.strip().split("=", 1)[1]
                    print(f"  SAP ID:     {sap or '(paired at runtime by the web app)'}")
                    break
    else:
        print("  SAP ID:     (no config found)")

    # Check scheduled task (Windows only — schtasks does not exist elsewhere)
    if platform.system() != "Windows":
        print("  Auto-start: n/a (Windows only)")
    else:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("  Auto-start: Enabled ✓")
        else:
            print("  Auto-start: Disabled ✗")

    print()
    return 0


if __name__ == "__main__":
    # Handle CLI commands before entering the main agent loop
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower().strip("-/")
        if cmd == "install":
            result = do_install()
            if result is not None:
                sys.exit(result)
            # result is None → continue into main()
            main()
        elif cmd == "uninstall":
            sys.exit(do_uninstall())
        elif cmd == "status":
            sys.exit(do_status())
        elif cmd in ("help", "h", "?"):
            print()
            print("  Academia Shield Agent")
            print()
            print("  Usage:")
            print("    AcademiaShield.exe              Run the agent")
            print("    AcademiaShield.exe --install     Install and auto-start on boot")
            print("    AcademiaShield.exe --uninstall   Remove auto-start")
            print("    AcademiaShield.exe --status      Show installation status")
            print()
            sys.exit(0)
        else:
            print(f"  Unknown command: {sys.argv[1]}")
            print("  Use --help for usage information.")
            sys.exit(1)
    else:
        main()
