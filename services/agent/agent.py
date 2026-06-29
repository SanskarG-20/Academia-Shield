import os
import sys
import time
import json
import socket
import platform
import urllib.parse
import urllib.request
import urllib.error
import logging
from datetime import datetime

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


TEST_MODE = parse_bool(os.getenv("TEST_MODE"), True)
SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1" if TEST_MODE else "192.168.137.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))
POLL_INTERVAL = max(5, min(int(os.getenv("POLL_INTERVAL", "8")), 10))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "5"))
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = int(os.getenv("RETRY_BACKOFF_SECONDS", "2"))

AGENT_ID = os.getenv("AGENT_ID", socket.gethostname())

CACHE_FILE = "last_config.json"
BACKUP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hosts.backup")
LOG_FILE = "agent.log"
MARKER_START = "# ACADEMIA_SHIELD_START"
MARKER_END = "# ACADEMIA_SHIELD_END"
REDIRECT_IP = "127.0.0.1"


def setup_logger():
    logger = logging.getLogger("academia_shield_agent")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


LOGGER = setup_logger()


# -----------------------------------------------------------------------------
# HOSTS FILE PATH
# -----------------------------------------------------------------------------
def get_hosts_path():
    system = platform.system()
    if system == "Windows":
        return r"C:\Windows\System32\drivers\etc\hosts"
    if system in ("Darwin", "Linux"):
        return "/etc/hosts"

    LOGGER.error("Unsupported OS. Cannot determine hosts file path.")
    sys.exit(1)


HOSTS_FILE = get_hosts_path()


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_cached_config():
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as cache_file:
            return json.load(cache_file)
    except json.JSONDecodeError:
        LOGGER.warning("Cache file is corrupted; ignoring cached config.")
        return None


def save_cached_config(config):
    with open(CACHE_FILE, "w", encoding="utf-8") as cache_file:
        json.dump(config, cache_file)


def normalize_config(payload):
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


def fetch_remote_config_once():
    query = urllib.parse.urlencode({
        "deviceId": AGENT_ID,
        "agentId": AGENT_ID,
    })
    url = f"http://{SERVER_IP}:{SERVER_PORT}/api/agent/config?{query}"
    req = urllib.request.Request(url)

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        data = response.read().decode("utf-8")
        payload = json.loads(data)
        config = normalize_config(payload)
        save_cached_config(config)
        return config


def fetch_config_with_retry():
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


def read_hosts_lines():
    with open(HOSTS_FILE, "r", encoding="utf-8", errors="ignore") as hosts_file:
        return hosts_file.readlines()


def ensure_backup_exists(hosts_lines):
    if os.path.exists(BACKUP_FILE):
        return True

    try:
        with open(BACKUP_FILE, "w", encoding="utf-8") as backup_file:
            backup_file.writelines(hosts_lines)
        LOGGER.info("Backup created: %s", BACKUP_FILE)
        return True
    except Exception as err:
        LOGGER.error("Could not create hosts backup; skipping update for safety: %s", err)
        return False


def normalize_domain(domain):
    value = str(domain or "").strip().lower()
    if not value:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urllib.parse.urlparse(value)
        value = parsed.netloc.strip().lower()

    value = value.split("/")[0].split(":")[0].strip()
    return value


def normalize_domain_list(domains):
    seen = set()
    normalized = []

    for domain in domains:
        cleaned = normalize_domain(domain)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return normalized


def remove_managed_block(lines):
    cleaned = []
    inside_managed_block = False

    for line in lines:
        stripped = line.strip()

        if stripped == MARKER_START:
            inside_managed_block = True
            continue

        if stripped == MARKER_END:
            inside_managed_block = False
            continue

        if not inside_managed_block:
            cleaned.append(line)

    if inside_managed_block:
        LOGGER.warning("Managed block start marker found without end marker; cleaned stale managed block.")

    return cleaned


