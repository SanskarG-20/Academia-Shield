"""
Academia Shield Agent — Hosts File Enforcement Engine (Prototype Mode)

Blocks domains by writing entries to the OS hosts file between
managed marker comments. Preserves all existing system entries.
"""

import os
import platform
import sys
import tempfile
import urllib.parse
import logging
from typing import List

from enforcement.base import EnforcementEngine
from config import MARKER_START, MARKER_END, REDIRECT_IP, BACKUP_FILE

LOGGER = logging.getLogger("academia_shield_agent")


# ---------------------------------------------------------------------------
# Hosts file path (OS-dependent)
# ---------------------------------------------------------------------------
def _get_hosts_path():
    system = platform.system()
    if system == "Windows":
        return r"C:\Windows\System32\drivers\etc\hosts"
    if system in ("Darwin", "Linux"):
        return "/etc/hosts"

    LOGGER.error("Unsupported OS. Cannot determine hosts file path.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Domain normalisation helpers
# ---------------------------------------------------------------------------
def normalize_domain(domain):
    """Clean a raw domain string (strip protocol, path, port, whitespace)."""
    value = str(domain or "").strip().lower()
    if not value:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urllib.parse.urlparse(value)
        value = parsed.netloc.strip().lower()

    value = value.split("/")[0].split(":")[0].strip()
    return value


def normalize_domain_list(domains):
    """Deduplicate and normalise a list of domains."""
    seen = set()
    normalized = []

    for domain in domains:
        cleaned = normalize_domain(domain)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return normalized


# ---------------------------------------------------------------------------
# Hosts file manipulation helpers
# ---------------------------------------------------------------------------
def _read_hosts_lines(hosts_path):
    with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.readlines()


def _remove_managed_block(lines):
    """Strip the managed block (between markers) from hosts lines."""
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


def _ensure_backup_exists(hosts_lines):
    """Create a one-time backup of the pristine hosts file. Never overwrites."""
    if os.path.exists(BACKUP_FILE):
        return True

    # A3 FIX: Strip any existing managed block before backing up so the backup is always pristine.
    pristine_lines = _remove_managed_block(hosts_lines)

    try:
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            f.writelines(pristine_lines)
        LOGGER.info("Backup created: %s", BACKUP_FILE)
        return True
    except Exception as err:
        LOGGER.error("Could not create hosts backup; skipping update for safety: %s", err)
        return False


def _build_managed_block(domains):
    """Build the marker-delimited block of hosts entries."""
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


def _log_dns_flush_instruction():
    if platform.system() == "Windows":
        LOGGER.info("Please run: ipconfig /flushdns")
    else:
        LOGGER.info("DNS cache may still contain old entries; flush DNS manually if needed.")


# ---------------------------------------------------------------------------
# Engine class
# ---------------------------------------------------------------------------
class HostsEnforcementEngine(EnforcementEngine):
    """Prototype enforcement engine that modifies the OS hosts file."""

    def __init__(self):
        self._hosts_path = _get_hosts_path()

    @property
    def name(self) -> str:
        return "Hosts File Engine"

    def is_available(self) -> bool:
        """Hosts engine is available on all supported OSes."""
        try:
            with open(self._hosts_path, "r", encoding="utf-8", errors="ignore"):
                pass
            return True
        except PermissionError:
            LOGGER.warning("Hosts file not readable — run as administrator")
            return False
        except Exception:
            return False

    def apply_rules(self, domains: List[str]) -> bool:
        """Write blocked domains to the hosts file."""
        return self._apply_domains_to_hosts(domains)

    def restore_rules(self) -> bool:
        """Remove the managed block from the hosts file."""
        return self._apply_domains_to_hosts([])

    def shutdown(self) -> None:
        """Cleanup on agent shutdown."""
        self.restore_rules()

    # -- internal implementation (extracted from original agent.py) ----------

    def _apply_domains_to_hosts(self, domains):
        try:
            current_lines = _read_hosts_lines(self._hosts_path)
        except PermissionError:
            LOGGER.error("Run as administrator to apply blocking")
            return False
        except Exception as err:
            LOGGER.error("Failed to read hosts file safely: %s", err)
            return False

        preserved_lines = _remove_managed_block(current_lines)
        managed_block = _build_managed_block(domains)

        new_lines = list(preserved_lines)
        if managed_block:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] = new_lines[-1] + "\n"
            if new_lines and new_lines[-1].strip() != "":
                new_lines.append("\n")
            new_lines.extend(managed_block)

        if not _ensure_backup_exists(current_lines):
            return False

        try:
            # A1 FIX: Atomic write — write to temp file, then os.replace.
            hosts_dir = os.path.dirname(self._hosts_path)
            fd, tmp_path = tempfile.mkstemp(dir=hosts_dir, suffix=".tmp", prefix="hosts_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                os.replace(tmp_path, self._hosts_path)
            except BaseException:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            LOGGER.info(
                "Hosts updated safely. Managed domains=%s",
                len(managed_block) - 2 if managed_block else 0,
            )
            _log_dns_flush_instruction()
            return True
        except PermissionError:
            LOGGER.error("Run as administrator to apply blocking")
            return False
        except Exception as err:
            LOGGER.error(
                "Hosts update failed; system entries preserved in memory and backup remains available: %s",
                err,
            )
            return False
