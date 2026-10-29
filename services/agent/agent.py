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
    Enrollment              — Run `python agent.py enroll` before starting
    POLL_INTERVAL           — Polling interval in seconds (clamped to 5-300, default 8)
    ENFORCEMENT_MODE        — "HOSTS" (DNS setting falls back to HOSTS)
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
import atexit
import platform
import shutil
import subprocess
import threading
import time

import config
from config import (
    AGENT_ID,
    DNS_BACKUP_FILE,
    ENFORCEMENT_MODE,
    POLL_INTERVAL,
    SERVER_IP,
    SERVER_PORT,
    SOCKET_ENABLED,
    SOCKET_URL,
    STOP_FILE,
    TEST_MODE,
)
from logger import setup_logger
from comms import fetch_config_with_retry, report_to_server, send_heartbeat
from comms import http_client
from enforcement import get_engine, normalize_domain_list, restore_previous_system_state
from activity import get_activity_tracker
from credentials import load_credential, device_id, clear_credential
from enforcement.apps import enforce_blocked_apps

LOGGER = setup_logger()

# ---------------------------------------------------------------------------
# Globals & State
# ---------------------------------------------------------------------------
SYNC_EVENT = threading.Event()
RUNNING = True
LAST_APPLIED_DOMAINS = None
LAST_STATE = None
HEARTBEAT_INTERVAL = 15  # seconds between heartbeats
ACTIVITY_REPORT_INTERVAL = 3  # seconds between activity batch reports (near instant)
activity_tracker = None
_MAIN_MUTEX_HANDLE = None


def acquire_main_instance():
    """Prevent two agent loops from racing over one machine's hosts file."""
    global _MAIN_MUTEX_HANDLE
    if platform.system() != "Windows":
        return True
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateMutexW(None, False, "Global\\AcademiaShieldAgentMain")
    if not handle:
        LOGGER.error("Could not acquire agent instance guard; refusing enforcement")
        return False
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        LOGGER.warning("Another agent instance is already running")
        return False
    _MAIN_MUTEX_HANDLE = handle
    atexit.register(lambda: kernel32.CloseHandle(handle))
    return True


def disable_activity_tracking():
    if activity_tracker:
        activity_tracker.stop()
        activity_tracker.clear()


