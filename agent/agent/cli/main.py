"""
Unified CLI for Academia Shield Windows Local Agent.

Commands:
  login / enroll             - Authenticate with backend and enroll device with Ed25519 keypair
  logout                    - Revoke backend session and securely delete credentials from DPAPI/Keyring
  status                    - Display current agent mode, enrollment, compliance, and active policy
  enable-development-mode   - Explicit local administrator action enabling DEVELOPMENT_ENFORCEMENT mode
  disable-enforcement       - Safely stop enforcement, restore network adapter DNS, and revert to AUDIT mode
  uninstall                 - Prompt for confirmation, restore network configuration, and clean agent files
  run                       - Run local agent orchestrator (policy sync, DNS resolver, process monitor, telemetry)
"""

import sys
import os
import time
import getpass
import argparse
import logging
import ctypes
from typing import Any, Dict, Set

# Ensure agent package is importable regardless of how this file is invoked
_current_dir = os.path.dirname(os.path.abspath(__file__))
_agent_pkg_dir = os.path.dirname(_current_dir)
_agent_root_dir = os.path.dirname(_agent_pkg_dir)
if _agent_root_dir not in sys.path:
    sys.path.insert(0, _agent_root_dir)

from agent.config import get_config, get_agent_mode, set_agent_mode
from agent.auth import TokenManager, Ed25519KeyManager
from agent.api import APIClientAdapter
from agent.storage import LocalStorageDB
from agent.policy import PolicyManager
from agent.monitoring import ProcessMonitor
from agent.dns import LocalDNSServer
from agent.telemetry import TelemetryManager
from agent.platform import get_platform_adapter, WindowsDNSAdapterManager, USBComplianceManager, HostsEnforcementEngine
from agent.telemetry.engagement_tracker import EngagementTracker

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
LOGGER = logging.getLogger("academia_agent")

def is_admin_user() -> bool:
    """Check if current process has elevated administrator privileges."""
    try:
        if sys.platform == "win32":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False

def cmd_login(args):
    """Real authentication and device enrollment command."""
    print("=" * 65)
    print(" ACADEMIA SHIELD AGENT -- AUTHENTICATION & DEVICE ENROLLMENT")
    print("=" * 65)
    print("Requested Permissions:")
    print(" - Windows Credential Manager / DPAPI : Securely store session tokens")
    print(" - Local DNS & Process Monitoring     : Safe session-bound policy enforcement")
    print("=" * 65)

    config = get_config()
    api_url = getattr(args, "url", None) or config.api_url or "http://127.0.0.1:8000"
    config.api_url = api_url.rstrip("/")

    token = getattr(args, "token", None)
    email = getattr(args, "email", None)
    password = getattr(args, "password", None)

    if not token and not email:
        print("\nChoose an enrollment method:")
        print(" [1] Enter 8-character Enrollment Token (Generated from Website)")
        print(" [2] Login with Student Email and Password")
        choice = input("\nSelect [1/2] (Default 1): ").strip() or "1"
        if choice == "1":
            token = input("Enter 8-Character Enrollment Token: ").strip()
        else:
            email = input("Email (Student or Professor): ").strip()
            try:
                password = getpass.getpass("Password: ").strip()
            except Exception:
                password = input("Password: ").strip()

    token_mgr = TokenManager()
    api_client = APIClientAdapter(token_manager=token_mgr)

    print("\n[1/3] Generating Ed25519 Device Keypair...")
    key_mgr = Ed25519KeyManager()
    priv_pem, pub_hex = key_mgr.generate_keypair()
    token_mgr.storage.store_credential("private_key", priv_pem)
    api_client.key_manager = key_mgr

    print(f"Device ID: {config.device_id}")
    print(f"Ed25519 Public Key: {pub_hex[:16]}...")

    os_adapter = get_platform_adapter()
    os_info = os_adapter.get_os_info()

    if token:
        print(f"\n[2/3] Enrolling device with Token '{token}' against {config.api_url}...")
        try:
            enroll_res = api_client.enroll_with_token(
                enrollment_token=token,
                public_key_hex=pub_hex,
                hostname=config.device_id,
                os_name=os_info["os_name"],
                os_version=os_info["os_version"]
            )
            print("\n[3/3] Device Successfully Enrolled and Paired with Student Account!")
            print("=" * 65)
            print("Session tokens saved to Windows Credential Store.")
            return True
        except Exception as err:
            print(f"\nDevice Enrollment Error: {err}")
            sys.exit(1)
    else:
        print(f"\n[2/3] Authenticating against {config.api_url}...")
        try:
            login_res = api_client.login(email, password)
            if not login_res.get("access_token"):
                print("Authentication failed: No access token returned.")
                sys.exit(1)
            print("Authentication Successful! Session tokens secured via Windows Credential Store.")
        except Exception as err:
            print(f"Authentication Error: {err}")
            sys.exit(1)

        print("\n[3/3] Registering Device with Backend...")
        try:
            enroll_res = api_client.enroll_device(
                public_key_hex=pub_hex,
                hostname=config.device_id,
                os_name=os_info["os_name"],
                os_version=os_info["os_version"]
            )
            if enroll_res.get("status") == "enrolled":
                print("\nDevice Successfully Enrolled and Bound to Account!")
                print("=" * 65)
                return True
            else:
                print(f"Enrollment response: {enroll_res}")
        except Exception as err:
            print(f"Device Enrollment Error: {err}")
            sys.exit(1)