def build_managed_block(domains):
    unique_domains = set()
    for domain in normalize_domain_list(domains):
        unique_domains.add(domain)
        if not domain.startswith("www."):
            unique_domains.add(f"www.{domain}")

    if not unique_domains:
        return []

    block = [f"{MARKER_START}\n"]
    for domain in sorted(unique_domains):
        block.append(f"{REDIRECT_IP} {domain}\n")
    block.append(f"{MARKER_END}\n")
    return block


def log_dns_flush_instruction():
    if platform.system() == "Windows":
        LOGGER.info("Please run: ipconfig /flushdns")
    else:
        LOGGER.info("DNS cache may still contain old entries; flush DNS manually if needed.")


def apply_domains_to_hosts(domains):
    try:
        current_lines = read_hosts_lines()
    except PermissionError:
        LOGGER.error("Run as administrator to apply blocking")
        return False
    except Exception as err:
        LOGGER.error("Failed to read hosts file safely: %s", err)
        return False

    preserved_lines = remove_managed_block(current_lines)
    managed_block = build_managed_block(domains)

    new_lines = list(preserved_lines)
    if managed_block:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("\n")
        new_lines.extend(managed_block)

    if not ensure_backup_exists(current_lines):
        return False

    try:
        with open(HOSTS_FILE, "w", encoding="utf-8") as hosts_file:
            hosts_file.writelines(new_lines)
        LOGGER.info("Hosts updated safely. Managed domains=%s", len(managed_block) - 2 if managed_block else 0)
        LOGGER.info("Hosts updated successfully")
        log_dns_flush_instruction()
        return True
    except PermissionError:
        LOGGER.error("Run as administrator to apply blocking")
        return False
    except Exception as err:
        LOGGER.error("Hosts update failed; system entries preserved in memory and backup remains available: %s", err)
        return False


def block_domains(domains):
    normalized_domains = normalize_domain_list(domains)
    LOGGER.info("Domains fetched from API (%s): %s", len(normalized_domains), ", ".join(normalized_domains) if normalized_domains else "(none)")
    LOGGER.info("Rewriting hosts file with domains: %s", normalized_domains)
    apply_domains_to_hosts(normalized_domains)


def unblock_domains():
    LOGGER.info("Restore triggered: removing managed hosts entries.")
    apply_domains_to_hosts([])


def sync_hosts_once():
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
        "Fetch response | active=%s sessions=%s domains=%s test_mode=%s",
        should_block,
        len(config.get("active_sessions", [])),
        len(domains_to_block),
        config.get("test_mode", TEST_MODE),
    )
    if domains_to_block:
        LOGGER.info("Blocked domain set from API: %s", ", ".join(domains_to_block))

    if should_block:
        block_domains(domains_to_block)
    else:
        LOGGER.info("STANDBY | no active blocking session")
        unblock_domains()


# -----------------------------------------------------------------------------
# MAIN LOOP
# -----------------------------------------------------------------------------
def main():
    LOGGER.info("----------------------------------------")
    LOGGER.info("ACADEMIA SHIELD AGENT")
    LOGGER.info("Server: http://%s:%s", SERVER_IP, SERVER_PORT)
    LOGGER.info("Agent ID: %s", AGENT_ID)
    LOGGER.info("Test mode: %s", TEST_MODE)
    LOGGER.info("Polling interval: %ss", POLL_INTERVAL)
    LOGGER.info("Hosts file: %s", HOSTS_FILE)
    LOGGER.info("Backup file: %s", BACKUP_FILE)
    LOGGER.info("----------------------------------------")

    # Apply immediately on startup to ensure restart reliability.
    sync_hosts_once()

    while True:
        try:
            sync_hosts_once()

            time.sleep(POLL_INTERVAL)

        except PermissionError:
            LOGGER.error("Permission denied while updating hosts file.")
            LOGGER.error("Run as administrator to apply blocking")
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            LOGGER.info("Interrupted. Cleaning up managed hosts entries...")
            try:
                unblock_domains()
            finally:
                LOGGER.info("Agent stopped.")
            break
        except Exception as err:
            LOGGER.exception("Unexpected runtime error: %s", err)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
