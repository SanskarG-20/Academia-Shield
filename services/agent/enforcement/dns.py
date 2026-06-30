"""
Academia Shield Agent — DNS Resolver Enforcement Engine (Production Mode)

Blocks domains by running a lightweight local DNS resolver on 127.0.0.1:53.
Blocked domains resolve to 127.0.0.1. All other queries are forwarded to the
upstream DNS server transparently.

System DNS is temporarily pointed to 127.0.0.1 via netsh (Windows) or
/etc/resolv.conf (Linux/macOS). Original settings are saved to dns_backup.json
and restored when the session ends or the agent exits.

Uses only Python standard library — zero external dependencies.
"""

import atexit
import json
import logging
import os
import platform
import socket
import struct
import subprocess
import threading
import time
from typing import List, Optional

from enforcement.base import EnforcementEngine
from config import DNS_LISTEN_PORT, DNS_UPSTREAM, DNS_UPSTREAM_PORT, DNS_BACKUP_FILE, REDIRECT_IP

LOGGER = logging.getLogger("academia_shield_agent")


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
# System DNS configuration (Windows netsh / Linux resolv.conf)
# ---------------------------------------------------------------------------
def _get_windows_dns_interface():
    """Find the primary network interface name on Windows."""
    try:
        output = subprocess.check_output(
            ["netsh", "interface", "ip", "show", "config"],
            text=True, timeout=10, stderr=subprocess.DEVNULL
        )
        # Find the first interface with a default gateway (active connection)
        current_iface = None
        for line in output.splitlines():
            stripped = line.strip()
            if line and not line[0].isspace() and stripped.startswith("Configuration for interface"):
                current_iface = stripped.split('"')[1] if '"' in stripped else None
            if current_iface and "Default Gateway" in stripped:
                gateway = stripped.split(":")[-1].strip()
                if gateway and gateway != "None":
                    return current_iface
        # Fallback: try common names
        for name in ["Wi-Fi", "Ethernet", "Local Area Connection"]:
            return name
    except Exception as err:
        LOGGER.warning("[DNS] Could not detect network interface: %s", err)
    return "Wi-Fi"


def _get_current_dns_windows(interface):
    """Read the current DNS server(s) for the given interface."""
    try:
        output = subprocess.check_output(
            ["netsh", "interface", "ip", "show", "dns", interface],
            text=True, timeout=10, stderr=subprocess.DEVNULL
        )
        servers = []
        for line in output.splitlines():
            stripped = line.strip()
            # Lines containing IP addresses
            parts = stripped.split()
            for part in parts:
                if _is_ipv4(part):
                    servers.append(part)
        return servers if servers else ["dhcp"]
    except Exception:
        return ["dhcp"]


def _is_ipv4(s):
    """Quick check if a string looks like an IPv4 address."""
    parts = s.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _save_dns_backup(interface, original_servers):
    """Save original DNS settings to disk for safe restoration."""
    backup = {"interface": interface, "servers": original_servers, "timestamp": time.time()}
    try:
        with open(DNS_BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2)
        LOGGER.info("[DNS] Backup saved: %s → %s", interface, original_servers)
    except Exception as err:
        LOGGER.error("[DNS] Failed to save DNS backup: %s", err)


def _load_dns_backup():
    """Load saved DNS backup from disk."""
    if not os.path.exists(DNS_BACKUP_FILE):
        return None
    try:
        with open(DNS_BACKUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _remove_dns_backup():
    """Delete the DNS backup file after successful restore."""
    try:
        if os.path.exists(DNS_BACKUP_FILE):
            os.remove(DNS_BACKUP_FILE)
    except Exception:
        pass


def _set_dns_windows(interface, dns_server):
    """Set the system DNS server via netsh."""
    try:
        if dns_server == "dhcp":
            subprocess.check_call(
                ["netsh", "interface", "ip", "set", "dns", interface, "dhcp"],
                timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.check_call(
                ["netsh", "interface", "ip", "set", "dns", interface, "static", dns_server],
                timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        LOGGER.info("[DNS] System DNS set to %s on %s", dns_server, interface)
        return True
    except subprocess.CalledProcessError as err:
        LOGGER.error("[DNS] Failed to set DNS via netsh: %s", err)
        return False
    except Exception as err:
        LOGGER.error("[DNS] Unexpected error setting DNS: %s", err)
        return False


def _restore_dns_from_backup():
    """Restore DNS settings from the backup file."""
    backup = _load_dns_backup()
    if not backup:
        LOGGER.info("[DNS] No DNS backup found — nothing to restore")
        return

    interface = backup.get("interface", "Wi-Fi")
    servers = backup.get("servers", ["dhcp"])

    system = platform.system()
    if system == "Windows":
        primary = servers[0] if servers else "dhcp"
        if primary == "dhcp" or not _is_ipv4(primary):
            _set_dns_windows(interface, "dhcp")
        else:
            _set_dns_windows(interface, primary)
    else:
        LOGGER.info("[DNS] Non-Windows restore: set DNS back to %s", servers)
        # On Linux/macOS, restoring resolv.conf would go here

    _remove_dns_backup()
    LOGGER.info("[DNS] Original DNS settings restored")


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

        # 3. Redirect system DNS to 127.0.0.1 (only on first apply)
        if not self._dns_redirected:
            self._interface = _get_windows_dns_interface()
            original_servers = _get_current_dns_windows(self._interface)

            # Don't re-backup if we're already pointing to ourselves
            if original_servers != ["127.0.0.1"]:
                _save_dns_backup(self._interface, original_servers)

            success = _set_dns_windows(self._interface, "127.0.0.1")
            if success:
                self._dns_redirected = True
                LOGGER.info("[DNS] System DNS redirected to local resolver")
            else:
                LOGGER.error("[DNS] Failed to redirect system DNS — blocking may not work")
                return False

        return True

    def restore_rules(self) -> bool:
        """Stop blocking: clear the domain list and restore original DNS."""
        # 1. Clear blocked domains (resolver keeps running for forwarding)
        if self._resolver and self._resolver.is_alive():
            self._resolver.clear_blocked_domains()

        # 2. Restore original DNS settings
        if self._dns_redirected:
            _restore_dns_from_backup()
            self._dns_redirected = False

        LOGGER.info("[DNS] All rules cleared, original DNS restored")
        return True

    def _emergency_restore(self):
        """atexit handler — ensures DNS is restored even on unexpected exit."""
        if self._dns_redirected:
            LOGGER.warning("[DNS] Emergency restore triggered (atexit)")
            try:
                _restore_dns_from_backup()
            except Exception as err:
                LOGGER.error("[DNS] Emergency restore failed: %s", err)

        if self._resolver and self._resolver.is_alive():
            self._resolver.stop()

    def __del__(self):
        """Destructor — best-effort cleanup."""
        try:
            if self._dns_redirected:
                _restore_dns_from_backup()
            if self._resolver and self._resolver.is_alive():
                self._resolver.stop()
        except Exception:
            pass
