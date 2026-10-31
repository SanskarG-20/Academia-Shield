"""
Windows Network Adapter DNS Configuration Adapter.

Provides explicit administrator-approved network adapter DNS configuration pointing to
the local resolver, a crash-safe machine-wide state journal, continuous drift detection,
and verified restoration.

Safety invariants:
- Only the physical adapter carrying the IPv4 default route is redirected. Virtual,
  host-only, VPN and disconnected adapters are never touched.
- The journal is written atomically BEFORE the first adapter change and is only deleted
  after every changed adapter has been verified back to its original state.
- A self-removing scheduled task runs the orphan repair path so a crash, forced kill or
  reboot can never leave the machine pointing at a dead loopback resolver.
"""

import os
import re
import sys
import json
import ctypes
import socket
import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

LOGGER = logging.getLogger(__name__)

LOOPBACK_DNS = {"127.0.0.1", "::1", "localhost"}
JOURNAL_VERSION = 2
JOURNAL_FILENAME = "dns_adapter_backup.json"
GUARD_TASK_NAME = "AcademiaShieldNetworkGuard"
GUARD_SCRIPT_NAME = "dns_guard.cmd"
GUARD_LOG_NAME = "dns_guard.log"

# DNS probes are sent to the local resolver to decide whether it is safe to keep
# adapters pointed at loopback.  Any DNS response proves something is listening.
DNS_PROBE_QUERY = (
    b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    b"\x06google\x03com\x00\x00\x01\x00\x01"
)

VIRTUAL_ADAPTER_MARKERS = (
    "virtual", "vethernet", "hyper-v", "vmware", "virtualbox", "vbox",
    "loopback", "tap", "tun", "wireguard", "tailscale", "zerotier", "vpn",
    "bluetooth", "wsl", "docker", "npcap", "host-only", "hostonly", "hamachi",
    "radmin", "openvpn", "teredo", "isatap",
)


def default_dns_state_dir() -> str:
    """Machine-wide journal directory, readable by a SYSTEM recovery task."""
    if sys.platform.startswith("win"):
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return os.path.join(program_data, "AcademiaShield")
    return os.path.expanduser("~/.academia_shield")


