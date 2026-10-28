"""
Academia Shield Agent — Hosts File Enforcement Engine (Prototype Mode)

Blocks domains by writing entries to the OS hosts file between
managed marker comments. Preserves all existing system entries.
"""

import os
import platform
import shutil
import sys
import tempfile
import urllib.parse
import logging
import re
import ipaddress
from typing import List

from enforcement.base import EnforcementEngine
from config import MARKER_START, MARKER_END, REDIRECT_IP, BACKUP_FILE, SERVER_IP

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
    if len(value) > 253 or "." not in value or value in {"localhost", SERVER_IP.lower()}:
        return ""
    if value.endswith((".local", ".localhost", ".internal", ".lan", ".home", ".arpa", ".test", ".invalid")):
        return ""
    try:
        ipaddress.ip_address(value)
        return ""
    except ValueError:
        pass
    if any(len(label) > 63 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
           for label in value.split(".")):
        return ""
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
    # Latin-1 is a reversible byte mapping. Never discard an existing hosts
    # byte just because the file is not valid UTF-8.
    with open(hosts_path, "r", encoding="latin-1", newline="") as f:
        return f.readlines()


def _remove_managed_block(lines):
    """Strip the managed block (between markers) from hosts lines."""
    cleaned = []
    inside_managed_block = False
    seen_block = False

    for line in lines:
        stripped = line.strip()

        if stripped == MARKER_START:
            if inside_managed_block or seen_block:
                raise ValueError("Duplicate managed hosts marker; refusing to alter hosts file")
            inside_managed_block = True
            seen_block = True
            continue

        if stripped == MARKER_END:
            if not inside_managed_block:
                raise ValueError("Unmatched managed hosts marker; refusing to alter hosts file")
            inside_managed_block = False
            continue

        if not inside_managed_block:
            cleaned.append(line)

    if inside_managed_block:
        raise ValueError("Unclosed managed hosts block; refusing to alter hosts file")

    return cleaned


def _ensure_backup_exists(hosts_lines):
    """Create a one-time backup of the pristine hosts file. Never overwrites."""
    if os.path.lexists(BACKUP_FILE):
        if os.path.islink(BACKUP_FILE) or not os.path.isfile(BACKUP_FILE):
            LOGGER.error("Hosts backup path is not a regular file; refusing update")
            return False
        return True

    # A3 FIX: Strip any existing managed block before backing up so the backup is always pristine.
    pristine_lines = _remove_managed_block(hosts_lines)

    created = False
    try:
        with open(BACKUP_FILE, "x", encoding="latin-1", newline="") as f:
            created = True
            f.writelines(pristine_lines)
            f.flush()
            os.fsync(f.fileno())
        LOGGER.info("Backup created: %s", BACKUP_FILE)
        return True
    except Exception as err:
        if created:
            try:
                os.remove(BACKUP_FILE)
            except OSError:
                pass
        LOGGER.error("Could not create hosts backup; skipping update for safety: %s", err)
        return False


def _build_managed_block(domains, newline="\n"):
    """Build the marker-delimited block of hosts entries."""
    unique_domains = set()
    for domain in normalize_domain_list(domains):
        unique_domains.add(domain)
        if not domain.startswith("www."):
            unique_domains.add(f"www.{domain}")

    if not unique_domains:
        return []

    block = [f"{MARKER_START}{newline}"]
    for domain in sorted(unique_domains):
        block.append(f"{REDIRECT_IP} {domain}{newline}")
    block.append(f"{MARKER_END}{newline}")
    return block


def _replace_hosts_file(original, replacement):
    """Replace atomically while preserving Windows hosts ACLs/attributes."""
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes
        replace = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
        replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                            wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
        replace.restype = wintypes.BOOL
        if not replace(original, replacement, None, 0, None, None):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(replacement, original)


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
        if os.path.islink(self._hosts_path):
            LOGGER.error("Hosts path is a symbolic link; refusing to alter it")
            return False
        try:
            initial_stat = os.stat(self._hosts_path)
            current_lines = _read_hosts_lines(self._hosts_path)
        except PermissionError:
            LOGGER.error("Run as administrator to apply blocking")
            return False
        except Exception as err:
            LOGGER.error("Failed to read hosts file safely: %s", err)
            return False

        try:
            preserved_lines = _remove_managed_block(current_lines)
        except ValueError as error:
            LOGGER.error("%s", error)
            return False
        newline = "\r\n" if any(line.endswith("\r\n") for line in current_lines) else "\n"
        needs_separator = bool(preserved_lines and not preserved_lines[-1].endswith(("\n", "\r")))
        if domains and needs_separator:
            LOGGER.error("Hosts file has no final newline; refusing to append a managed block")
            return False
        managed_block = _build_managed_block(domains, newline)

        new_lines = list(preserved_lines)
        if managed_block:
            new_lines.extend(managed_block)

        if new_lines == current_lines:
            return True

        if not _ensure_backup_exists(current_lines):
            return False

        try:
            # Atomic replacement keeps the original intact if writing fails.
            hosts_dir = os.path.dirname(self._hosts_path)
            fd, tmp_path = tempfile.mkstemp(dir=hosts_dir, suffix=".tmp", prefix="hosts_")
            try:
                with os.fdopen(fd, "w", encoding="latin-1", newline="") as f:
                    f.writelines(new_lines)
                    f.flush()
                    os.fsync(f.fileno())
                latest_stat = os.stat(self._hosts_path)
                if (latest_stat.st_mtime_ns != initial_stat.st_mtime_ns
                        or latest_stat.st_size != initial_stat.st_size):
                    raise RuntimeError("Hosts file changed concurrently; retrying later")
                shutil.copystat(self._hosts_path, tmp_path)
                _replace_hosts_file(self._hosts_path, tmp_path)
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
