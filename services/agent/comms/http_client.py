"""
Academia Shield Agent — HTTP Communication Module

Handles polling the backend for config and reporting blocking activity.
Uses only Python stdlib (urllib).
"""

import json
import hmac
import hashlib
import socket
import time
import logging
import urllib.parse
import urllib.request
import urllib.error
import config
from credentials import load_credential, device_id

from config import (
    SERVER_IP,
    SERVER_PORT,
    AGENT_ID,
    REQUEST_TIMEOUT,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    TEST_MODE,
    CACHE_FILE,
    USE_HTTPS,
)

LOGGER = logging.getLogger("academia_shield_agent")
MAX_POLICY_BYTES = 1_000_000
MAX_DOMAINS = 200
MAX_APPS = 50


class InvalidPolicyError(Exception):
    """Authenticated server response cannot be used or cached."""


def _auth_headers(extra=None):
    """Build request headers using this installation's OS-stored credential."""
    headers = dict(extra or {})
    credential = load_credential()
    if not credential:
        raise RuntimeError("Device is not enrolled")
    headers["Authorization"] = f"Device {credential}"
    return headers


# ---------------------------------------------------------------------------
# Config Cache (offline fallback)
# ---------------------------------------------------------------------------
def _check_and_expire_cached_config(cached_cfg):
    """Reject cache lacking identity, explicit policy expiry, or valid session end."""
    from datetime import datetime, timezone
    if not isinstance(cached_cfg, dict):
        return None
    if cached_cfg.get("deviceId") != device_id():
        return None
    expiry = cached_cfg.get("expiresAt")
    if not isinstance(expiry, str) or not expiry:
        return None
    try:
        expires_at = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            return None
        if expires_at <= datetime.now(timezone.utc):
            return None
    except (ValueError, TypeError):
        return None
    active_sessions = cached_cfg.get("active_sessions", [])
    if not isinstance(active_sessions, list) or any(not isinstance(s, dict) for s in active_sessions):
        return None
    domains = cached_cfg.get("blockedDomains", [])
    apps = cached_cfg.get("blockedApps", [])
    if (not isinstance(domains, list) or len(domains) > MAX_DOMAINS
            or not isinstance(apps, list) or len(apps) > MAX_APPS
            or any(not isinstance(value, str) or len(value) > 253 for value in domains)
            or any(not isinstance(value, str) or len(value) > 128 for value in apps)):
        return None
    if cached_cfg.get("active") and not active_sessions:
        return None

    now = datetime.now(timezone.utc)
    valid_sessions = []
    for s in active_sessions:
        ends_at_str = s.get("ends_at")
        if not isinstance(ends_at_str, str) or not ends_at_str:
            continue
        try:
            clean_str = ends_at_str.replace("Z", "+00:00")
            ends_at = datetime.fromisoformat(clean_str)
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=timezone.utc)
            if ends_at > now:
                valid_sessions.append(s)
        except Exception as err:
            LOGGER.debug("Failed parsing session ends_at '%s': %s", ends_at_str, err)

    if active_sessions and not valid_sessions:
        return None
    return cached_cfg


def load_cached_config():
    """Read the last-known-good config from the cache file."""
    import os
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        if os.path.getsize(CACHE_FILE) > MAX_POLICY_BYTES:
            LOGGER.warning("Cached policy is oversized; ignoring it")
            return None
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            wrapper = json.load(f)
            credential = load_credential()
            if not credential or not isinstance(wrapper, dict):
                return None
            cfg = wrapper.get("policy")
            mac = wrapper.get("mac", "")
            if not isinstance(cfg, dict) or not isinstance(mac, str):
                return None
            expected = hmac.new(credential.encode(), json.dumps(cfg, sort_keys=True).encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, expected):
                return None
            cfg["is_cached"] = True
            return _check_and_expire_cached_config(cfg)
    except (json.JSONDecodeError, OSError, TypeError, ValueError, AttributeError, UnicodeError):
        LOGGER.warning("Cache file is corrupted; ignoring cached config.")
        return None


