"""
Academia Shield Agent — Main Orchestrator

This is the entry point for the agent. It selects the appropriate
enforcement engine (Hosts or DNS) based on configuration, polls the
backend for active sessions, and applies/restores blocking rules.

Usage:
    python agent.py

Environment Variables:
    API_URL            — Full API URL (e.g., https://academia-shield-api.onrender.com)
    TEST_MODE          — "true" for local development
    SERVER_IP          — Backend API IP address (fallback if API_URL not set)
    SERVER_PORT        — Backend API port (default 5000)
    STUDENT_SAP_ID     — Student SAP ID for log attribution
    POLL_INTERVAL      — Polling interval in seconds (5-10, default 8)
    ENFORCEMENT_MODE   — "HOSTS" (default) or "DNS"
    SOCKET_ENABLED     — "true" to enable Socket.IO push (requires python-socketio)

See config.py for the full list of configuration options.
"""

import sys
import os

# Load environment variables from .env file before any other imports
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(AGENT_DIR, f".env.{os.getenv('NODE_ENV', 'development')}")
if not os.path.exists(env_file):
    env_file = os.path.join(AGENT_DIR, ".env")

if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

import time
import logging
import ctypes
import platform
import threading

# Ensure the agent directory is on sys.path so relative imports work
# regardless of the working directory.
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from config import (
    ENFORCEMENT_MODE,
    POLL_INTERVAL,
    SERVER_IP,
    SERVER_PORT,
    AGENT_ID,
    STUDENT_SAP_ID,
    TEST_MODE,
    SOCKET_ENABLED,
    SOCKET_URL,
)
from logger import setup_logger
from comms.http_client import fetch_config_with_retry, report_to_server
from enforcement.hosts import HostsEnforcementEngine, normalize_domain_list

LOGGER = setup_logger()
SYNC_EVENT = threading.Event()
RUNNING = True
LAST_APPLIED_DOMAINS = None
LAST_STATE = None


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
# Engine selection
# ---------------------------------------------------------------------------
def get_engine():
    """Select the enforcement engine based on ENFORCEMENT_MODE config."""
    if ENFORCEMENT_MODE == "DNS":
        try:
            from enforcement.dns import DnsEnforcementEngine
            engine = DnsEnforcementEngine()
            if engine.is_available():
                LOGGER.info("DNS enforcement engine loaded successfully")
                return engine
            LOGGER.warning("DNS engine is not available on this system — falling back to HOSTS mode")
        except ImportError as err:
            LOGGER.warning("DNS engine could not be imported (%s) — falling back to HOSTS mode", err)
        except Exception as err:
            LOGGER.warning("DNS engine initialisation failed (%s) — falling back to HOSTS mode", err)

    engine = HostsEnforcementEngine()
    if engine.is_available():
        return engine

    LOGGER.error("No enforcement engine is available. Check permissions.")
    return engine  # Return anyway — errors will be caught at apply_rules time


# ---------------------------------------------------------------------------
# Sync cycle
# ---------------------------------------------------------------------------
def sync_once(engine):
    """Single polling cycle: fetch config → apply or restore rules."""
    config = fetch_config_with_retry()
    if not config:
        LOGGER.warning("No config available from server or cache; retrying in %ss", POLL_INTERVAL)
        return

    should_block = bool(config.get("active", config.get("blocking_active", False)))
    domains_to_block = sorted(
        set(
            str(d).strip().lower()
            for d in config.get("blockedDomains", config.get("domains", []))
            if str(d).strip()
        )
    )

    LOGGER.info(
        "Fetch response | active=%s sessions=%s domains=%s test_mode=%s engine=%s",
        should_block,
        len(config.get("active_sessions", [])),
        len(domains_to_block),
        config.get("test_mode", TEST_MODE),
        engine.name,
    )

    if domains_to_block:
        LOGGER.info("Blocked domain set from API: %s", ", ".join(domains_to_block))

    global LAST_APPLIED_DOMAINS, LAST_STATE

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
                LOGGER.error("Failed to apply blocking rules. Will retry on next cycle.")
                # Reset state to force retry
                LAST_STATE = None
                LAST_APPLIED_DOMAINS = None
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
    LOGGER.info("=" * 50)
    LOGGER.info("ACADEMIA SHIELD AGENT")
    LOGGER.info("=" * 50)
    LOGGER.info("Server:           http://%s:%s", SERVER_IP, SERVER_PORT)
    LOGGER.info("Agent ID:         %s", AGENT_ID)
    LOGGER.info("Enforcement mode: %s", ENFORCEMENT_MODE)
    LOGGER.info("Test mode:        %s", TEST_MODE)
    LOGGER.info("Poll interval:    %ss", POLL_INTERVAL)
    LOGGER.info("Socket.IO:        %s", "enabled" if SOCKET_ENABLED else "disabled")
    LOGGER.info("Student SAP ID:   %s", STUDENT_SAP_ID or "(not set — logs will use agent hostname)")

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

    # Socket.IO setup
    socket_client = None
    if SOCKET_ENABLED:
        def on_socket_event(data):
            LOGGER.info("Socket event received — forcing immediate sync")
            SYNC_EVENT.set()

        from comms.socket_client import AgentSocketClient
        socket_client = AgentSocketClient(
            server_url=SOCKET_URL,
            agent_id=AGENT_ID,
            on_session_started=on_socket_event,
            on_session_ended=on_socket_event,
        )
        socket_client.connect()

    # Apply immediately on startup to ensure restart reliability
    sync_once(engine)

    # Main polling loop
    global RUNNING
    while RUNNING:
        try:
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
    LOGGER.info("Restoring original system state before shutdown...")
    try:
        engine.shutdown()
        report_to_server("BLOCK_REMOVED")
    finally:
        if socket_client:
            socket_client.disconnect()
        LOGGER.info("Agent stopped.")


if __name__ == "__main__":
    main()
