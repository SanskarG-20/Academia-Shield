"""
Academia Shield Agent — Configuration Module

All environment variables and constants used by the agent.

env_loader.load_env() must run before this module is imported, because every
value below is read from os.environ at import time.
"""

import os
import socket
import sys

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
TEST_MODE = parse_bool(os.getenv("TEST_MODE"), not getattr(sys, "frozen", False))

if API_URL:
    # Parse API_URL (e.g., https://academia-shield-api.onrender.com)
    from urllib.parse import urlparse
    parsed = urlparse(API_URL)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RuntimeError("API_URL must be a valid HTTP or HTTPS URL")
    if parsed.scheme != "https" and (getattr(sys, "frozen", False) or not TEST_MODE):
        raise RuntimeError("Packaged or production agent requires HTTPS API_URL")
    SERVER_IP = parsed.hostname
    SERVER_PORT = parsed.port or (443 if parsed.scheme == "https" else 80)
    USE_HTTPS = parsed.scheme == "https"
else:
    if getattr(sys, "frozen", False) or not TEST_MODE:
        raise RuntimeError("Packaged or production agent requires HTTPS API_URL")
    # Fallback to individual environment variables
    SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1" if TEST_MODE else "192.168.137.1")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))
    USE_HTTPS = parse_bool(os.getenv("USE_HTTPS"), False)

# Poll interval: floor of 5s to avoid hammering the API, ceiling of 300s so a
# typo cannot leave an agent effectively unmanaged. The shipped
# .env.production uses 30s to stay light on the free Render tier.
POLL_INTERVAL = max(5, min(int(os.getenv("POLL_INTERVAL", "8")), 300))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = int(os.getenv("RETRY_BACKOFF_SECONDS", "2"))

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
AGENT_ID = os.getenv("AGENT_ID", socket.gethostname())

# ---------------------------------------------------------------------------
# Enforcement Mode
# ---------------------------------------------------------------------------
#   "HOSTS" — managed hosts-file entries (the only active enforcement mode)
#   "DNS"   — legacy setting, now falls back to HOSTS for device safety
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
_SOCKET_SCHEME = "https" if USE_HTTPS else "http"
_SOCKET_DEFAULT_PORT = 443 if USE_HTTPS else 80
# Omit the port for standard HTTP/HTTPS so the URL stays valid behind hosts
# like Render that terminate TLS on 443.
if SERVER_PORT == _SOCKET_DEFAULT_PORT:
    _SOCKET_DEFAULT_URL = f"{_SOCKET_SCHEME}://{SERVER_IP}"
else:
    _SOCKET_DEFAULT_URL = f"{_SOCKET_SCHEME}://{SERVER_IP}:{SERVER_PORT}"
SOCKET_URL = os.getenv("SOCKET_URL", _SOCKET_DEFAULT_URL)
if getattr(sys, "frozen", False):
    from urllib.parse import urlparse
    socket_target = urlparse(SOCKET_URL)
    if (socket_target.scheme != "https" or socket_target.hostname != SERVER_IP
            or (socket_target.port or 443) != SERVER_PORT):
        raise RuntimeError("Packaged agent Socket.IO URL must use the HTTPS API origin")

# ---------------------------------------------------------------------------
# File Paths
# ---------------------------------------------------------------------------
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_data_dir():
    """
    Directory for mutable state: cached config, hosts backup, DNS backup, log.

    A PyInstaller onefile build unpacks sources into a temp dir that is deleted
    on exit, so AGENT_DIR must never be used for state in a frozen build — the
    hosts backup has to outlive the process for restore-on-restart to work.
    Order: AGENT_DATA_DIR override, then stable ProgramData for frozen Windows
    builds, then next to the .exe, then AGENT_DIR.
    """
    override = os.getenv("AGENT_DATA_DIR", "").strip()
    if override:
        candidate = override
    elif getattr(sys, "frozen", False) and sys.platform == "win32":
        candidate = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "AcademiaShield")
    elif getattr(sys, "frozen", False):
        candidate = os.path.dirname(os.path.abspath(sys.executable))
    else:
        candidate = AGENT_DIR

    try:
        os.makedirs(candidate, exist_ok=True)
        if getattr(sys, "frozen", False) and sys.platform == "win32":
            if os.path.normcase(os.path.realpath(candidate)) != os.path.normcase(os.path.abspath(candidate)):
                raise OSError("Agent state directory is redirected")
        probe = os.path.join(candidate, ".write-test")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("")
        os.remove(probe)
        return candidate
    except OSError:
        if getattr(sys, "frozen", False) and sys.platform == "win32":
            raise RuntimeError("Cannot use stable ProgramData for agent state; refusing enforcement")
        # Last resort: a stable per-machine location that is always writable
        # for an elevated service.
        fallback = os.path.join(
            os.environ.get("ProgramData", os.path.expanduser("~")), "AcademiaShield"
        )
        try:
            os.makedirs(fallback, exist_ok=True)
            return fallback
        except OSError:
            return AGENT_DIR


DATA_DIR = _resolve_data_dir()
CACHE_FILE = os.path.join(DATA_DIR, "last_config.json")
BACKUP_FILE = os.path.join(DATA_DIR, "hosts.backup")
DNS_BACKUP_FILE = os.path.join(DATA_DIR, "dns_backup.json")
LOG_FILE = os.path.join(DATA_DIR, "agent.log")
STOP_FILE = os.path.join(DATA_DIR, "stop.request")

# ---------------------------------------------------------------------------
# Hosts Engine Constants
# ---------------------------------------------------------------------------
MARKER_START = "# ACADEMIA_SHIELD_START"
MARKER_END = "# ACADEMIA_SHIELD_END"
REDIRECT_IP = "127.0.0.1"