def save_cached_config(config):
    """Persist config to the cache file."""
    import os
    if not config.get("active"):
        try:
            os.remove(CACHE_FILE)
        except FileNotFoundError:
            pass
        except OSError as error:
            LOGGER.warning("Could not remove cached policy: %s", error)
        return
    credential = load_credential()
    if not credential or not _check_and_expire_cached_config(config):
        return
    mac = hmac.new(credential.encode(), json.dumps(config, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    import tempfile
    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(CACHE_FILE), prefix="policy-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"policy": config, "mac": mac}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, CACHE_FILE)
    except OSError as error:
        LOGGER.warning("Could not persist cached policy: %s", error)
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass


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
    active_sessions = payload.get("active_sessions", [])
    if (not isinstance(blocked_domains, list) or not isinstance(blocked_apps, list)
            or not isinstance(active_sessions, list)):
        raise RuntimeError("Server returned invalid policy lists")
    if (len(blocked_domains) > MAX_DOMAINS or len(blocked_apps) > MAX_APPS
            or any(not isinstance(value, str) or len(value) > 253 for value in blocked_domains)
            or any(not isinstance(value, str) or len(value) > 128 for value in blocked_apps)):
        raise RuntimeError("Server policy exceeds safe size limits")

    return {
        "active": active,
        "blockedDomains": list(blocked_domains or []),
        "blockedApps": list(blocked_apps or []),
        "blocking_active": active,
        "domains": list(blocked_domains or []),
        "apps": list(blocked_apps or []),
        "server_time": payload.get("server_time", ""),
        "active_sessions": active_sessions,
        "deviceId": payload.get("deviceId"),
        "issuedAt": payload.get("issuedAt"),
        "expiresAt": payload.get("expiresAt"),
        "test_mode": bool(payload.get("test_mode", TEST_MODE)),
        "device_authorized": bool(payload.get("device_authorized", True)),
    }


# ---------------------------------------------------------------------------
# HTTP Fetch
# ---------------------------------------------------------------------------
def fetch_remote_config_once():
    """Single HTTP GET to the agent config endpoint."""
    protocol = "https" if USE_HTTPS else "http"
    url = f"{protocol}://{SERVER_IP}:{SERVER_PORT}/api/agent/config"
    req = urllib.request.Request(url, headers=_auth_headers())

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        data = response.read(MAX_POLICY_BYTES + 1)
        if len(data) > MAX_POLICY_BYTES:
            raise InvalidPolicyError("Server policy response is too large")
        data = data.decode("utf-8")
        payload = json.loads(data)
        try:
            config = normalize_config(payload)
        except RuntimeError as error:
            raise InvalidPolicyError(str(error)) from error
        if config["deviceId"] != device_id():
            raise InvalidPolicyError("Policy belongs to another device")
        if config["active"] and not _check_and_expire_cached_config(config):
            raise InvalidPolicyError("Policy is expired or invalid")
        save_cached_config(config)
        return config


def fetch_config_with_retry():
    """Fetch config with exponential backoff retries, falling back to cache."""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return fetch_remote_config_once()
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                LOGGER.warning("Device authorization rejected; restoring local policy")
                save_cached_config({"active": False})
                return None
            LOGGER.warning("Config fetch failed: HTTP %s", err.code)
        except InvalidPolicyError as err:
            LOGGER.warning("Rejecting invalid server policy: %s", err)
            save_cached_config({"active": False})
            return None
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
            "action": action,
            "domains": list(domains or []),
        }).encode("utf-8")

        url = f"{protocol}://{SERVER_IP}:{SERVER_PORT}/api/agent/report"
        req = urllib.request.Request(
            url,
            data=payload,
            headers=_auth_headers({"Content-Type": "application/json"}),
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
            logged = data.get("data", {}).get("logged", 0)
            LOGGER.info("Reported %s to server | logged=%s entries", action, logged)

    except Exception as err:
        # Reporting is best-effort; never block the main enforcement loop.
        LOGGER.warning("Report to server failed (non-fatal): %s", err)


# ---------------------------------------------------------------------------
# Heartbeat / Telemetry
# ---------------------------------------------------------------------------
def send_heartbeat(active_app="Unknown", status="online"):
    """POST periodic heartbeat telemetry to the backend (best-effort)."""
    try:
        protocol = "https" if USE_HTTPS else "http"
        payload = json.dumps({
            "activeApp": active_app,
            "status": status,
        }).encode("utf-8")

        url = f"{protocol}://{SERVER_IP}:{SERVER_PORT}/api/agent/heartbeat"
        req = urllib.request.Request(
            url,
            data=payload,
            headers=_auth_headers({"Content-Type": "application/json"}),
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
            LOGGER.debug("Heartbeat sent | sessions=%s", data.get("data", {}).get("sessions", 0))

    except Exception as err:
        LOGGER.debug("Heartbeat failed (non-fatal): %s", err)


def send_activity_batch(events):
    """POST batched activity events to the backend (best-effort)."""
    if not events:
        return

    try:
        payload = json.dumps({
            "events": events,
        }).encode("utf-8")

        protocol = "https" if USE_HTTPS else "http"
        url = f"{protocol}://{SERVER_IP}:{SERVER_PORT}/api/agent/activity"
        req = urllib.request.Request(
            url,
            data=payload,
            headers=_auth_headers({"Content-Type": "application/json"}),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            LOGGER.debug("Activity batch sent: %d events, status %s", len(events), resp.status)
    except Exception as err:
        LOGGER.debug("Activity batch failed (non-fatal): %s", err)