def request_stop():
    """Create a stop marker without following a planted symlink."""
    try:
        os.makedirs(os.path.dirname(STOP_FILE), exist_ok=True)
        if os.path.lexists(STOP_FILE):
            return os.path.isfile(STOP_FILE) and not os.path.islink(STOP_FILE)
        with open(STOP_FILE, "x", encoding="utf-8") as file:
            file.write("stop\n")
        return True
    except OSError as error:
        LOGGER.error("Cannot create agent stop request: %s", error)
        return False


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
            if LAST_STATE == "ACTIVE":
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
    global LAST_APPLIED_DOMAINS, LAST_STATE
    remote_config = fetch_config_with_retry()
    if os.path.lexists(STOP_FILE):
        disable_activity_tracking()
        LAST_STATE = "STANDBY" if engine.restore_rules() else "ERROR"
        LAST_APPLIED_DOMAINS = set()
        return
    if not remote_config:
        disable_activity_tracking()
        restored = engine.restore_rules()
        if restored:
            LAST_STATE = "STANDBY"
            LAST_APPLIED_DOMAINS = set()
        else:
            LAST_STATE = "ERROR"
        LOGGER.warning("No valid policy available; restoration %s", "complete" if restored else "will retry")
        return

    should_block = bool(remote_config.get("active", remote_config.get("blocking_active", False)))
    
    # A2 FIX: When using cached config, verify active sessions haven't passed ends_at
    if should_block and remote_config.get("is_cached"):
        active_sessions = remote_config.get("active_sessions", [])
        if active_sessions:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            has_active = False
            for s in active_sessions:
                ends_at_str = s.get("ends_at")
                if ends_at_str:
                    try:
                        clean_str = ends_at_str.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(clean_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt > now:
                            has_active = True
                            break
                    except Exception:
                        pass
            if not has_active:
                LOGGER.warning("All sessions in cached config have expired (ends_at passed). Disabling blocking.")
                should_block = False

    domains_to_block = sorted(
        set(
            str(d).strip().lower()
            for d in remote_config.get("blockedDomains", remote_config.get("domains", []))
            if str(d).strip()
        )
    ) if should_block else []

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

    if should_block:
        normalized = normalize_domain_list(domains_to_block)
        current_domains_set = set(normalized)
        
        if LAST_STATE != "ACTIVE" or LAST_APPLIED_DOMAINS != current_domains_set:
            LOGGER.info("Applying blocking rules for %s domains via %s", len(normalized), engine.name)
            
            success = engine.apply_rules(normalized)
            if success:
                report_to_server("BLOCK_APPLIED", normalized)
                LAST_STATE = "ACTIVE"
                LAST_APPLIED_DOMAINS = current_domains_set
            else:
                LOGGER.error("Failed to apply blocking rules; restoring previous managed settings.")
                engine.restore_rules()
                disable_activity_tracking()
                LAST_STATE = "ERROR"
                LAST_APPLIED_DOMAINS = set()
        else:
            LOGGER.debug("Blocking rules unchanged; skipping enforcement update")
        if LAST_STATE == "ACTIVE":
            if activity_tracker:
                activity_tracker.set_blocked_domains(domains_to_block)
                activity_tracker.start()
            blocked_apps = remote_config.get("blockedApps", [])
            for app in enforce_blocked_apps(blocked_apps):
                report_to_server("APP_CLOSE_REQUESTED", [app])
    else:
        disable_activity_tracking()
        if LAST_STATE != "STANDBY":
            LOGGER.info("STANDBY | no active blocking session")
        was_enforcing = LAST_STATE != "STANDBY"
        restored = engine.restore_rules()
        if restored:
            if was_enforcing:
                report_to_server("BLOCK_REMOVED")
            LAST_STATE = "STANDBY"
            LAST_APPLIED_DOMAINS = set()
        else:
            LAST_STATE = "ERROR"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    global LAST_STATE, LAST_APPLIED_DOMAINS
    if not acquire_main_instance():
        return
    if os.path.lexists(STOP_FILE):
        restore_previous_system_state()
        LOGGER.warning("Agent stop was requested; enforcement remains off")
        return
    if not load_credential():
        # A lost or removed credential must not leave a previous policy enforced.
        restore_previous_system_state()
        LOGGER.warning("Agent is not enrolled. Generate a claim in the student dashboard and run: python agent.py enroll")
        return
    LOGGER.info("=" * 50)
    LOGGER.info("ACADEMIA SHIELD AGENT")
    LOGGER.info("=" * 50)
    LOGGER.info("Server:           http://%s:%s", SERVER_IP, SERVER_PORT)
    LOGGER.info("Agent ID:         %s", AGENT_ID)
    LOGGER.info("Enforcement mode: %s", ENFORCEMENT_MODE)
    LOGGER.info("Test mode:        %s", TEST_MODE)
    LOGGER.info("Poll interval:    %ss", POLL_INTERVAL)
    LOGGER.info("Socket.IO:        %s", "enabled" if SOCKET_ENABLED else "disabled")
    LOGGER.info("Enrolled device:  %s", device_id())

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
    if not restore_previous_system_state():  # Recover both modes after a crash or mode change.
        LOGGER.error("Could not restore previous managed settings; refusing to enforce new policy")
        return

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
    LOGGER.info("Activity tracker ready: %s (starts with an active policy)", activity_tracker.__class__.__name__)

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

            if os.path.lexists(STOP_FILE):
                LOGGER.info("Stop requested; restoring and exiting")
                break

            sync_once(engine)

        except PermissionError:
            LOGGER.error("Permission denied while updating system configuration.")
            LOGGER.error("Run as administrator to apply blocking")
            disable_activity_tracking()
            LAST_STATE = "ERROR"
            LAST_APPLIED_DOMAINS = set()
            if not restore_previous_system_state():
                LOGGER.error("Could not restore managed network settings; recovery task will retry")
            SYNC_EVENT.wait(POLL_INTERVAL)
            SYNC_EVENT.clear()
        except KeyboardInterrupt:
            LOGGER.info("Interrupted (KeyboardInterrupt).")
            break
        except Exception as err:
            LOGGER.exception("Unexpected runtime error: %s", err)
            disable_activity_tracking()
            LAST_STATE = "ERROR"
            LAST_APPLIED_DOMAINS = set()
            try:
                if not restore_previous_system_state():
                    LOGGER.error("Could not restore managed network settings; recovery task will retry")
            except Exception:
                LOGGER.exception("Restoration after runtime error failed; recovery task will retry")
            SYNC_EVENT.wait(POLL_INTERVAL)
            SYNC_EVENT.clear()

    # Graceful shutdown (reached via KeyboardInterrupt or RUNNING=False)
    RUNNING = False
    LOGGER.info("Restoring original system state before shutdown...")
    try:
        try:
            disable_activity_tracking()
            engine.shutdown()
        except Exception:
            LOGGER.exception("Shutdown cleanup failed; trying direct restoration")
        if restore_previous_system_state():
            report_to_server("BLOCK_REMOVED")
        else:
            LOGGER.error("Shutdown restoration incomplete; recovery task will retry")
    finally:
        if agent_socket:
            agent_socket.disconnect()
        LOGGER.info("Agent stopped.")


def recover_expired_policy():
    """Scheduled offline cleanup after a crash or expired cached policy."""
    if (os.path.lexists(STOP_FILE) or os.path.lexists(DNS_BACKUP_FILE)
            or not load_credential() or not http_client.load_cached_config()):
        return restore_previous_system_state()
    return True


# ---------------------------------------------------------------------------
# Auto-startup: Install / Uninstall / Status
# ---------------------------------------------------------------------------
INSTALL_DIR = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "AcademiaShield")
INSTALL_EXE = os.path.join(INSTALL_DIR, "AcademiaShield.exe")
INSTALL_ENV = os.path.join(INSTALL_DIR, ".env.production")
TASK_NAME = "AcademiaShieldAgent"
RECOVERY_TASK_NAME = "AcademiaShieldRecovery"


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