def probe_local_resolver(host: str = "127.0.0.1", port: int = 53, timeout: float = 1.0) -> bool:
    """Return True only if a DNS server actually answers on host:port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(DNS_PROBE_QUERY, (host, int(port)))
            data, _ = sock.recvfrom(512)
            return len(data) >= 12
        finally:
            sock.close()
    except Exception:
        return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_ipv4_list(values: Optional[List[str]]) -> List[str]:
    """Deduplicate IPv4 servers while dropping loopback/placeholder entries."""
    cleaned: List[str] = []
    for value in values or []:
        item = str(value).strip()
        if not item or item in LOOPBACK_DNS:
            continue
        match = re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", item)
        if not match:
            continue
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


class WindowsDNSAdapterManager:
    """Manages Windows network adapter DNS settings with a durable journal."""

    def __init__(self, backup_dir: Optional[str] = None):
        self.backup_dir = backup_dir or default_dns_state_dir()
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except Exception as err:
            fallback = os.path.expanduser("~/.academia_shield")
            LOGGER.warning("Cannot create DNS state dir %s (%s); falling back to %s", self.backup_dir, err, fallback)
            self.backup_dir = fallback
            os.makedirs(self.backup_dir, exist_ok=True)

        self.backup_file = os.path.join(self.backup_dir, JOURNAL_FILENAME)
        self.guard_script_file = os.path.join(self.backup_dir, GUARD_SCRIPT_NAME)
        self.guard_log_file = os.path.join(self.backup_dir, GUARD_LOG_NAME)
        self._is_enforced = False

    # ------------------------------------------------------------------
    # Platform helpers
    # ------------------------------------------------------------------
    @property
    def _is_windows(self) -> bool:
        return sys.platform.startswith("win")

    def is_admin(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def resolver_is_alive(self, port: int = 53, timeout: float = 2.0) -> bool:
        """Probe the local resolver before deciding that enforcement is still healthy."""
        return probe_local_resolver("127.0.0.1", port=port, timeout=timeout)

    def _run_powershell(self, script: str, timeout: int = 8):
        return subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    @staticmethod
    def _parse_json_payload(stdout: str) -> List[Dict[str, Any]]:
        text = (stdout or "").strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except Exception:
            return []
        if isinstance(data, dict):
            data = [data]
        return [item for item in data if isinstance(item, dict)]

    # ------------------------------------------------------------------
    # Adapter discovery
    # ------------------------------------------------------------------
    def get_all_adapters(self) -> List[Dict[str, Any]]:
        """Return every visible network adapter with alias, index and description."""
        if not self._is_windows:
            return []

        ps_script = (
            "Get-NetAdapter | Select-Object InterfaceAlias, InterfaceIndex, Name, "
            "InterfaceDescription, Status | ConvertTo-Json"
        )
        adapters: List[Dict[str, Any]] = []
        try:
            res = self._run_powershell(ps_script)
            if res.returncode == 0:
                for item in self._parse_json_payload(res.stdout):
                    alias = item.get("InterfaceAlias") or item.get("Name")
                    if not alias:
                        continue
                    adapters.append({
                        "alias": alias,
                        "index": item.get("InterfaceIndex"),
                        "name": item.get("Name") or alias,
                        "description": item.get("InterfaceDescription") or "",
                        "status": item.get("Status") or "",
                    })
        except Exception as err:
            LOGGER.warning("PowerShell net adapter query exception: %s", err)
        return adapters

    def get_active_adapters(self) -> List[Dict[str, Any]]:
        """Get connected adapters (kept for status/reporting compatibility)."""
        return [
            {"alias": adapter["alias"], "index": adapter.get("index")}
            for adapter in self.get_all_adapters()
            if str(adapter.get("status", "")).lower() == "up"
        ]

    def _query_default_route_adapters(self) -> List[Dict[str, Any]]:
        """Adapters carrying the lowest-metric IPv4 default route."""
        if not self._is_windows:
            return []

        ps_script = (
            "$routes = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
            "-ErrorAction SilentlyContinue | Where-Object { $_.NextHop -ne '0.0.0.0' }; "
            "if ($routes) { "
            "  $min = ($routes | Measure-Object -Property RouteMetric -Minimum).Minimum; "
            "  $routes | Where-Object { $_.RouteMetric -eq $min } | ForEach-Object { "
            "    Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue "
            "  } | Where-Object { $_.Status -eq 'Up' } | "
            "  Select-Object InterfaceAlias, InterfaceIndex, Name, InterfaceDescription, Status "
            "  | ConvertTo-Json "
            "}"
        )
        try:
            res = self._run_powershell(ps_script)
            if res.returncode != 0:
                LOGGER.warning("Default-route adapter query failed: %s", (res.stderr or "").strip())
                return []
            return self._parse_json_payload(res.stdout)
        except Exception as err:
            LOGGER.warning("Default-route adapter query exception: %s", err)
            return []

    @staticmethod
    def _is_virtual_adapter(adapter: Dict[str, Any]) -> bool:
        keys = (
            "alias", "name", "description",
            "InterfaceAlias", "Name", "InterfaceDescription",
        )
        haystack = " ".join(str(adapter.get(key) or "") for key in keys).lower()
        return any(marker in haystack for marker in VIRTUAL_ADAPTER_MARKERS)

    def get_enforcement_adapters(self, selected_adapter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Adapters that may safely be redirected: the physical default-route adapter(s).
        Returns an empty list rather than guessing when no safe adapter exists.
        """
        if not self._is_windows:
            return []

        if selected_adapter:
            wanted = selected_adapter.strip().lower()
            for adapter in self.get_all_adapters():
                if str(adapter.get("alias", "")).strip().lower() != wanted:
                    continue
                if self._is_virtual_adapter(adapter) or "loopback" in str(adapter.get("alias", "")).lower():
                    LOGGER.error("Refusing to redirect virtual/loopback adapter '%s'", selected_adapter)
                    return []
                status = str(adapter.get("status", "")).lower()
                if status and status != "up":
                    LOGGER.warning("Selected adapter '%s' is not connected (status=%s)", selected_adapter, status)
                    return []
                return [{"alias": adapter["alias"], "index": adapter.get("index")}]
            LOGGER.warning("Selected adapter '%s' was not found", selected_adapter)
            return []

        candidates = []
        for adapter in self._query_default_route_adapters():
            if self._is_virtual_adapter(adapter):
                LOGGER.info(
                    "Skipping virtual default-route adapter '%s' (%s)",
                    adapter.get("InterfaceAlias"),
                    adapter.get("InterfaceDescription"),
                )
                continue
            candidates.append({
                "alias": adapter.get("InterfaceAlias") or adapter.get("Name"),
                "index": adapter.get("InterfaceIndex"),
            })
        return [candidate for candidate in candidates if candidate.get("alias")]

    # ------------------------------------------------------------------
    # Adapter state read/write
    # ------------------------------------------------------------------
    def _query_adapter_dns_state(self, adapter: Dict[str, Any]) -> Dict[str, Any]:
        """Read DNS configuration mode (DHCP vs static) and effective servers."""
        state: Dict[str, Any] = {"ok": False, "dhcp": False, "servers": []}
        if not self._is_windows:
            return state

        alias = adapter.get("alias")
        if not alias:
            return state

        # CIM exposes whether the search order is static (non-null) or supplied by
        # DHCP (null), independent of display language and of effective addresses.
        ps_script = (
            f'$adapter = Get-NetAdapter -InterfaceAlias "{alias}" -ErrorAction SilentlyContinue; '
            "if (-not $adapter) { exit 2 }; "
            "$cfg = Get-CimInstance Win32_NetworkAdapterConfiguration "
            "-Filter \"InterfaceIndex = $($adapter.InterfaceIndex)\" -ErrorAction SilentlyContinue; "
            "$servers = @(); "
            "if ($cfg -and $cfg.DNSServerSearchOrder) { $servers = @($cfg.DNSServerSearchOrder) }; "
            "[PSCustomObject]@{ Servers = $servers; Dhcp = -not ($cfg -and $cfg.DNSServerSearchOrder) } "
            "| ConvertTo-Json -Compress"
        )
        try:
            res = self._run_powershell(ps_script)
            if res.returncode == 0 and (res.stdout or "").strip():
                data = json.loads(res.stdout)
                if isinstance(data, dict):
                    servers = data.get("Servers")
                    if isinstance(servers, str):
                        servers = [servers]
                    state["ok"] = True
                    state["dhcp"] = bool(data.get("Dhcp"))
                    state["servers"] = [str(server).strip() for server in (servers or []) if server]
                    return state
        except Exception as err:
            LOGGER.debug("CIM DNS query failed for '%s': %s", alias, err)

        # Fallback for systems where CIM/PowerShell is unavailable.
        try:
            res = subprocess.run(
                ["netsh", "interface", "ipv4", "show", "dns", f"name={alias}"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            output = res.stdout or ""
            if res.returncode == 0:
                lowered = output.lower()
                state["ok"] = True
                state["dhcp"] = (
                    "configured through dhcp" in lowered
                    or ("dhcp" in lowered and "statically configured" not in lowered)
                )
                state["servers"] = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", output)
        except Exception as err:
            LOGGER.debug("netsh DNS query failed for '%s': %s", alias, err)
        return state

    def _apply_adapter_servers(self, adapter: Dict[str, Any], servers: Optional[List[str]]) -> bool:
        """Set static DNS servers, or reset to DHCP when servers is None."""
        alias = adapter.get("alias")
        if not alias:
            return False
        if not self._is_windows:
            return False

        if servers is None:
            ps_script = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ResetServerAddresses'
            try:
                res = self._run_powershell(ps_script)
                if res.returncode == 0:
                    return True
            except Exception as err:
                LOGGER.debug("PowerShell DNS reset failed for '%s': %s", alias, err)
            try:
                res = subprocess.run(
                    ["netsh", "interface", "ipv4", "set", "dns", f"name={alias}", "dhcp"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                return res.returncode == 0
            except Exception as err:
                LOGGER.error("netsh DNS reset failed for '%s': %s", alias, err)
                return False

        server_list = ",".join(f'"{server}"' for server in servers)
        ps_script = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ServerAddresses ({server_list})'
        try:
            res = self._run_powershell(ps_script)
            if res.returncode == 0:
                return True
        except Exception as err:
            LOGGER.debug("PowerShell DNS set failed for '%s': %s", alias, err)

        try:
            primary = servers[0]
            res = subprocess.run(
                ["netsh", "interface", "ipv4", "set", "dns", f"name={alias}", "static", primary, "primary"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if res.returncode != 0:
                LOGGER.error("netsh DNS set failed for '%s': %s", alias, (res.stderr or res.stdout).strip())
                return False
            for index, server in enumerate(servers[1:], start=2):
                subprocess.run(
                    ["netsh", "interface", "ipv4", "add", "dns", f"name={alias}", server, f"index={index}"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
            return True
        except Exception as err:
            LOGGER.error("netsh DNS set failed for '%s': %s", alias, err)
            return False

    @staticmethod
    def _flush_dns() -> None:
        try:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Durable journal
    # ------------------------------------------------------------------
    def _write_journal(self, journal: Dict[str, Any]) -> bool:
        """Atomically persist the journal (temp file + fsync + replace)."""
        journal["version"] = JOURNAL_VERSION
        journal["updated_at_utc"] = _utc_now()
        temp_path = None
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(prefix=".dns_journal_", dir=self.backup_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(journal, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.backup_file)
            return True
        except Exception as err:
            LOGGER.error("Failed writing DNS state journal %s: %s", self.backup_file, err)
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return False

    def _load_journal(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.backup_file):
            return None
        try:
            with open(self.backup_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as err:
            LOGGER.error("Could not read DNS state journal %s: %s", self.backup_file, err)
            # Quarantine the unreadable journal so orphan repair can run and the
            # recovery guard can eventually remove itself.
            try:
                os.replace(self.backup_file, self.backup_file + ".corrupt")
            except Exception:
                pass
            return None

        if not isinstance(data, dict):
            return None

        # Legacy v1 format: {"Wi-Fi": ["8.8.8.8", "1.1.1.1"]}
        if "adapters" not in data:
            entries: Dict[str, Dict[str, Any]] = {}
            for alias, servers in data.items():
                if not isinstance(servers, list):
                    continue
                raw_servers = [str(server).strip() for server in servers]
                clean_servers = _as_ipv4_list(raw_servers)
                entries[str(alias)] = {
                    "alias": str(alias),
                    "index": None,
                    "original_servers": clean_servers,
                    "was_dhcp": not clean_servers,
                    "pre_existing_loopback": any(server in LOOPBACK_DNS for server in raw_servers),
                    "changed": True,
                    "restored": False,
                    "snapshot_ok": True,
                }
            if not entries:
                return None
            return {
                "version": JOURNAL_VERSION,
                "status": "enforced",
                "created_at_utc": _utc_now(),
                "updated_at_utc": _utc_now(),
                "resolver_port": 53,
                "adapters": entries,
                "legacy": True,
            }

        if not isinstance(data.get("adapters"), dict) or not data["adapters"]:
            return None
        return data

    def _remove_journal(self) -> None:
        try:
            if os.path.exists(self.backup_file):
                os.remove(self.backup_file)
        except Exception as err:
            LOGGER.warning("Could not remove DNS state journal %s: %s", self.backup_file, err)

    def _legacy_backup_paths(self) -> List[str]:
        candidates = [
            os.path.expanduser("~/.academia_shield/dns_adapter_backup.json"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "AcademiaShield", "dns_adapter_backup.json"),
            os.path.join(os.environ.get("ProgramFiles", ""), "AcademiaShield", "dns_adapter_backup.json"),
        ]
        current = os.path.abspath(self.backup_file)
        paths = []
        for candidate in candidates:
            if not candidate or not os.path.isfile(candidate):
                continue
            if os.path.abspath(candidate) == current:
                continue
            paths.append(candidate)
        return paths

    def _migrate_legacy_journal(self) -> Optional[Dict[str, Any]]:
        """Import an old per-user backup (v1) into the durable machine-wide journal."""
        for legacy_path in self._legacy_backup_paths():
            try:
                with open(legacy_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except Exception:
                continue
            if not isinstance(raw, dict) or not raw:
                continue

            previous_file = self.backup_file
            self.backup_file = legacy_path
            try:
                journal = self._load_journal()
            finally:
                self.backup_file = previous_file

            if not journal:
                continue
            journal["migrated_from"] = legacy_path
            if not self._write_journal(journal):
                continue
            LOGGER.warning("Imported legacy DNS backup from %s into %s", legacy_path, self.backup_file)
            try:
                os.remove(legacy_path)
            except Exception:
                pass
            return journal
        return None

    def _snapshot_adapter(self, adapter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        state = self._query_adapter_dns_state(adapter)
        if not state.get("ok"):
            LOGGER.error(
                "Refusing to modify adapter '%s': its current DNS state could not be read safely.",
                adapter.get("alias"),
            )
            return None

        raw_servers = [str(server).strip() for server in state.get("servers", [])]
        clean_servers = _as_ipv4_list(raw_servers)
        pre_loopback = any(server in LOOPBACK_DNS for server in raw_servers)
        return {
            "alias": adapter.get("alias"),
            "index": adapter.get("index"),
            "original_servers": clean_servers,
            "was_dhcp": bool(state.get("dhcp")) or not clean_servers,
            "pre_existing_loopback": pre_loopback,
            "changed": False,
            "restored": False,
            "snapshot_ok": True,
        }

    # ------------------------------------------------------------------
    # Enforcement lifecycle
    # ------------------------------------------------------------------
    def backup_original_dns(self) -> bool:
        """Snapshot the exact pre-enforcement DNS state without changing anything."""
        existing = self._load_journal()
        if existing and existing.get("adapters"):
            return True

        adapters = self.get_enforcement_adapters()
        if not adapters:
            LOGGER.error("No safe physical default-route adapter found; refusing to back up or redirect DNS.")
            return False

        entries: Dict[str, Dict[str, Any]] = {}
        for adapter in adapters:
            snapshot = self._snapshot_adapter(adapter)
            if snapshot:
                entries[snapshot["alias"]] = snapshot

        if not entries:
            LOGGER.error("Could not snapshot any adapter DNS state; refusing DNS enforcement.")
            return False

        journal = {
            "version": JOURNAL_VERSION,
            "status": "pending",
            "created_at_utc": _utc_now(),
            "resolver_port": 53,
            "agent_pid": os.getpid(),
            "adapters": entries,
            "last_error": None,
        }
        if not self._write_journal(journal):
            return False
        LOGGER.info("Saved original Windows DNS configuration to durable journal %s", self.backup_file)
        return True

    def configure_local_dns(
        self,
        target_dns: str = "127.0.0.1",
        resolver_healthy: bool = True,
        selected_adapter: Optional[str] = None,
        resolver_port: int = 53,
    ) -> bool:
        """
        Point the physical default-route adapter at the local resolver.

        The journal is persisted before the first mutation and refreshed after every
        adapter change, so a crash at any point is recoverable on the next boot.
        """
        if not resolver_healthy:
            LOGGER.error("Cannot enable DNS enforcement: local resolver is not healthy.")
            return False

        if not self.is_admin():
            LOGGER.warning("Admin rights required to configure adapter DNS; skipping live redirection.")
            return False

        if target_dns in LOOPBACK_DNS and int(resolver_port) != 53:
            LOGGER.error(
                "Refusing adapter redirect: Windows DNS always uses port 53, but the resolver listens on %s. "
                "Redirecting would break all DNS.",
                resolver_port,
            )
            return False

        # Defense in depth: never trust the caller's health flag alone.  If nothing
        # answers on the loopback resolver, pointing adapters at it blacks out DNS.
        if target_dns in LOOPBACK_DNS and not probe_local_resolver(
            target_dns, int(resolver_port), timeout=1.5
        ):
            LOGGER.error(
                "Refusing adapter redirect: no DNS server answered on %s:%s.",
                target_dns,
                resolver_port,
            )
            return False

        adapters = self.get_enforcement_adapters(selected_adapter=selected_adapter)
        if not adapters:
            LOGGER.error("No safe default-route adapter available for DNS redirection.")
            return False

        journal = self._load_journal()
        created_journal = journal is None
        if journal is None:
            journal = {
                "version": JOURNAL_VERSION,
                "status": "pending",
                "created_at_utc": _utc_now(),
                "resolver_port": int(resolver_port),
                "agent_pid": os.getpid(),
                "adapters": {},
                "last_error": None,
            }

        # Snapshot every new target before it is touched.  If the journal cannot
        # be persisted, no adapter may be changed.
        for adapter in adapters:
            alias = adapter["alias"]
            if alias in journal["adapters"]:
                continue
            snapshot = self._snapshot_adapter(adapter)
            if not snapshot:
                continue
            journal["adapters"][alias] = snapshot

        journal["resolver_port"] = int(resolver_port)
        journal["agent_pid"] = os.getpid()
        if not journal["adapters"]:
            LOGGER.error("No adapter could be snapshotted; refusing DNS redirection.")
            return False
        if not self._write_journal(journal):
            LOGGER.error("DNS state journal is not writable; refusing DNS redirection.")
            return False

        # The guard must exist before the first adapter change so a crash or
        # forced termination cannot strand the machine on loopback DNS.
        self.ensure_recovery_task()

        changed = False
        for adapter in adapters:
            alias = adapter["alias"]
            entry = journal["adapters"].get(alias)
            if not entry:
                continue
            if entry.get("restored"):
                # Reusing a stale journal must never restore an already-restored entry.
                snapshot = self._snapshot_adapter(adapter)
                if not snapshot:
                    continue
                journal["adapters"][alias] = snapshot
                entry = snapshot

            current = self._query_adapter_dns_state(adapter)
            if current.get("ok") and target_dns in current.get("servers", []):
                entry["changed"] = True
                changed = True
                continue

            if self._apply_adapter_servers(adapter, [target_dns]):
                # Record the mutation immediately: even if verification below
                # fails, restore must know this adapter was changed.
                entry["changed"] = True
                entry["applied_at_utc"] = _utc_now()
                verified = self._query_adapter_dns_state(adapter)
                if verified.get("ok") and target_dns in verified.get("servers", []):
                    changed = True
                    LOGGER.info("Configured DNS for adapter '%s' -> %s", alias, target_dns)
                else:
                    journal["last_error"] = f"Adapter '{alias}' did not report the enforced DNS server"
                    LOGGER.error("DNS enforcement verification failed for adapter '%s'", alias)
            else:
                journal["last_error"] = f"Failed to configure adapter '{alias}'"
                LOGGER.error("Could not configure DNS for adapter '%s'", alias)
            self._write_journal(journal)

        if changed:
            journal["status"] = "enforced"
            self._write_journal(journal)
            self._is_enforced = True
            LOGGER.info("DNS enforcement active on %s adapter(s)", len(journal["adapters"]))
            return True

        # Nothing was changed: do not leave a pending journal or guard behind.
        if created_journal:
            self._remove_journal()
            self.remove_recovery_task()
        self._is_enforced = False
        return False

    def _find_adapter(self, alias: str, index: Optional[int] = None) -> Optional[Dict[str, Any]]:
        inventory = self.get_all_adapters()
        for adapter in inventory:
            if str(adapter.get("alias", "")).lower() == str(alias).lower():
                return adapter
        if index is not None:
            for adapter in inventory:
                if adapter.get("index") == index:
                    return adapter
        return None

    def restore_original_dns(self) -> bool:
        """
        Restore every journaled adapter to its exact pre-enforcement state and verify
        the result.  The journal is removed only after all adapters are verified.
        """
        if not self._is_windows:
            return True

        journal = self._load_journal()
        if journal is None:
            journal = self._migrate_legacy_journal()

        if journal is None:
            # No journal: only repair adapters actually pointing at loopback.
            return self._reset_orphaned_loopback_adapters(remove_guard=True)

        if not self.is_admin():
            LOGGER.warning("Admin privileges required to restore Windows adapter DNS; keeping journal for recovery.")
            return False

        failed_aliases: List[str] = []
        for alias, entry in journal["adapters"].items():
            if entry.get("restored"):
                continue

            adapter = self._find_adapter(alias, entry.get("index"))
            if adapter is None:
                if not entry.get("changed"):
                    entry["restored"] = True
                    continue
                entry["last_error"] = "adapter not present"
                failed_aliases.append(alias)
                LOGGER.warning("Adapter '%s' is not present; keeping journal entry for later recovery.", alias)
                continue

            original = _as_ipv4_list(entry.get("original_servers"))
            if entry.get("was_dhcp") or not original:
                expected: Optional[List[str]] = None
            else:
                expected = original

            applied = self._apply_adapter_servers(adapter, expected)
            if not applied:
                entry["last_error"] = "failed to apply original DNS"
                failed_aliases.append(alias)
                continue

            current = self._query_adapter_dns_state(adapter)
            if not current.get("ok"):
                entry["last_error"] = "could not verify restored DNS state"
                failed_aliases.append(alias)
                continue

            current_servers = [str(server).strip() for server in current.get("servers", [])]
            if expected is None:
                verified = bool(current.get("dhcp")) or not any(
                    server in LOOPBACK_DNS for server in current_servers
                )
            else:
                verified = set(current_servers) == set(expected)

            if not verified:
                entry["last_error"] = f"verification mismatch: current={current_servers} expected={expected or 'DHCP'}"
                failed_aliases.append(alias)
                LOGGER.error("Restore verification failed for adapter '%s': %s", alias, entry["last_error"])
                continue

            entry["restored"] = True
            entry["restored_at_utc"] = _utc_now()
            entry.pop("last_error", None)
            LOGGER.info("Restored DNS for adapter '%s' -> %s", alias, original or "DHCP")
            self._write_journal(journal)

        if failed_aliases:
            journal["status"] = "restore_pending"
            journal["last_error"] = "restore failed for: " + ", ".join(sorted(failed_aliases))
            self._write_journal(journal)
            self._flush_dns()
            LOGGER.error(
                "DNS restoration incomplete for %s. Journal kept at %s and recovery guard retained.",
                journal["last_error"],
                self.backup_file,
            )
            return False

        self._flush_dns()
        self._remove_journal()
        self._is_enforced = False
        self.remove_recovery_task()
        LOGGER.info("Original DNS configuration verified and restored on all managed adapters.")
        return True

    def _reset_orphaned_loopback_adapters(self, remove_guard: bool = False) -> bool:
        """
        Repair adapters that point at loopback while no resolver answers.

        This intentionally runs only when no journal exists, and only touches adapters
        whose own DNS servers include loopback.  Healthy static/DHCP adapters are never
        rewritten.
        """
        if not self._is_windows:
            return True

        if probe_local_resolver("127.0.0.1", 53):
            LOGGER.info("A local resolver is answering; refusing to alter adapter DNS.")
            return True

        adapters = self.get_all_adapters()
        if not adapters:
            LOGGER.warning("Could not enumerate network adapters; cannot verify stale DNS state.")
            return False

        targets: List[Any] = []
        for adapter in adapters:
            alias = str(adapter.get("alias", ""))
            if "loopback" in alias.lower():
                continue
            # Never rewrite a third-party VPN/Docker/WSL adapter that legitimately
            # uses a loopback DNS proxy of its own.
            if self._is_virtual_adapter(adapter):
                continue
            state = self._query_adapter_dns_state(adapter)
            if not state.get("ok"):
                continue
            raw_servers = [str(server).strip() for server in state.get("servers", [])]
            if any(server in LOOPBACK_DNS for server in raw_servers):
                targets.append((adapter, raw_servers))

        # Nothing stale: a standard user can safely complete the no-op restore.
        if not targets:
            if remove_guard:
                self.remove_recovery_task()
            return True

        if not self.is_admin():
            LOGGER.warning("Admin rights required to repair orphaned loopback DNS.")
            return False

        repaired = 0
        failed: List[str] = []
        for adapter, raw_servers in targets:
            alias = str(adapter.get("alias", ""))

            # Preserve any real upstream servers that were configured alongside
            # loopback; only fall back to DHCP when loopback was the sole server.
            fallback_servers = _as_ipv4_list(raw_servers) or None
            LOGGER.warning(
                "Stale loopback DNS detected on adapter '%s'; restoring %s.",
                alias,
                fallback_servers or "DHCP",
            )
            if self._apply_adapter_servers(adapter, fallback_servers):
                verified = self._query_adapter_dns_state(adapter)
                verified_servers = [str(server).strip() for server in verified.get("servers", [])]
                if verified.get("ok") and not any(server in LOOPBACK_DNS for server in verified_servers):
                    repaired += 1
                    continue
            failed.append(alias)

        if repaired:
            self._flush_dns()
        if failed:
            LOGGER.error("Could not repair stale loopback DNS on: %s", ", ".join(failed))
            return False

        if remove_guard:
            self.remove_recovery_task()
        return True

    def clean_stale_dns(self) -> bool:
        """
        Conservative startup repair: restore a journal if one exists, otherwise reset
        only adapters that are actually pointing at a dead loopback resolver.
        """
        journal = self._load_journal()
        if journal is not None:
            return self.restore_original_dns()
        return self._reset_orphaned_loopback_adapters(remove_guard=True)

    def recover_orphaned_state(self) -> Dict[str, Any]:
        """
        Entry point for the startup and scheduled-task recovery path.

        Skips work while a local resolver is answering (an agent is likely running),
        otherwise restores the durable journal or repairs loopback-only adapters.
        """
        journal = self._load_journal()
        if journal is not None:
            port = int(journal.get("resolver_port") or 53)
            if probe_local_resolver("127.0.0.1", port):
                return {"status": "skipped", "reason": "resolver_live", "journal": self.backup_file}
            if not self.is_admin():
                return {"status": "requires_admin", "journal": self.backup_file}
            restored = self.restore_original_dns()
            return {
                "status": "restored" if restored else "restore_failed",
                "journal": self.backup_file,
            }

        # A legacy per-user backup may exist from an older agent build.
        migrated = self._migrate_legacy_journal()
        if migrated is not None:
            if probe_local_resolver("127.0.0.1", int(migrated.get("resolver_port") or 53)):
                return {"status": "skipped", "reason": "resolver_live", "journal": self.backup_file}
            restored = self.restore_original_dns()
            return {
                "status": "restored" if restored else "restore_failed",
                "journal": self.backup_file,
                "migrated": True,
            }

        if probe_local_resolver("127.0.0.1", 53):
            return {"status": "skipped", "reason": "resolver_live"}
        if not self.is_admin():
            return {"status": "requires_admin"}
        repaired = self.clean_stale_dns()
        return {"status": "clean" if repaired else "repair_failed"}

    # ------------------------------------------------------------------
    # Watchdog / scheduled-task recovery
    # ------------------------------------------------------------------
    def _guard_command(self) -> List[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "repair", "--orphan-check", "--quiet"]
        package_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        script = os.path.join(package_dir, "agent.py")
        return [sys.executable, script, "repair", "--orphan-check", "--quiet"]

    def _write_guard_script(self) -> bool:
        command = subprocess.list2cmdline(self._guard_command())
        content = (
            "@echo off\r\n"
            f"{command} >> \"{self.guard_log_file}\" 2>&1\r\n"
        )
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            with open(self.guard_script_file, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            return True
        except Exception as err:
            LOGGER.warning("Could not write recovery guard script: %s", err)
            return False

    def ensure_recovery_task(self) -> bool:
        """
        Install a self-removing SYSTEM task that runs orphan recovery every two minutes.
        Best-effort: never blocks enforcement when Task Scheduler is unavailable.
        """
        if not self._is_windows or not self.is_admin():
            return False
        if not self._write_guard_script():
            return False

        command = [
            "schtasks", "/Create",
            "/TN", GUARD_TASK_NAME,
            "/TR", self.guard_script_file,
            "/SC", "MINUTE", "/MO", "2",
            "/RU", "SYSTEM", "/RL", "HIGHEST",
            "/F",
        ]
        try:
            res = subprocess.run(command, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                LOGGER.info("Installed DNS recovery guard task '%s'.", GUARD_TASK_NAME)
                return True

            LOGGER.warning("SYSTEM recovery task creation failed (%s); trying current-user scope.", (res.stderr or res.stdout).strip())
            fallback = [
                "schtasks", "/Create",
                "/TN", GUARD_TASK_NAME,
                "/TR", self.guard_script_file,
                "/SC", "MINUTE", "/MO", "2",
                "/F",
            ]
            res = subprocess.run(fallback, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                LOGGER.info("Installed current-user DNS recovery guard task '%s'.", GUARD_TASK_NAME)
                return True
            LOGGER.warning("Could not install DNS recovery guard task: %s", (res.stderr or res.stdout).strip())
        except Exception as err:
            LOGGER.warning("Could not install DNS recovery guard task: %s", err)
        return False

    def remove_recovery_task(self) -> bool:
        """Remove the recovery task once no journal remains (or during uninstall)."""
        if not self._is_windows:
            return False
        try:
            res = subprocess.run(
                ["schtasks", "/Delete", "/TN", GUARD_TASK_NAME, "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0:
                LOGGER.info("Removed DNS recovery guard task '%s'.", GUARD_TASK_NAME)
                return True
        except Exception as err:
            LOGGER.debug("Could not remove DNS recovery guard task: %s", err)
        return False

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def detect_drift(self, expected_dns: str = "127.0.0.1") -> bool:
        """Return True if an enforced default-route adapter no longer points at the resolver."""
        journal = self._load_journal()
        if journal is None:
            return False
        for alias in journal.get("adapters", {}):
            adapter = self._find_adapter(alias)
            if adapter is None:
                continue
            state = self._query_adapter_dns_state(adapter)
            if state.get("ok") and expected_dns not in state.get("servers", []):
                LOGGER.warning(
                    "DNS drift detected on adapter '%s': current=%s expected=%s",
                    alias,
                    state.get("servers"),
                    expected_dns,
                )
                return True
        return False

    def get_status(self) -> Dict[str, Any]:
        journal = self._load_journal()
        return {
            "enforcement_active": journal is not None,
            "journal_path": self.backup_file,
            "journal_status": journal.get("status") if journal else None,
            "managed_adapters": sorted(journal.get("adapters", {}).keys()) if journal else [],
        }
