"""
Academia Shield Agent — Configuration Module

All environment variables and constants used by the agent.
"""

import os
import socket

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def parse_bool(value, default=False):
    """Convert an environment variable string to a boolean."""
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Core Settings
# ---------------------------------------------------------------------------
TEST_MODE = parse_bool(os.getenv("TEST_MODE"), True)
SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1" if TEST_MODE else "192.168.137.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))
POLL_INTERVAL = max(5, min(int(os.getenv("POLL_INTERVAL", "8")), 10))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "5"))
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = int(os.getenv("RETRY_BACKOFF_SECONDS", "2"))

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
AGENT_ID = os.getenv("AGENT_ID", socket.gethostname())
STUDENT_SAP_ID = os.getenv("STUDENT_SAP_ID", "").strip()

# ---------------------------------------------------------------------------
# Enforcement Mode
# ---------------------------------------------------------------------------
#   "HOSTS" — Prototype mode (modify OS hosts file)
#   "DNS"   — Production mode (local DNS resolver)
ENFORCEMENT_MODE = os.getenv("ENFORCEMENT_MODE", "HOSTS").strip().upper()

# ---------------------------------------------------------------------------
# DNS Engine Settings (used when ENFORCEMENT_MODE=DNS)
# ---------------------------------------------------------------------------
DNS_LISTEN_PORT = int(os.getenv("DNS_LISTEN_PORT", "53"))
DNS_UPSTREAM = os.getenv("DNS_UPSTREAM", "8.8.8.8")
DNS_UPSTREAM_PORT = int(os.getenv("DNS_UPSTREAM_PORT", "53"))

# ---------------------------------------------------------------------------
# Socket.IO Settings
# ---------------------------------------------------------------------------
SOCKET_ENABLED = parse_bool(os.getenv("SOCKET_ENABLED"), False)
SOCKET_URL = os.getenv("SOCKET_URL", f"http://{SERVER_IP}:{SERVER_PORT}")

# ---------------------------------------------------------------------------
# File Paths
# ---------------------------------------------------------------------------
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(AGENT_DIR, "last_config.json")
BACKUP_FILE = os.path.join(AGENT_DIR, "hosts.backup")
DNS_BACKUP_FILE = os.path.join(AGENT_DIR, "dns_backup.json")
LOG_FILE = os.path.join(AGENT_DIR, "agent.log")

# ---------------------------------------------------------------------------
# Hosts Engine Constants
# ---------------------------------------------------------------------------
MARKER_START = "# ACADEMIA_SHIELD_START"
MARKER_END = "# ACADEMIA_SHIELD_END"
REDIRECT_IP = "127.0.0.1"
