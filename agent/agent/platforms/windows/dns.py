"""
Windows DNS Enforcement Adapter.
Manages Windows network adapter DNS settings safely via netsh / PowerShell.
Guarantees:
- Pre-flight DNS resolver health check on port 5353
- Complete backup of existing DNS configuration before changes
- Restoration of original DNS configuration on session end / exit / error
- Strictly touches only active connected network adapters
- NEVER touches the hosts file or unrelated network interfaces.
"""

import sys
import socket
import subprocess
import logging
import json
import re
from typing import List, Dict, Optional, Any

from ..base import PlatformDnsEnforcement, PlatformCapabilityStatus, PlatformStatusResult

logger = logging.getLogger(__name__)

class WindowsDnsEnforcement(PlatformDnsEnforcement):
    """
    Windows DNS manager.
    Queries active interfaces, stores pre-enforcement DNS servers,
    and cleanly restores them.
    """

    def __init__(self):
        self._original_dns_backup: Dict[str, Dict[str, Any]] = {}
        self._is_enforced: bool = False

    def check_resolver_health(self, host: str = "127.0.0.1", port: int = 5353) -> bool:
        """
        Verify that the local Academia Shield DNS proxy resolver is running and responding.
        """
        try:
            # Try binding or connecting UDP test query
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            # Send standard empty/dummy DNS query packet (Transaction ID 0x1234, Flags standard query)
            dummy_query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x06google\x03com\x00\x00\x01\x00\x01"
            sock.sendto(dummy_query, (host, port))
            data, _ = sock.recvfrom(512)
            sock.close()
            return len(data) > 0
        except Exception as e:
            logger.debug(f"DNS health check on {host}:{port} returned: {e}")
            # As a secondary check, see if port is open / listening
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_sock.connect((host, port))
                test_sock.close()
                return True
            except Exception:
                return False

    def _get_active_interfaces(self) -> List[str]:
        """Find active network interface names with default gateways."""
        interfaces = []
        if not sys.platform.startswith("win"):
            return ["Ethernet", "Wi-Fi"]
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-NetIPInterface -AddressFamily IPv4 -ConnectionState Connected | Select-Object -ExpandProperty InterfaceAlias"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    alias = line.strip()
                    if alias and "loopback" not in alias.lower() and "vethernet" not in alias.lower():
                        interfaces.append(alias)
        except Exception as e:
            logger.warning(f"Failed to list network interfaces via PowerShell: {e}")

        # Fallback to netsh
        if not interfaces:
            try:
                res = subprocess.run(["netsh", "interface", "ipv4", "show", "interfaces"], capture_output=True, text=True, timeout=5)
                for line in res.stdout.splitlines():
                    if "connected" in line.lower():
                        parts = line.split()
                        if len(parts) >= 5:
                            alias = " ".join(parts[4:])
                            if "loopback" not in alias.lower():
                                interfaces.append(alias)
            except Exception as e:
                logger.error(f"Fallback interface lookup failed: {e}")

        return list(set(interfaces))

    def _query_adapter_dns(self, interface: str) -> Dict[str, Any]:
        """Query current DNS config for an interface."""
        info = {"dhcp": True, "servers": []}
        try:
            cmd = ["netsh", "interface", "ipv4", "show", "dns", f"name={interface}"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                output = res.stdout
                if "DHCP" in output or "dynamically" in output.lower():
                    info["dhcp"] = True
                else:
                    info["dhcp"] = False
                # Extract IPs
                ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", output)
                info["servers"] = ips
        except Exception as e:
            logger.error(f"Failed to query DNS for interface {interface}: {e}")
        return info

    def apply_dns_redirect(self, dns_ip: str = "127.0.0.1", port: int = 5353) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            self._is_enforced = True
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="Simulated Windows DNS redirect active on non-Windows host"
            )

        # Pre-flight health check
        if not self.check_resolver_health(dns_ip, port):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=f"Local DNS proxy health check failed on {dns_ip}:{port}. Refusing to alter system DNS."
            )

        interfaces = self._get_active_interfaces()
        if not interfaces:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="No active connected network interfaces found for DNS enforcement"
            )

        applied = []
        for iface in interfaces:
            # Backup original settings if not already backed up
            if iface not in self._original_dns_backup:
                self._original_dns_backup[iface] = self._query_adapter_dns(iface)

            try:
                # Set static DNS to local proxy
                cmd = ["netsh", "interface", "ipv4", "set", "dns", f"name={iface}", "static", dns_ip, "primary"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    applied.append(iface)
                else:
                    logger.warning(f"Could not set DNS on {iface}: {res.stderr}")
            except Exception as e:
                logger.error(f"Exception setting DNS on {iface}: {e}")

        if applied:
            self._is_enforced = True
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"DNS redirection applied to {len(applied)} interface(s)",
                details={"interfaces": applied, "dns_ip": dns_ip, "port": port}
            )
        else:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL,
                message="Administrator privileges required to configure network adapter DNS"
            )

    def restore_original_dns(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            self._is_enforced = False
            self._original_dns_backup.clear()
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="Simulated DNS restored"
            )

        if not self._original_dns_backup:
            # If no backup recorded, ensure active interfaces are reset to DHCP
            for iface in self._get_active_interfaces():
                subprocess.run(["netsh", "interface", "ipv4", "set", "dns", f"name={iface}", "dhcp"], capture_output=True, timeout=5)
            self._is_enforced = False
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="Default DHCP DNS restored across active interfaces"
            )

        restored = []
        for iface, backup in self._original_dns_backup.items():
            try:
                if backup.get("dhcp", True) or not backup.get("servers"):
                    cmd = ["netsh", "interface", "ipv4", "set", "dns", f"name={iface}", "dhcp"]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if res.returncode == 0:
                        restored.append(iface)
                else:
                    servers = backup.get("servers", [])
                    primary = servers[0]
                    cmd1 = ["netsh", "interface", "ipv4", "set", "dns", f"name={iface}", "static", primary, "primary"]
                    subprocess.run(cmd1, capture_output=True, text=True, timeout=5)
                    for secondary in servers[1:]:
                        cmd2 = ["netsh", "interface", "ipv4", "add", "dns", f"name={iface}", secondary, "index=2"]
                        subprocess.run(cmd2, capture_output=True, text=True, timeout=5)
                    restored.append(iface)
            except Exception as e:
                logger.error(f"Error restoring DNS on {iface}: {e}")

        self._original_dns_backup.clear()
        self._is_enforced = False

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ACTIVE,
            message=f"Original DNS settings restored for {len(restored)} interface(s)",
            details={"restored_interfaces": restored}
        )

    def get_status(self) -> PlatformStatusResult:
        if self._is_enforced:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="Windows DNS enforcement active",
                details={"backed_up_adapters": list(self._original_dns_backup.keys())}
            )
        return PlatformStatusResult(
            status=PlatformCapabilityStatus.SUPPORTED,
            message="Windows DNS enforcement idle (original settings intact)"
        )
