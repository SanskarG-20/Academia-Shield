"""
Academia Shield Agent — DNS Resolver Enforcement Engine (Production Mode)

Blocks domains by running a lightweight local DNS resolver on 127.0.0.1:53.
Blocked domains resolve to 127.0.0.1. All other queries are forwarded to the
upstream DNS server transparently.

System DNS is temporarily pointed to 127.0.0.1. The exact pre-enforcement
state is journaled to a machine-wide file BEFORE the adapter is touched, and
the journal is only deleted after the original state has been re-applied and
verified. A crash, forced kill or reboot can therefore never leave the device
pointing at a dead loopback resolver: the next agent start repairs it.

Uses only Python standard library — zero external dependencies.
"""

import atexit
import json
import logging
import os
import platform
import re
import socket
import struct
import subprocess
import threading
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from enforcement.base import EnforcementEngine
from config import DNS_LISTEN_PORT, DNS_UPSTREAM, DNS_UPSTREAM_PORT, DNS_BACKUP_FILE, REDIRECT_IP

LOGGER = logging.getLogger("academia_shield_agent")

LOOPBACK_DNS = {"127.0.0.1", "::1", "localhost"}
DNS_JOURNAL_VERSION = 2
DNS_PROBE_QUERY = (
    b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    b"\x06google\x03com\x00\x00\x01\x00\x01"
)
VIRTUAL_INTERFACE_MARKERS = (
    "virtual", "vethernet", "hyper-v", "vmware", "virtualbox", "vbox",
    "loopback", "tap", "tun", "wireguard", "tailscale", "zerotier", "vpn",
    "bluetooth", "wsl", "docker", "npcap", "host-only", "hostonly", "hamachi",
    "radmin", "openvpn", "teredo", "isatap",
)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _is_admin():
    try:
        if platform.system() == "Windows":
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return os.geteuid() == 0
    except Exception:
        return False


def _clean_ipv4(values):
    cleaned = []
    for value in values or []:
        item = str(value).strip()
        if not item or item in LOOPBACK_DNS:
            continue
        if not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", item):
            continue
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


def _run_powershell(script, timeout=8):
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _probe_resolver(host="127.0.0.1", port=None, timeout=1.5):
    """Return True only if a DNS server actually answers on host:port."""
    if port is None:
        port = DNS_LISTEN_PORT
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


def _flush_dns():
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5)
    except Exception:
        pass


def _parse_ps_json(stdout):
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


def _is_virtual_interface(alias, description=""):
    haystack = f"{alias or ''} {description or ''}".lower()
    return any(marker in haystack for marker in VIRTUAL_INTERFACE_MARKERS)


def _all_interfaces():
    """Return [{alias, index, description, status}] for every visible adapter."""
    script = (
        "Get-NetAdapter | Select-Object InterfaceAlias, InterfaceIndex, Name, "
        "InterfaceDescription, Status | ConvertTo-Json"
    )
    interfaces = []
    try:
        res = _run_powershell(script)
        if res.returncode == 0:
            for item in _parse_ps_json(res.stdout):
                alias = item.get("InterfaceAlias") or item.get("Name")
                if not alias:
                    continue
                interfaces.append({
                    "alias": alias,
                    "index": item.get("InterfaceIndex"),
                    "description": item.get("InterfaceDescription") or "",
                    "status": item.get("Status") or "",
                })
    except Exception as err:
        LOGGER.warning("[DNS] Adapter enumeration failed: %s", err)
    return interfaces