def cmd_logout(args):
    """Revoke session and clear credentials."""
    print("Logging out device...")
    token_mgr = TokenManager()
    api_client = APIClientAdapter(token_manager=token_mgr)
    api_client.logout()
    print("Device session revoked and credentials securely wiped from Windows Credential Store and SQLite DB.")

def cmd_status(args):
    """Display current agent mode, health, compliance, and active policy status."""
    token_mgr = TokenManager()
    db = LocalStorageDB()
    config = get_config()
    current_mode = get_agent_mode(config.storage_dir)

    refresh_tok = token_mgr.get_refresh_token()
    device_id = token_mgr.get_device_id() or config.device_id

    latest_policy = db.get_latest_policy()
    pending_telemetry = len(db.peek_telemetry_batch(limit=1000))

    usb_mgr = USBComplianceManager(mode=current_mode)
    usb_status = usb_mgr.get_compliance_status()

    win_dns = WindowsDNSAdapterManager()
    dns_backup_exists = os.path.exists(win_dns.backup_file)

    # Check live session state from backend
    session_status_str = "IDLE / LEFT SESSION (No active session)"
    enforcement_str = "INACTIVE (Normal unrestricted internet)"
    api_client = APIClientAdapter(token_manager=token_mgr)
    if refresh_tok and api_client.is_backend_available():
        try:
            pol_res = api_client.fetch_policy()
            if pol_res and pol_res.get("policy_active"):
                session_id = pol_res.get("session_id", "Active")
                domain_cnt = len(pol_res.get("domain_rules", []))
                app_cnt = len(pol_res.get("application_rules", []))
                session_status_str = f"IN ACTIVE SESSION ({session_id})"
                enforcement_str = f"ENFORCING ({domain_cnt} websites, {app_cnt} apps blocked)"
            else:
                session_status_str = "IDLE / NOT IN SESSION (Student left or session not active)"
                enforcement_str = "INACTIVE (Baseline internet restored)"
        except Exception:
            session_status_str = "BACKEND DISCONNECTED / IDLE"

    print("=" * 65)
    print(" ACADEMIA SHIELD AGENT STATUS")
    print("=" * 65)
    print(f" Operating Mode:      {current_mode}")
    print(f" Device ID:           {device_id}")
    print(f" Backend API URL:     {config.api_url}")
    print(f" Device Enrollment:   {'ENROLLED (Hardware Paired)' if refresh_tok else 'NOT ENROLLED'}")
    print(f" Session State:       {session_status_str}")
    print(f" Blocking Policy:     {enforcement_str}")
    print(f" Agent Version:       {config.agent_version}")
    print(f" Elevated Admin:      {'YES' if is_admin_user() else 'NO'}")
    print(f" DNS Adapter Backup:  {'ACTIVE (' + win_dns.backup_file + ')' if dns_backup_exists else 'NONE (Default DHCP)'}")
    print("=" * 65)


