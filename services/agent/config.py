"""
Academia Shield Agent — Configuration Module

All environment variables and constants used by the agent.
"""

import os
import platform
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
# Support both full API_URL or individual SERVER_IP/SERVER_PORT
API_URL = os.getenv("API_URL", "").strip()
TEST_MODE = parse_bool(os.getenv("TEST_MODE"), True)

if API_URL:
    # Parse API_URL (e.g., https://academia-shield-api.onrender.com)
    from urllib.parse import urlparse
    parsed = urlparse(API_URL)
    SERVER_IP = parsed.hostname or "127.0.0.1"
    SERVER_PORT = parsed.port or (443 if parsed.scheme == "https" else 80)
    USE_HTTPS = parsed.scheme == "https"
else:
    # Fallback to individual environment variables
    SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1" if TEST_MODE else "192.168.137.1")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))
    USE_HTTPS = parse_bool(os.getenv("USE_HTTPS"), False)

POLL_INTERVAL = max(5, min(int(os.getenv("POLL_INTERVAL", "8")), 10))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
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
LOG_FILE = os.path.join(AGENT_DIR, "agent.log")

# The DNS journal must survive crashes, reboots and different user accounts,
# so it lives in a machine-wide location instead of next to the executable.
def _machine_state_dir():
    if platform.system() == "Windows":
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return os.path.join(program_data, "AcademiaShield")
    return os.path.expanduser("~/.academia_shield")


DNS_STATE_DIR = _machine_state_dir()
DNS_BACKUP_FILE = os.path.join(DNS_STATE_DIR, "dns_backup.json")

# ---------------------------------------------------------------------------
# Hosts Engine Constants
# ---------------------------------------------------------------------------
MARKER_START = "# ACADEMIA_SHIELD_START"
MARKER_END = "# ACADEMIA_SHIELD_END"
REDIRECT_IP = "127.0.0.1"