def _get_windows_dns_interfaces():
    """
    Physical adapters carrying the lowest-metric IPv4 default route.

    Virtual/host-only/VPN adapters are never returned. An empty list means
    'do not redirect' rather than guessing an interface name.
    """
    script = (
        "$routes = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
        "-ErrorAction SilentlyContinue | Where-Object { $_.NextHop -ne '0.0.0.0' }; "
        "if ($routes) { "
        "  $min = ($routes | Measure-Object -Property RouteMetric -Minimum).Minimum; "
        "  $routes | Where-Object { $_.RouteMetric -eq $min } | ForEach-Object { "
        "    Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue "
        "  } | Where-Object { $_.Status -eq 'Up' } | "
        "  Select-Object InterfaceAlias, InterfaceIndex, InterfaceDescription, Status "
        "  | ConvertTo-Json "
        "}"
    )
    selected = []
    try:
        res = _run_powershell(script)
        if res.returncode == 0:
            for item in _parse_ps_json(res.stdout):
                alias = item.get("InterfaceAlias")
                description = item.get("InterfaceDescription") or ""
                if not alias or _is_virtual_interface(alias, description):
                    continue
                selected.append(alias)
    except Exception as err:
        LOGGER.warning("[DNS] Default-route query failed: %s", err)

    if selected:
        return selected

    # Fallback for hosts without the NetTCPIP module. Only accept an interface
    # that has a default gateway and is not obviously virtual.
    try:
        output = subprocess.check_output(
            ["netsh", "interface", "ip", "show", "config"],
            text=True, timeout=10, stderr=subprocess.DEVNULL,
        )
        current_iface = None
        for line in output.splitlines():
            stripped = line.strip()
            if line and not line[0].isspace() and stripped.startswith("Configuration for interface"):
                current_iface = stripped.split('"')[1] if '"' in stripped else None
            if current_iface and "Default Gateway" in stripped:
                gateway = stripped.split(":")[-1].strip()
                if gateway and gateway != "None" and not _is_virtual_interface(current_iface):
                    return [current_iface]
    except Exception as err:
        LOGGER.warning("[DNS] Fallback interface detection failed: %s", err)
    return []


def _interface_state(alias):
    """Read exact DNS mode (DHCP vs static) and servers for an interface."""
    state = {"ok": False, "dhcp": False, "servers": []}
    escaped = str(alias).replace('"', '`"')
    script = (
        f'$adapter = Get-NetAdapter -InterfaceAlias "{escaped}" -ErrorAction SilentlyContinue; '
        "if (-not $adapter) { exit 2 }; "
        "$cfg = Get-CimInstance Win32_NetworkAdapterConfiguration "
        "-Filter \"InterfaceIndex = $($adapter.InterfaceIndex)\" -ErrorAction SilentlyContinue; "
        "$servers = @(); "
        "if ($cfg -and $cfg.DNSServerSearchOrder) { $servers = @($cfg.DNSServerSearchOrder) }; "
        "[PSCustomObject]@{ Servers = $servers; Dhcp = -not ($cfg -and $cfg.DNSServerSearchOrder) } "
        "| ConvertTo-Json -Compress"
    )
    try:
        res = _run_powershell(script)
        if res.returncode == 0 and (res.stdout or "").strip():
            data = json.loads(res.stdout)
            if isinstance(data, dict):
                servers = data.get("Servers")
                if isinstance(servers, str):
                    servers = [servers]
                state["ok"] = True
                state["dhcp"] = bool(data.get("Dhcp"))
                state["servers"] = [str(item).strip() for item in (servers or []) if item]
                return state
    except Exception as err:
        LOGGER.debug("[DNS] CIM query failed for '%s': %s", alias, err)

    try:
        res = subprocess.run(
            ["netsh", "interface", "ipv4", "show", "dns", f"name={alias}"],
            capture_output=True, text=True, timeout=8,
        )
        if res.returncode == 0:
            lowered = (res.stdout or "").lower()
            state["ok"] = True
            state["dhcp"] = (
                "configured through dhcp" in lowered
                or ("dhcp" in lowered and "statically configured" not in lowered)
            )
            state["servers"] = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", res.stdout or "")
    except Exception as err:
        LOGGER.debug("[DNS] netsh query failed for '%s': %s", alias, err)
    return state