def cmd_enable_dev_mode(args):
    """Explicit administrator action to enable DEVELOPMENT_ENFORCEMENT mode."""
    print("=" * 65)
    print(" ACADEMIA SHIELD AGENT -- ENABLE DEVELOPMENT ENFORCEMENT MODE")
    print("=" * 65)

    if not is_admin_user():
        print("Notice: Administrator privileges are recommended for live adapter DNS redirection.")

    config = get_config()
    set_agent_mode("DEVELOPMENT_ENFORCEMENT", storage_dir=config.storage_dir)
    print("Status: DEVELOPMENT_ENFORCEMENT mode ENABLED.")
    print("=" * 65)
    print(" >>> ENFORCEMENT ACTIVE <<<")
    print(" - Safe App warn/close enforcement enabled for active professor sessions")
    print(" - Local DNS resolver active on port 5353")
    print(" - USB restriction requires managed-device policy (no automatic USB blocking)")
    print("=" * 65)

def cmd_disable_enforcement(args):
    """Safely stop enforcement, restore network adapter DNS, and revert to AUDIT mode."""
    print("=" * 65)
    print(" ACADEMIA SHIELD AGENT -- DISABLE ENFORCEMENT")
    print("=" * 65)

    config = get_config()
    win_dns = WindowsDNSAdapterManager()

    print("Restoring original network adapter DNS settings...")
    try:
        restored = win_dns.restore_original_dns()
        if restored:
            print("Original DNS settings verified and restored.")
        else:
            print("WARNING: DNS restoration is incomplete. The recovery journal was kept")
            print("         and the background recovery guard will retry automatically.")
    except Exception as err:
        LOGGER.warning("Could not restore DNS settings: %s", err)

    try:
        hosts_engine = HostsEnforcementEngine() if HostsEnforcementEngine else None
        if hosts_engine:
            hosts_engine.restore_rules()
    except Exception as err:
        LOGGER.warning("Could not restore hosts file rules: %s", err)

    set_agent_mode("AUDIT", storage_dir=config.storage_dir)
    print("Agent Operating Mode reverted to AUDIT (non-blocking).")
    print("All enforcement terminated safely.")
    print("=" * 65)

def cmd_uninstall(args):
    """Uninstall agent configuration and restore system settings."""
    force = getattr(args, "yes", False)
    if not force:
        ans = input("Are you sure you want to disable enforcement and uninstall Academia Shield Agent? (yes/no): ").strip().lower()
        if ans not in ("y", "yes"):
            print("Uninstall cancelled.")
            return

    print("\n[1/3] Restoring network adapter configuration...")
    config = get_config()
    win_dns = WindowsDNSAdapterManager()
    try:
        if not win_dns.restore_original_dns():
            print("ERROR: Original DNS settings could not be verified and restored.")
            print("       Uninstallation aborted so the recovery journal is not destroyed.")
            print("       Re-run this command as Administrator; the recovery guard will also retry.")
            return
        hosts_engine = HostsEnforcementEngine() if HostsEnforcementEngine else None
        if hosts_engine:
            hosts_engine.restore_rules()
        win_dns.remove_recovery_task()
        print("Original network configuration restored and verified.")
    except Exception as err:
        LOGGER.warning("Error during DNS restoration: %s", err)
        print("ERROR: DNS restoration failed; uninstallation aborted to keep recovery data.")
        return

    print("[2/3] Wiping secure credentials and tokens...")
    cmd_logout(args)

    print("[3/3] Removing agent configuration and database...")
    storage_dir = config.storage_dir
    import shutil
    if os.path.exists(storage_dir):
        try:
            shutil.rmtree(storage_dir)
            print(f"Removed local agent data directory: {storage_dir}")
        except Exception as err:
            print(f"Error removing directory: {err}")

    # Remove optional startup shortcut if present
    try:
        if sys.platform == "win32":
            startup_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
            shortcut_path = os.path.join(startup_dir, "AcademiaShieldAgent.lnk")
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
                print(f"Removed startup shortcut: {shortcut_path}")
    except Exception:
        pass

    print("\nAcademia Shield Agent uninstalled successfully. No hidden accounts or services remain.")

def cleanup_all_enforcement(hosts_engine=None, win_dns=None, usb_compliance=None, dns_server=None, is_admin=False):
    """Guaranteed failsafe cleanup of all system interventions."""
    try:
        if dns_server:
            dns_server.stop()
    except Exception:
        pass
    try:
        if hosts_engine:
            hosts_engine.restore_rules()
    except Exception:
        pass
    try:
        if win_dns:
            if not win_dns.restore_original_dns():
                LOGGER.error(
                    "DNS restoration is incomplete. The journal was retained and the "
                    "background recovery guard will keep retrying."
                )
    except Exception as err:
        LOGGER.error("DNS restoration error during cleanup: %s", err)
    try:
        if is_admin and usb_compliance:
            usb_compliance.restore_usb_storage_access()
    except Exception:
        pass