def do_install(start_if_enrolled=True):
    """
    Install the agent for auto-startup:
    1. Copy the .exe to C:\\ProgramData\\AcademiaShield\\
    2. Write non-secret runtime configuration
    3. Create a Windows Scheduled Task to run at logon with admin rights
    """
    if platform.system() != "Windows":
        print("[ERROR] Auto-install is only supported on Windows.")
        return 1

    if not _is_admin():
        print("[ERROR] Installation requires Administrator privileges.")
        print("        Right-click your terminal and select 'Run as administrator'.")
        return 1

    if not getattr(sys, 'frozen', False):
        print("[ERROR] Auto-install requires the built Windows executable.")
        return 1

    print()
    print("=" * 55)
    print("  Academia Shield Agent — Installer")
    print("=" * 55)
    print()

    # 2. Create install directory. Enrollment is performed separately.
    os.makedirs(INSTALL_DIR, exist_ok=True)

    # 3. Copy the exe
    current_exe = _get_current_exe()
    if os.path.normcase(os.path.abspath(current_exe)) != os.path.normcase(os.path.abspath(INSTALL_EXE)):
        print(f"  [1/3] Copying agent to {INSTALL_DIR}...")
        try:
            shutil.copy2(current_exe, INSTALL_EXE)
        except OSError as error:
            print(f"[ERROR] Could not copy agent executable: {error}")
            return 1
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
"""
    if not os.path.exists(INSTALL_ENV):
        with open(INSTALL_ENV, "x", encoding="utf-8") as f:
            f.write(env_content)
    else:
        print("  Existing configuration preserved.")

    # 5. Create Scheduled Task
    print("  [3/3] Registering auto-start task...")

    # Recovery runs every minute so a crash cannot strand expired restrictions.
    recovery = subprocess.run(
        ["schtasks", "/create", "/tn", RECOVERY_TASK_NAME,
         "/tr", f'"{INSTALL_EXE}" --recover', "/sc", "MINUTE", "/mo", "1",
         "/rl", "HIGHEST", "/f"],
        capture_output=True, text=True,
    )
    if recovery.returncode != 0:
        print(f"[ERROR] Could not register recovery task: {recovery.stderr.strip()}")
        return 1

    # Create or update the logon task only after recovery is in place.
    result = subprocess.run(
        [
            "schtasks", "/create",
            "/tn", TASK_NAME,
            "/tr", f'"{INSTALL_EXE}"',
            "/sc", "ONLOGON",
            "/rl", "HIGHEST",         # Run with admin privileges
            "/f",                      # Force overwrite
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"[ERROR] Failed to create scheduled task: {result.stderr.strip()}")
        return 1

    if os.path.lexists(STOP_FILE):
        if os.path.islink(STOP_FILE):
            print("[ERROR] Stop marker is a symbolic link; inspect it before installation.")
            return 1
        try:
            os.remove(STOP_FILE)
        except OSError as error:
            print(f"[ERROR] Cannot clear prior stop request: {error}")
            return 1

    # Also start the agent now
    print()
    print("=" * 55)
    print("  ✅ Installation Complete!")
    print("=" * 55)
    print()
    print(f"  Device:     {'enrolled' if load_credential() else 'not enrolled'}")
    print(f"  Install:    {INSTALL_DIR}")
    print(f"  Auto-start: Enabled (runs at logon as Administrator)")
    print()
    print("  The agent will now start automatically every time you")
    print("  log into Windows. Enroll the device before starting enforcement.")
    print()
    print("  To uninstall:  AcademiaShield.exe --uninstall")
    print("  To check:      AcademiaShield.exe --status")
    print()

    if start_if_enrolled and load_credential():
        print("  Starting enrolled agent now...")
        print()
        return None  # Signal to continue into main().
    print("  Agent will start at the next Windows sign-in after enrollment.")
    return 0


def do_uninstall():
    """Stop enforcement and tasks, retaining files for safe manual cleanup."""
    if platform.system() != "Windows":
        print("[ERROR] Auto-uninstall is only supported on Windows.")
        return 1

    if not _is_admin():
        print("[ERROR] Uninstallation requires Administrator privileges.")
        return 1

    if not getattr(sys, 'frozen', False):
        print("[ERROR] Run uninstall from the built Windows executable.")
        return 1

    print()
    print("  Academia Shield Agent — Uninstaller")
    print()

    # Existing agent instances check this before applying another policy.
    if not request_stop():
        print("[ERROR] Could not create a safe stop request; no tasks were removed.")
        return 1

    # Stop future logon starts before restoring settings.
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("  [✓] Auto-start task removed.")
    else:
        remaining = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME], capture_output=True)
        if remaining.returncode == 0:
            print("[ERROR] Auto-start task still exists; stop request remains in place.")
            return 1
        print("  [—] No auto-start task found (already removed).")

    if not restore_previous_system_state():
        print("[ERROR] Could not restore all managed network settings. Recovery task and backup files remain for retry.")
        return 1

    try:
        clear_credential()
    except Exception as error:
        print(f"  [!] Could not remove local credential: {error}")

    recovery = subprocess.run(
        ["schtasks", "/delete", "/tn", RECOVERY_TASK_NAME, "/f"],
        capture_output=True, text=True,
    )
    if recovery.returncode == 0:
        print("  [✓] Recovery task removed.")
    else:
        print("  [!] Recovery task could not be removed; inspect it manually.")
        return 1

    print()
    print("  Managed hosts/DNS settings restored. Installed files and backups are retained")
    print(f"  in {INSTALL_DIR} for inspection; no directory is deleted automatically.")
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

    print(f"  Device:     {device_id() or '(not enrolled)'}")

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
        recovery = subprocess.run(
            ["schtasks", "/query", "/tn", RECOVERY_TASK_NAME],
            capture_output=True, text=True,
        )
        print(f"  Recovery:   {'Enabled' if recovery.returncode == 0 else 'Disabled'}")

    print()
    return 0


if __name__ == "__main__":
    # Handle CLI commands before entering the main agent loop
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower().strip("-/")
        if cmd == "enroll":
            if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != "--stdin"):
                print("Usage: python agent.py enroll [--stdin]")
                sys.exit(2)
            from enroll import enroll
            from getpass import getpass
            try:
                claim = sys.stdin.readline().strip() if len(sys.argv) == 3 else getpass("Enrollment code: ").strip()
                if len(claim) != 32 or not all(char.isalnum() or char in "-_" for char in claim):
                    raise ValueError("Invalid enrollment code")
                enrolled_id = enroll(claim)
                if os.path.lexists(STOP_FILE):
                    if os.path.islink(STOP_FILE):
                        raise RuntimeError("Stop marker is a symbolic link")
                    os.remove(STOP_FILE)
                print(f"Device enrolled: {enrolled_id}")
            except Exception as error:
                print(f"Enrollment failed: {error}")
                sys.exit(1)
            sys.exit(0)
        elif cmd == "logout":
            if not request_stop():
                print("[ERROR] Could not request safe agent stop.")
                sys.exit(1)
            if not restore_previous_system_state():
                print("[ERROR] Network settings could not be restored; credential retained for recovery.")
                sys.exit(1)
            clear_credential()
            print("Local device credential removed and managed settings restored. Revoke this device in the dashboard if needed.")
            sys.exit(0)
        elif cmd == "recover":
            sys.exit(0 if recover_expired_policy() else 1)
        elif cmd == "install":
            result = do_install()
            if result is not None:
                sys.exit(result)
            # result is None → continue into main()
            main()
        elif cmd == "install-only":
            sys.exit(do_install(start_if_enrolled=False))
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
            print("    AcademiaShield.exe --install-only  Install without starting the agent")
            print("    AcademiaShield.exe --uninstall   Remove auto-start")
            print("    AcademiaShield.exe --status      Show installation status")
            print("    AcademiaShield.exe enroll        Pair with a student account")
            print()
            sys.exit(0)
        else:
            print(f"  Unknown command: {sys.argv[1]}")
            print("  Use --help for usage information.")
            sys.exit(1)
    else:
        main()