def _apply_interface_servers(alias, servers):
    """Set static DNS servers, or reset to DHCP when servers is None."""
    if servers is None:
        script = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ResetServerAddresses'
        try:
            res = _run_powershell(script)
            if res.returncode == 0:
                return True
        except Exception as err:
            LOGGER.debug("[DNS] PowerShell reset failed for '%s': %s", alias, err)
        try:
            res = subprocess.run(
                ["netsh", "interface", "ipv4", "set", "dns", f"name={alias}", "dhcp"],
                capture_output=True, text=True, timeout=8,
            )
            return res.returncode == 0
        except Exception as err:
            LOGGER.error("[DNS] netsh reset failed for '%s': %s", alias, err)
            return False

    server_list = ",".join(f'"{server}"' for server in servers)
    script = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ServerAddresses ({server_list})'
    try:
        res = _run_powershell(script)
        if res.returncode == 0:
            return True
    except Exception as err:
        LOGGER.debug("[DNS] PowerShell set failed for '%s': %s", alias, err)

    try:
        res = subprocess.run(
            ["netsh", "interface", "ipv4", "set", "dns", f"name={alias}", "static", servers[0], "primary"],
            capture_output=True, text=True, timeout=8,
        )
        if res.returncode != 0:
            LOGGER.error("[DNS] netsh set failed for '%s': %s", alias, (res.stderr or res.stdout).strip())
            return False
        for index, server in enumerate(servers[1:], start=2):
            subprocess.run(
                ["netsh", "interface", "ipv4", "add", "dns", f"name={alias}", server, f"index={index}"],
                capture_output=True, text=True, timeout=8,
            )
        return True
    except Exception as err:
        LOGGER.error("[DNS] netsh set failed for '%s': %s", alias, err)
        return False