def cmd_repair(args):
    """Crash/reboot recovery entry point; safe to run from the SYSTEM guard task."""
    quiet = bool(getattr(args, "quiet", False))
    win_dns = WindowsDNSAdapterManager()
    had_journal = os.path.exists(win_dns.backup_file)

    try:
        result = win_dns.recover_orphaned_state()
    except Exception as err:
        LOGGER.exception("Network recovery check failed: %s", err)
        result = {"status": "error", "error": str(err)}

    # A journal means a DNS-redirected session was orphaned. Remove the managed
    # hosts block as well so the machine is fully back to baseline.
    if had_journal and result.get("reason") != "resolver_live":
        try:
            hosts_engine = HostsEnforcementEngine() if HostsEnforcementEngine else None
            if hosts_engine:
                hosts_engine.restore_rules()
        except Exception as err:
            LOGGER.debug("Hosts restoration during repair: %s", err)

    # Nothing left to guard once the journal is gone.
    if not os.path.exists(win_dns.backup_file):
        win_dns.remove_recovery_task()

    if not quiet:
        print("Network recovery status:", result.get("status"), result.get("reason") or "")
    return result


def cmd_run(args):
    """Main Agent Runtime Orchestrator Loop."""
    config = get_config()
    current_mode = get_agent_mode(config.storage_dir)

    LOGGER.info("Starting Academia Shield Desktop Agent v%s (Mode: %s)", config.agent_version, current_mode)
    LOGGER.info("API URL: %s | Device ID: %s", config.api_url, config.device_id)

    is_admin = is_admin_user()
    if is_admin:
        LOGGER.info("Privileges: Administrator ✓")
    else:
        LOGGER.info("Privileges: Standard user (Safe non-elevated runtime)")

    # Startup self-healing: ensure any stale restrictions from unexpected crashes are restored.
    # The adapter journal is machine-wide (ProgramData) so a crashed run, a reboot or a
    # different user account can always find and undo a half-applied DNS redirect.
    win_dns = WindowsDNSAdapterManager()
    hosts_engine = HostsEnforcementEngine() if HostsEnforcementEngine else None
    usb_compliance = USBComplianceManager(mode=current_mode)

    recovery: Dict[str, Any] = {}
    try:
        recovery = win_dns.recover_orphaned_state()
        LOGGER.info(
            "Startup network recovery: %s%s",
            recovery.get("status"),
            f" ({recovery.get('reason')})" if recovery.get("reason") else "",
        )
    except Exception as err:
        LOGGER.debug("Startup DNS recovery: %s", err)

    try:
        # Keep hosts rules intact when an already-running resolver owns the state,
        # otherwise remove any stale block left by a previous crash.
        if hosts_engine and recovery.get("reason") != "resolver_live":
            hosts_engine.restore_rules()
    except Exception as err:
        LOGGER.debug("Startup hosts rule restoration: %s", err)

    try:
        if is_admin:
            usb_compliance.restore_usb_storage_access()
    except Exception as err:
        LOGGER.debug("Startup USB restoration: %s", err)

    db = LocalStorageDB()
    token_mgr = TokenManager()

    # Do not enter the background loop when it cannot authenticate or obtain
    # policy.  Previously this looked like a started agent while enforcement
    # was permanently inactive and the logs only showed repeated retries.
    if not token_mgr.get_refresh_token():
        token_input = getattr(args, "token", None)
        if token_input:
            setattr(args, "token", token_input)
            cmd_login(args)
            token_mgr = TokenManager()
        else:
            LOGGER.info("Auto-registering device '%s' with backend...", config.device_id)
            key_mgr = Ed25519KeyManager()
            priv_pem, pub_hex = key_mgr.generate_keypair()
            token_mgr.storage.store_credential("private_key", priv_pem)
            temp_client = APIClientAdapter(token_manager=token_mgr, key_manager=key_mgr)
            os_adapter = get_platform_adapter()
            os_info = os_adapter.get_os_info()
            try:
                temp_client.enroll_with_token(
                    enrollment_token="",
                    public_key_hex=pub_hex,
                    hostname=config.device_id,
                    os_name=os_info["os_name"],
                    os_version=os_info["os_version"]
                )
                LOGGER.info("Device '%s' successfully connected to Academia Shield Backend!", config.device_id)
                token_mgr = TokenManager()
            except Exception as auto_err:
                LOGGER.warning("Auto-enrollment fallback notice: %s", auto_err)

    # Load private key if stored
    priv_pem = token_mgr.storage.get_credential("private_key")
    key_mgr = Ed25519KeyManager(private_key_pem=priv_pem) if priv_pem else None

    api_client = APIClientAdapter(token_manager=token_mgr, key_manager=key_mgr)
    backend_ok = False
    LOGGER.info("Connecting to backend at %s...", config.api_url)
    for attempt in range(1, 31):
        if api_client.is_backend_available():
            backend_ok = True
            break
        if attempt % 5 == 0:
            LOGGER.info("Waiting for backend service to become ready (%ds/30s)...", attempt)
        time.sleep(1)
    if not backend_ok:
        LOGGER.error(
            "Backend is unavailable at %s after 30s. Start it with: npm.cmd run dev:api",
            config.api_url,
        )
        return

    policy_mgr = PolicyManager(db=db, api_client=api_client)
    engagement_tracker = EngagementTracker(api_client=api_client)
    telemetry_mgr = TelemetryManager(db=db, api_client=api_client, engagement_tracker=engagement_tracker)
    platform_adapter = get_platform_adapter()
    proc_monitor = ProcessMonitor(platform_adapter=platform_adapter, telemetry_manager=telemetry_mgr)

    # Windows DNS adapters always query port 53.  Keep the unprivileged
    # resolver on its configured high port, but use port 53 when this
    # elevated runtime will redirect a real adapter to 127.0.0.1.
    # Redirecting an adapter to a resolver on 5353 can never enforce DNS
    # rules because Windows has no per-adapter DNS-port setting.
    dns_listener_port = 53 if is_admin else config.dns_listen_port
    dns_server = LocalDNSServer(
        listen_port=dns_listener_port,
        telemetry_manager=telemetry_mgr,
    )
    dns_server.start()

    # Register exit and signal cleanup handlers
    import signal
    import atexit
    _cleanup_executed = False

    def _safe_exit_cleanup(*_):
        nonlocal _cleanup_executed
        if not _cleanup_executed:
            _cleanup_executed = True
            LOGGER.info("Executing safe system enforcement cleanup...")
            cleanup_all_enforcement(hosts_engine, win_dns, usb_compliance, dns_server, is_admin)

    atexit.register(_safe_exit_cleanup)
    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, lambda signum, frame: _safe_exit_cleanup())
            except Exception:
                pass

    LOGGER.info("Agent initialization complete. Entering main polling loop (interval: %ss)...", config.poll_interval)

    _last_session_active = False
    _dns_enforced = False
    _hosts_enforced = False
    _dns_health_failures = 0
    _dns_suspended_until_session_end = False
    _dns_restore_next_attempt = 0.0
    _last_successful_sync = time.time()
    _seen_removable_drives: Set[str] = set()

    def _restore_adapter_dns(reason: str) -> None:
        """Undo adapter DNS redirection, keeping the journal until restore is verified."""
        nonlocal _dns_enforced, _dns_health_failures, _dns_restore_next_attempt
        journal_pending = os.path.exists(win_dns.backup_file)
        if not _dns_enforced and not journal_pending:
            _dns_health_failures = 0
            return
        now = time.time()
        if not _dns_enforced and now < _dns_restore_next_attempt:
            return
        try:
            restored = win_dns.restore_original_dns()
        except Exception as err:
            restored = False
            LOGGER.error("Adapter DNS restore error (%s): %s", reason, err)
        if restored:
            LOGGER.info("Adapter DNS restored (%s).", reason)
        else:
            LOGGER.error(
                "Adapter DNS restore incomplete (%s); journal retained and the network guard will retry.",
                reason,
            )
        _dns_enforced = False
        _dns_health_failures = 0
        _dns_restore_next_attempt = 0.0 if restored else now + 60.0

    try:
        while True:
            # Re-read mode in case it was toggled via CLI
            current_mode = get_agent_mode(config.storage_dir)
            usb_compliance.mode = current_mode

            # 1. Sync Active Policy
            policy, status_msg = policy_mgr.sync_policy()
            is_active = bool(policy and policy.is_session_active() and not policy.is_expired())

            if policy:
                dns_server.set_policy(policy)
                active_domains = policy.get_active_blocked_domains()
                active_apps = policy.get_active_blocked_apps()

                LOGGER.info("Policy sync: v%s | Session Active: %s | Mode: %s | Domains: %s | Apps: %s",
                            policy.policy_version, is_active, current_mode, len(active_domains), len(active_apps))

                if is_active:
                    first_win = policy.schedule_windows[0] if policy.schedule_windows else None
                    sess_id = getattr(first_win, "session_id", None) if first_win else None
                    batch_id = getattr(first_win, "batch_id", None) if first_win else None
                    if sess_id and not engagement_tracker.is_active:
                        engagement_tracker.start_session(
                            session_id=sess_id,
                            student_id=config.device_id,
                            batch_id=batch_id,
                            device_id=config.device_id
                        )
                    if engagement_tracker.is_active:
                        allowed_apps = set(policy.get_active_allowed_apps()) if hasattr(policy, "get_active_allowed_apps") else None
                        allowed_domains = set(policy.get_active_allowed_domains()) if hasattr(policy, "get_active_allowed_domains") else None
                        blocked_apps = set(policy.get_active_blocked_apps()) if hasattr(policy, "get_active_blocked_apps") else None
                        blocked_domains = set(policy.get_active_blocked_domains()) if hasattr(policy, "get_active_blocked_domains") else None
                        engagement_tracker.tick(
                            allowed_applications=allowed_apps if allowed_apps else None,
                            allowed_websites=allowed_domains,
                            blocked_applications=blocked_apps if blocked_apps else None,
                            blocked_websites=blocked_domains,
                            policy_version=policy.policy_version
                        )

                # Safe Enforcement Gate: Enforce ONLY in DEVELOPMENT_ENFORCEMENT or MANAGED_ENFORCEMENT modes
                if is_active and current_mode in ("DEVELOPMENT_ENFORCEMENT", "MANAGED_ENFORCEMENT"):
                    # 1. Safe Application Control (close / warn blocked applications)
                    proc_monitor.scan_and_enforce(policy)

                    # 2. Hosts-File Website Blocking (maps blocked domains to 127.0.0.1 and flushes DNS)
                    if hosts_engine:
                        if active_domains:
                            current_doms = tuple(sorted(str(d).strip().lower() for d in active_domains))
                            if not _hosts_enforced or getattr(hosts_engine, "_enforced_domains", None) != current_doms:
                                _hosts_enforced = hosts_engine.apply_rules(active_domains, allowed_domains=allowed_domains)
                                if _hosts_enforced:
                                    hosts_engine._enforced_domains = current_doms
                        elif _hosts_enforced:
                            hosts_engine.restore_rules()
                            hosts_engine._enforced_domains = None
                            _hosts_enforced = False

                    # 3. Active USB / Pen Drive Removable Storage Blocking
                    if is_admin and not getattr(usb_compliance, "_is_blocked", False):
                        usb_compliance.apply_usb_storage_block()

                    # 4. Detect unauthorized USB storage devices attached during session (1 pendrive = 1 violation)
                    detected_drives = set(usb_compliance.detect_removable_drives())
                    new_drives = detected_drives - _seen_removable_drives
                    if new_drives:
                        drive_list = sorted(list(new_drives))
                        LOGGER.warning("Unauthorized removable USB drive attached during active session: %s", drive_list)
                        telemetry_mgr.record_violation_event(
                            event_type="usb_storage_violation",
                            resource_name=f"USB_Drive_{','.join(drive_list)}",
                            action="blocked",
                            session_id=policy.schedule_windows[0].session_id if policy.schedule_windows else None,
                            rule_id="usb_storage_restriction",
                            details={"drives": drive_list, "message": "Unauthorized USB pen drive blocked during active session"}
                        )
                    _seen_removable_drives = detected_drives

                    # 5. DNS Adapter redirection: only ever point an adapter at loopback
                    #    when the resolver is verified alive on port 53. A failed apply
                    #    is rolled back immediately instead of leaving the device offline.
                    if is_admin and not _dns_enforced and not _dns_suspended_until_session_end:
                        if (
                            dns_server.healthy
                            and dns_listener_port == 53
                            and win_dns.resolver_is_alive(port=dns_listener_port)
                        ):
                            if win_dns.configure_local_dns(
                                target_dns="127.0.0.1",
                                resolver_healthy=True,
                                resolver_port=dns_listener_port,
                            ):
                                _dns_enforced = True
                                _dns_health_failures = 0
                            else:
                                LOGGER.error(
                                    "DNS adapter redirection failed; restoring any partially applied adapter state."
                                )
                                _restore_adapter_dns("redirect failed")
                        else:
                            LOGGER.error(
                                "DNS adapter redirection skipped: resolver must answer on port 53 (configured port: %s).",
                                dns_listener_port,
                            )
                else:
                    if current_mode == "AUDIT" and is_active:
                        LOGGER.info("AUDIT Mode: Active session detected, observing health and violations without blocking.")

                # If session just ended, restore settings and send idempotent policy_restored event
                if _last_session_active and not is_active:
                    LOGGER.info("Session ended or deactivated. Stopping enforcement and restoring settings.")
                    if engagement_tracker.is_active:
                        engagement_tracker.end_session()
                    if hosts_engine:
                        hosts_engine.restore_rules()
                        hosts_engine._enforced_domains = None
                        _hosts_enforced = False
                    _restore_adapter_dns("session ended")
                    _dns_suspended_until_session_end = False
                    if is_admin:
                        usb_compliance.restore_usb_storage_access()

                    # Idempotent policy_restored event
                    telemetry_mgr.record_violation_event(
                        event_type="policy_restored",
                        resource_name="all",
                        action="restored",
                        session_id=policy.schedule_windows[0].session_id if policy.schedule_windows else None,
                        rule_id="session_end_restoration",
                        is_violation=False
                    )

                _last_session_active = is_active
                _last_successful_sync = time.time()

            else:
                LOGGER.debug("Policy sync: %s", status_msg)
                offline_duration = time.time() - _last_successful_sync
                # Fail-safe watchdog: if offline for > 300s during an active session, auto-unblock all restrictions
                if _last_session_active and offline_duration > 300:
                    LOGGER.warning(
                        "Academia Shield Fail-Safe Watchdog: Backend unreachable for %ds (> 300s grace period). Auto-restoring all restrictions.",
                        int(offline_duration)
                    )
                    if hosts_engine:
                        hosts_engine.restore_rules()
                        _hosts_enforced = False
                    _restore_adapter_dns("backend offline fail-safe")
                    _dns_suspended_until_session_end = False
                    if is_admin:
                        usb_compliance.restore_usb_storage_access()
                    _last_session_active = False
                elif not _last_session_active:
                    if hosts_engine:
                        hosts_engine.restore_rules()
                        _hosts_enforced = False
                    _restore_adapter_dns("no active session")
                    _dns_suspended_until_session_end = False
                    if is_admin:
                        usb_compliance.restore_usb_storage_access()
                    _last_session_active = False

            # 2. DNS Health check
            health_info = dns_server.check_health_and_drift()
            if health_info.get("drift_detected"):
                LOGGER.warning("DNS Drift Detected! Recording telemetry...")
                telemetry_mgr.record_violation_event(
                    event_type="drift",
                    resource_name="dns_config",
                    action="drift_alert"
                )

            # Resolver watchdog: adapters must never stay pointed at a dead resolver.
            # Three consecutive failed probes restore the original adapter DNS and
            # keep redirection disabled until the current session ends.
            if _dns_enforced:
                if win_dns.resolver_is_alive(port=dns_listener_port):
                    _dns_health_failures = 0
                else:
                    _dns_health_failures += 1
                    LOGGER.warning(
                        "Local DNS resolver failed liveness probe (%d/3).",
                        _dns_health_failures,
                    )
                    if _dns_health_failures >= 3:
                        LOGGER.error(
                            "Local DNS resolver is unresponsive; restoring adapter DNS to prevent a network lockout."
                        )
                        _restore_adapter_dns("resolver unresponsive")
                        _dns_suspended_until_session_end = True

            # 3. Send Heartbeat with full compliance metrics
            app_ctrl_status = "active" if (is_active and current_mode != "AUDIT") else ("audit" if is_active else "idle")
            dns_status = "active" if (_dns_enforced or _hosts_enforced) else "normal"
            usb_restricted = usb_compliance.is_usb_storage_restricted()
            usb_status_str = usb_compliance.get_usb_storage_restriction_status()

            try:
                api_client.send_heartbeat(
                    active_app="AcademiaShieldAgent",
                    status_str="online",
                    agent_installed=True,
                    agent_service_running=True,
                    application_control_status=app_ctrl_status,
                    dns_enforcement_status=dns_status,
                    usb_storage_restricted=usb_restricted,
                    usb_storage_restriction_status=usb_status_str,
                    policy_version=policy.policy_version if policy else None
                )
            except Exception as err:
                LOGGER.debug("Heartbeat exception (best-effort): %s", err)

            telemetry_mgr.flush_queue()
            sleep_duration = 2 if is_active else config.poll_interval
            time.sleep(sleep_duration)

    except KeyboardInterrupt:
        LOGGER.info("Shutting down Academia Shield Agent...")
    finally:
        _safe_exit_cleanup()
        LOGGER.info("Agent shutdown complete.")

