"""
Academia Shield Agent — HTTP Communication Module

Handles polling the backend for config and reporting blocking activity.
Uses only Python stdlib (urllib).
"""

import json
import socket
import time
import logging
import urllib.parse
import urllib.request
import urllib.error

from config import (
    SERVER_IP,
    SERVER_PORT,
    AGENT_ID,
    STUDENT_SAP_ID,
    REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    TEST_MODE,
    CACHE_FILE,
    USE_HTTPS,
)

LOGGER = logging.getLogger("academia_shield_agent")


# ---------------------------------------------------------------------------
# Config Cache (offline fallback)
# ---------------------------------------------------------------------------
def load_cached_config():
    """Read the last-known-good config from the cache file."""
    import os
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        LOGGER.warning("Cache file is corrupted; ignoring cached config.")
        return None


def save_cached_config(config):
    """Persist config to the cache file."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f)


# ---------------------------------------------------------------------------
# Config Normalisation
# ---------------------------------------------------------------------------
def normalize_config(payload):
    """Normalise the raw API response into a consistent internal format."""
    if isinstance(payload, dict) and "success" in payload and "data" in payload:
        if not payload.get("success"):
            raise RuntimeError(payload.get("message", "Server returned unsuccessful response."))
        payload = payload.get("data") or {}

    if not isinstance(payload, dict):
        raise RuntimeError("Server returned invalid config format.")

    active = bool(payload.get("active", payload.get("blocking_active", False)))
    blocked_domains = payload.get("blockedDomains", payload.get("domains", []))
    blocked_apps = payload.get("blockedApps", payload.get("apps", []))

    return {
        "active": active,
        "blockedDomains": list(blocked_domains or []),
        "blockedApps": list(blocked_apps or []),
        "blocking_active": active,
        "domains": list(blocked_domains or []),
        "apps": list(blocked_apps or []),
        "server_time": payload.get("server_time", ""),
        "active_sessions": list(payload.get("active_sessions", []) or []),
        "test_mode": bool(payload.get("test_mode", TEST_MODE)),
        "device_authorized": bool(payload.get("device_authorized", True)),
    }


# ---------------------------------------------------------------------------
# HTTP Fetch
# ---------------------------------------------------------------------------
def fetch_remote_config_once():
    """Single HTTP GET to the agent config endpoint."""
    protocol = "https" if USE_HTTPS else "http"
    query = urllib.parse.urlencode({
        "deviceId": AGENT_ID,
        "agentId": AGENT_ID,
    })
    url = f"{protocol}://{SERVER_IP}:{SERVER_PORT}/api/agent/config?{query}"
    req = urllib.request.Request(url)

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        data = response.read().decode("utf-8")
        payload = json.loads(data)
        config = normalize_config(payload)
        save_cached_config(config)
        return config


def fetch_config_with_retry():
    """Fetch config with exponential backoff retries, falling back to cache."""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return fetch_remote_config_once()
        except (urllib.error.URLError, socket.timeout, RuntimeError, json.JSONDecodeError) as err:
            LOGGER.warning(
                "Config fetch attempt %s/%s failed: %s",
                attempt,
                RETRY_ATTEMPTS,
                err,
            )
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    LOGGER.warning("Server unreachable after retries; falling back to cached config.")
    return load_cached_config()


# ---------------------------------------------------------------------------
# Activity Reporting
# ---------------------------------------------------------------------------
def report_to_server(action, domains=None):
    """POST blocking activity back to the API so professors see live logs."""
    try:
        protocol = "https" if USE_HTTPS else "http"
        payload = json.dumps({
            "agentId": AGENT_ID,
            "sapId": STUDENT_SAP_ID or None,
            "action": action,
            "domains": list(domains or []),
        }).encode("utf-8")

        url = f"{protocol}://{SERVER_IP}:{SERVER_PORT}/api/agent/report"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
            logged = data.get("data", {}).get("logged", 0)
            LOGGER.info("Reported %s to server | logged=%s entries", action, logged)

    except Exception as err:
        # Reporting is best-effort; never block the main enforcement loop.
        LOGGER.warning("Report to server failed (non-fatal): %s", err)