# ---------------------------------------------------------------------------
# Durable DNS journal
# ---------------------------------------------------------------------------
def _write_journal(journal):
    journal["version"] = DNS_JOURNAL_VERSION
    journal["updated_at_utc"] = _utc_now()
    temp_path = None
    try:
        os.makedirs(os.path.dirname(DNS_BACKUP_FILE), exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=".dns_journal_", dir=os.path.dirname(DNS_BACKUP_FILE)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(journal, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, DNS_BACKUP_FILE)
        return True
    except Exception as err:
        LOGGER.error("[DNS] Failed writing DNS journal: %s", err)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def _load_journal():
    if not os.path.exists(DNS_BACKUP_FILE):
        return None
    try:
        with open(DNS_BACKUP_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as err:
        LOGGER.error("[DNS] Could not read DNS journal: %s", err)
        try:
            os.replace(DNS_BACKUP_FILE, DNS_BACKUP_FILE + ".corrupt")
        except Exception:
            pass
        return None
    if not isinstance(data, dict) or not isinstance(data.get("adapters"), dict):
        return None
    if not data["adapters"]:
        return None
    return data


def _remove_journal():
    try:
        if os.path.exists(DNS_BACKUP_FILE):
            os.remove(DNS_BACKUP_FILE)
    except Exception as err:
        LOGGER.warning("[DNS] Could not remove DNS journal: %s", err)


def _migrate_legacy_backup():
    """Import the old single-interface backup stored next to the agent."""
    agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    legacy_path = os.path.join(agent_dir, "dns_backup.json")
    if os.path.abspath(legacy_path) == os.path.abspath(DNS_BACKUP_FILE):
        return None
    if not os.path.isfile(legacy_path):
        return None
    try:
        with open(legacy_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        return None
    if not isinstance(raw, dict) or "interface" not in raw:
        return None

    interface = str(raw.get("interface") or "").strip()
    if not interface:
        return None
    raw_servers = [str(item).strip() for item in raw.get("servers", [])]
    clean_servers = _clean_ipv4(raw_servers)
    journal = {
        "version": DNS_JOURNAL_VERSION,
        "status": "enforced",
        "created_at_utc": _utc_now(),
        "resolver_port": DNS_LISTEN_PORT,
        "adapters": {
            interface: {
                "alias": interface,
                "original_servers": clean_servers,
                "was_dhcp": not clean_servers or raw_servers == ["dhcp"],
                "pre_existing_loopback": any(server in LOOPBACK_DNS for server in raw_servers),
                "changed": True,
                "restored": False,
            }
        },
        "migrated_from": legacy_path,
    }
    if not _write_journal(journal):
        return None
    try:
        os.remove(legacy_path)
    except Exception:
        pass
    LOGGER.warning("[DNS] Migrated legacy DNS backup %s into %s", legacy_path, DNS_BACKUP_FILE)
    return journal


def _snapshot_interface(alias):
    state = _interface_state(alias)
    if not state.get("ok"):
        LOGGER.error("[DNS] Refusing to modify '%s': current DNS state is unreadable.", alias)
        return None
    raw_servers = [str(item).strip() for item in state.get("servers", [])]
    clean_servers = _clean_ipv4(raw_servers)
    return {
        "alias": alias,
        "original_servers": clean_servers,
        "was_dhcp": bool(state.get("dhcp")) or not clean_servers,
        "pre_existing_loopback": any(server in LOOPBACK_DNS for server in raw_servers),
        "changed": False,
        "restored": False,
    }


def _restore_dns_from_journal():
    """Restore and verify every journaled interface; delete the journal only on success."""
    journal = _load_journal()
    if journal is None:
        return True
    if not _is_admin():
        LOGGER.warning("[DNS] Administrator rights required to restore DNS; journal kept.")
        return False

    failed = []
    for alias, entry in journal["adapters"].items():
        if entry.get("restored"):
            continue

        original = _clean_ipv4(entry.get("original_servers"))
        expected = None if entry.get("was_dhcp") or not original else original

        if not _apply_interface_servers(alias, expected):
            failed.append(alias)
            continue

        current = _interface_state(alias)
        if not current.get("ok"):
            failed.append(alias)
            continue

        current_servers = [str(item).strip() for item in current.get("servers", [])]
        if expected is None:
            verified = bool(current.get("dhcp")) or not any(
                server in LOOPBACK_DNS for server in current_servers
            )
        else:
            verified = set(current_servers) == set(expected)

        if not verified:
            LOGGER.error(
                "[DNS] Restore verification failed for '%s': current=%s expected=%s",
                alias, current_servers, expected or "DHCP",
            )
            failed.append(alias)
            continue

        entry["restored"] = True
        entry["restored_at_utc"] = _utc_now()
        _write_journal(journal)
        LOGGER.info("[DNS] Restored DNS for '%s' -> %s", alias, original or "DHCP")

    if failed:
        journal["status"] = "restore_pending"
        journal["last_error"] = "restore failed for: " + ", ".join(sorted(failed))
        _write_journal(journal)
        _flush_dns()
        LOGGER.error("[DNS] DNS restoration incomplete for %s; journal retained.", journal["last_error"])
        return False

    _flush_dns()
    _remove_journal()
    LOGGER.info("[DNS] Original DNS settings verified and restored")
    return True


def _repair_loopback_interfaces():
    """With no journal, reset only interfaces that are actually pointing at loopback."""
    interfaces = _all_interfaces()
    if not interfaces:
        return False

    targets = []
    for adapter in interfaces:
        alias = adapter.get("alias")
        if not alias or adapter.get("status", "").lower() != "up":
            continue
        if _is_virtual_interface(alias, adapter.get("description", "")):
            continue
        state = _interface_state(alias)
        if not state.get("ok"):
            continue
        raw_servers = [str(item).strip() for item in state.get("servers", [])]
        if any(server in LOOPBACK_DNS for server in raw_servers):
            targets.append((alias, raw_servers))

    if not targets:
        return True
    if not _is_admin():
        LOGGER.warning("[DNS] Administrator rights required to repair loopback DNS.")
        return False

    repaired = 0
    failed = []
    for alias, raw_servers in targets:
        fallback = _clean_ipv4(raw_servers) or None
        LOGGER.warning("[DNS] Stale loopback DNS on '%s'; restoring %s.", alias, fallback or "DHCP")
        if _apply_interface_servers(alias, fallback):
            state = _interface_state(alias)
            servers = [str(item).strip() for item in state.get("servers", [])]
            if state.get("ok") and not any(server in LOOPBACK_DNS for server in servers):
                repaired += 1
                continue
        failed.append(alias)

    if repaired:
        _flush_dns()
    if failed:
        LOGGER.error("[DNS] Could not repair loopback DNS on: %s", ", ".join(failed))
        return False
    return True


def cleanup_stale_dns():
    """
    Startup/repair entry point. Restores any orphaned DNS journal, or resets
    interfaces stuck on loopback when no resolver is running.
    """
    if platform.system() != "Windows":
        return True

    journal = _load_journal()
    if journal is None:
        journal = _migrate_legacy_backup()

    if journal is not None:
        port = int(journal.get("resolver_port") or DNS_LISTEN_PORT)
        if _probe_resolver(port=port):
            # A live resolver (probably the current agent) owns this state.
            return True
        return _restore_dns_from_journal()

    if _probe_resolver(port=DNS_LISTEN_PORT):
        return True
    return _repair_loopback_interfaces()


# ---------------------------------------------------------------------------
# DNS packet helpers (RFC 1035 minimal implementation)
# ---------------------------------------------------------------------------
def _parse_dns_name(data, offset):
    """Parse a domain name from a DNS packet, handling compression pointers."""
    labels = []
    jumped = False
    original_offset = offset
    max_jumps = 20  # prevent infinite loops

    for _ in range(max_jumps):
        if offset >= len(data):
            break

        length = data[offset]

        if length == 0:
            offset += 1
            break

        # Compression pointer (top 2 bits set)
        if (length & 0xC0) == 0xC0:
            if offset + 1 >= len(data):
                break
            pointer = struct.unpack("!H", data[offset:offset + 2])[0] & 0x3FFF
            if not jumped:
                original_offset = offset + 2
            offset = pointer
            jumped = True
            continue

        offset += 1
        if offset + length > len(data):
            break
        labels.append(data[offset:offset + length].decode("ascii", errors="ignore"))
        offset += length

    name = ".".join(labels).lower()
    return name, (original_offset if jumped else offset)


def _build_dns_response_blocked(query_data):
    """
    Build a DNS response that resolves the queried domain to 127.0.0.1.
    Returns the raw bytes of the response packet.
    """
    if len(query_data) < 12:
        return None

    # Transaction ID
    tid = query_data[:2]

    # Flags: standard response, no error, authoritative
    flags = struct.pack("!H", 0x8580)

    # Question count (copy from query), Answer count = 1
    qd_count = struct.unpack("!H", query_data[4:6])[0]
    an_count = struct.pack("!H", 1)
    ns_count = struct.pack("!H", 0)
    ar_count = struct.pack("!H", 0)

    header = tid + flags + struct.pack("!H", qd_count) + an_count + ns_count + ar_count

    # Copy the question section from the query
    offset = 12
    for _ in range(qd_count):
        _, offset = _parse_dns_name(query_data, offset)
        offset += 4  # QTYPE (2) + QCLASS (2)

    question_section = query_data[12:offset]

    # Answer section: pointer to name in question + A record → 127.0.0.1
    answer = (
        b"\xc0\x0c"                              # Name pointer to offset 12 (question name)
        + struct.pack("!H", 1)                    # TYPE: A
        + struct.pack("!H", 1)                    # CLASS: IN
        + struct.pack("!I", 60)                   # TTL: 60 seconds
        + struct.pack("!H", 4)                    # RDLENGTH: 4 bytes
        + socket.inet_aton(REDIRECT_IP)            # RDATA: 127.0.0.1
    )

    return header + question_section + answer


def _forward_dns_query(query_data, upstream_ip, upstream_port, timeout=3):
    """Forward a DNS query to the upstream server and return the response."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(query_data, (upstream_ip, upstream_port))
        response, _ = sock.recvfrom(4096)
        return response
    except Exception:
        return None
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# DNS Server Thread
# ---------------------------------------------------------------------------
class _DnsResolverThread(threading.Thread):
    """A lightweight threaded DNS resolver that filters blocked domains."""

    def __init__(self, listen_port, upstream_ip, upstream_port):
        super().__init__(daemon=True, name="DnsResolver")
        self._listen_port = listen_port
        self._upstream_ip = upstream_ip
        self._upstream_port = upstream_port
        self._blocked_domains = set()
        self._lock = threading.Lock()
        self._running = False
        self._sock = None

    def set_blocked_domains(self, domains):
        """Update the set of blocked domains (thread-safe)."""
        with self._lock:
            self._blocked_domains = set()
            for d in domains:
                d = d.strip().lower()
                if d:
                    self._blocked_domains.add(d)
                    if not d.startswith("www."):
                        self._blocked_domains.add(f"www.{d}")

    def clear_blocked_domains(self):
        """Remove all blocked domains."""
        with self._lock:
            self._blocked_domains.clear()

    def _is_blocked(self, domain):
        with self._lock:
            return domain.lower() in self._blocked_domains

    def run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("127.0.0.1", self._listen_port))
            self._sock.settimeout(1.0)  # allow periodic stop checks
            self._running = True
            LOGGER.info("[DNS] Resolver listening on 127.0.0.1:%s", self._listen_port)
        except OSError as err:
            LOGGER.error("[DNS] Failed to bind to port %s: %s", self._listen_port, err)
            self._running = False
            return

        while self._running:
            try:
                data, addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    LOGGER.warning("[DNS] Socket error, stopping resolver")
                break

            if len(data) < 12:
                continue

            # Parse the queried domain name
            qname, _ = _parse_dns_name(data, 12)

            if self._is_blocked(qname):
                LOGGER.info("[DNS] BLOCKED: %s → %s", qname, REDIRECT_IP)
                response = _build_dns_response_blocked(data)
                if response:
                    self._sock.sendto(response, addr)
            else:
                # Forward to upstream
                response = _forward_dns_query(data, self._upstream_ip, self._upstream_port)
                if response:
                    self._sock.sendto(response, addr)

        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        LOGGER.info("[DNS] Resolver stopped")

    def stop(self):
        """Signal the resolver thread to stop."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# DNS Enforcement Engine
# ---------------------------------------------------------------------------
class DnsEnforcementEngine(EnforcementEngine):
    """Production enforcement engine using a local DNS resolver."""

    def __init__(self):
        self._resolver: Optional[_DnsResolverThread] = None
        self._interface: Optional[str] = None
        self._dns_redirected = False

        # Register atexit handler to ensure DNS is always restored
        atexit.register(self._emergency_restore)

    @property
    def name(self) -> str:
        return "DNS Resolver Engine"

    def is_available(self) -> bool:
        """Check if we can bind to the DNS port and run netsh."""
        system = platform.system()
        if system != "Windows":
            LOGGER.warning("[DNS] DNS engine currently supports Windows only")
            return False

        # Check if port 53 is available
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            test_sock.bind(("127.0.0.1", DNS_LISTEN_PORT))
            test_sock.close()
            return True
        except OSError as err:
            LOGGER.warning("[DNS] Port %s is not available: %s", DNS_LISTEN_PORT, err)
            LOGGER.warning("[DNS] Try stopping the 'DNS Client' service: net stop dnscache")
            test_sock.close()
            return False

    def apply_rules(self, domains: List[str]) -> bool:
        """Start the DNS resolver (if not running) and block the given domains."""
        # Repair any state left behind by a previous crashed run before touching
        # the network again. A live resolver (this one) makes this a no-op.
        try:
            cleanup_stale_dns()
        except Exception as err:
            LOGGER.warning("[DNS] Startup DNS cleanup: %s", err)

        # 1. Start the resolver thread if needed
        if self._resolver is None or not self._resolver.is_alive():
            self._resolver = _DnsResolverThread(DNS_LISTEN_PORT, DNS_UPSTREAM, DNS_UPSTREAM_PORT)
            self._resolver.start()
            # Give it a moment to bind
            time.sleep(0.3)
            if not self._resolver._running:
                LOGGER.error("[DNS] Resolver failed to start")
                return False

        # 2. Update blocked domains
        self._resolver.set_blocked_domains(domains)
        LOGGER.info("[DNS] Blocking %s domains (+ www variants)", len(domains))

        # 3. Never redirect unless the resolver actually answers on port 53.
        if not _probe_resolver(port=DNS_LISTEN_PORT):
            LOGGER.error(
                "[DNS] Local resolver did not answer on port %s; refusing to redirect system DNS.",
                DNS_LISTEN_PORT,
            )
            return False

        # 4. Redirect system DNS to 127.0.0.1 (only on first successful apply)
        if not self._dns_redirected:
            interfaces = _get_windows_dns_interfaces()
            if not interfaces:
                LOGGER.error("[DNS] No safe physical default-route interface found; not redirecting DNS.")
                return False

            journal = _load_journal()
            created_journal = journal is None
            if journal is None:
                journal = {
                    "version": DNS_JOURNAL_VERSION,
                    "status": "pending",
                    "created_at_utc": _utc_now(),
                    "resolver_port": DNS_LISTEN_PORT,
                    "adapters": {},
                    "last_error": None,
                }

            for alias in interfaces:
                if alias in journal["adapters"] and not journal["adapters"][alias].get("restored"):
                    continue
                snapshot = _snapshot_interface(alias)
                if snapshot:
                    journal["adapters"][alias] = snapshot
            if not journal["adapters"]:
                LOGGER.error("[DNS] Could not snapshot any interface; refusing DNS redirect.")
                return False
            if not _write_journal(journal):
                LOGGER.error("[DNS] DNS journal is not writable; refusing DNS redirect.")
                return False

            changed = False
            for alias in interfaces:
                entry = journal["adapters"].get(alias)
                if not entry or entry.get("restored"):
                    continue
                if _apply_interface_servers(alias, ["127.0.0.1"]):
                    # Record the mutation before verification so even a crash
                    # between apply and verify remains recoverable.
                    entry["changed"] = True
                    entry["applied_at_utc"] = _utc_now()
                    state = _interface_state(alias)
                    servers = [str(item).strip() for item in state.get("servers", [])]
                    if state.get("ok") and "127.0.0.1" in servers:
                        changed = True
                        LOGGER.info("[DNS] System DNS redirected to local resolver on '%s'", alias)
                    else:
                        journal["last_error"] = f"verification failed for '{alias}'"
                        LOGGER.error("[DNS] Redirect verification failed on '%s'", alias)
                else:
                    journal["last_error"] = f"failed to configure '{alias}'"
                    LOGGER.error("[DNS] Failed to redirect DNS on '%s'", alias)
                _write_journal(journal)

            if not changed:
                if created_journal:
                    _remove_journal()
                self._dns_redirected = False
                return False

            journal["status"] = "enforced"
            _write_journal(journal)
            self._interface = interfaces[0]
            self._dns_redirected = True

        return True

    def ensure_resolver_healthy(self) -> bool:
        """Periodic watchdog: restore DNS if the local resolver stops answering."""
        if not self._dns_redirected:
            return True
        if _probe_resolver(port=DNS_LISTEN_PORT):
            return True
        LOGGER.error("[DNS] Local resolver stopped answering; restoring original system DNS.")
        self.restore_rules()
        return False

    def restore_rules(self) -> bool:
        """Stop blocking: clear the domain list and restore original DNS (verified)."""
        # 1. Clear blocked domains (resolver keeps running for forwarding)
        if self._resolver and self._resolver.is_alive():
            self._resolver.clear_blocked_domains()

        # 2. Restore original DNS from the durable journal, even if this process
        #    never set _dns_redirected (for example after a crash and restart).
        restored = _restore_dns_from_journal()
        if restored:
            self._dns_redirected = False
            self._interface = None

        if restored:
            LOGGER.info("[DNS] All rules cleared, original DNS restored")
        else:
            LOGGER.error("[DNS] DNS restore pending; journal retained for the next run")
        return restored

    def shutdown(self) -> None:
        """Cleanup on agent shutdown."""
        self.restore_rules()
        if self._resolver and self._resolver.is_alive():
            self._resolver.stop()

    def _emergency_restore(self):
        """atexit handler — ensures DNS is restored even on unexpected exit."""
        if self._dns_redirected or _load_journal() is not None:
            LOGGER.warning("[DNS] Emergency restore triggered (atexit)")
            try:
                _restore_dns_from_journal()
            except Exception as err:
                LOGGER.error("[DNS] Emergency restore failed: %s", err)

        if self._resolver and self._resolver.is_alive():
            self._resolver.stop()

    def __del__(self):
        """Destructor — best-effort cleanup."""
        try:
            if self._dns_redirected or _load_journal() is not None:
                _restore_dns_from_journal()
            if self._resolver and self._resolver.is_alive():
                self._resolver.stop()
        except Exception:
            pass