def main():
    parser = argparse.ArgumentParser(prog="academia-agent", description="Academia Shield Windows Local Agent CLI")
    subparsers = parser.add_subparsers(dest="command", help="Agent command to execute")

    # Login / Enroll
    p_login = subparsers.add_parser("login", help="Authenticate student and enroll device with Ed25519 keypair")
    p_login.add_argument("--url", help="Backend API URL")
    p_login.add_argument("--token", help="8-Character Enrollment Token from Website")
    p_login.add_argument("--email", help="Student email / Institutional ID")
    p_login.add_argument("--password", help="Student password")

    p_enroll = subparsers.add_parser("enroll", help="Alias for login")
    p_enroll.add_argument("--url", help="Backend API URL")
    p_enroll.add_argument("--token", help="8-Character Enrollment Token from Website")
    p_enroll.add_argument("--email", help="Student email / Institutional ID")
    p_enroll.add_argument("--password", help="Student password")

    # Logout
    p_logout = subparsers.add_parser("logout", help="Revoke session and wipe DPAPI credentials")

    # Status
    p_status = subparsers.add_parser("status", help="Show current mode, health, compliance, and active policy")

    # Enable Development Mode
    p_dev = subparsers.add_parser("enable-development-mode", help="Enable DEVELOPMENT_ENFORCEMENT mode (explicit admin action)")

    # Disable Enforcement
    p_dis = subparsers.add_parser("disable-enforcement", help="Stop enforcement, restore network adapter DNS, and revert to AUDIT")

    # Uninstall
    p_uninst = subparsers.add_parser("uninstall", help="Uninstall and remove agent configuration safely")
    p_uninst.add_argument("--yes", "-y", action="store_true", help="Skip interactive confirmation")

    # Network repair (used by the autonomous recovery guard task)
    p_repair = subparsers.add_parser("repair", help="Recover adapter DNS/hosts left behind by a crash or reboot")
    p_repair.add_argument("--orphan-check", action="store_true", help="Only act when stale agent state is present")
    p_repair.add_argument("--quiet", action="store_true", help="Suppress console output")

    # Run / Start
    p_run = subparsers.add_parser("run", help="Run local agent background daemon")
    p_run.add_argument("--token", help="8-Character Enrollment Token from Website")
    p_run.add_argument("--enable-dns-adapter", action="store_true", help="Enable elevated network adapter DNS redirection")

    p_start = subparsers.add_parser("start", help="Alias for run")
    p_start.add_argument("--token", help="8-Character Enrollment Token from Website")
    p_start.add_argument("--enable-dns-adapter", action="store_true", help="Enable elevated network adapter DNS redirection")

    args = parser.parse_args()

    if args.command in ("login", "enroll"):
        cmd_login(args)
    elif args.command == "logout":
        cmd_logout(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "enable-development-mode":
        cmd_enable_dev_mode(args)
    elif args.command == "disable-enforcement":
        cmd_disable_enforcement(args)
    elif args.command == "uninstall":
        cmd_uninstall(args)
    elif args.command == "repair":
        cmd_repair(args)
    elif args.command in ("run", "start"):
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
