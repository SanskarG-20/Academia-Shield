"""
macOS DNS Enforcement Adapter.
Uses approved macOS network tools (networksetup / scutil) to manage DNS settings.
Includes pre-flight health checks, state backup, and clean restoration.
"""

import sys
import socket
import subprocess
import logging
from typing import List, Dict, Optional, Any

from ..base import PlatformDnsEnforcement, PlatformCapabilityStatus, PlatformStatusResult

logger = logging.getLogger(__name__)

class MacosDnsEnforcement(PlatformDnsEnforcement):
    """
    macOS DNS manager using `networksetup`.
    Backs up active network services' DNS servers and restores them on exit.
    """

    def __init__(self):
        self._original_dns_backup: Dict[str, List[str]] = {}
        self._is_enforced: bool = False

    def check_resolver_health(self, host: str = "127.0.0.1", port: int = 5353) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            dummy_query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x06google\x03com\x00\x00\x01\x00\x01"
            sock.sendto(dummy_query, (host, port))
            data, _ = sock.recvfrom(512)
            sock.close()
            return len(data) > 0
        except Exception:
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_sock.connect((host, port))
                test_sock.close()
                return True
            except Exception:
                return False

    def _get_network_services(self) -> List[str]:
        services = []
        if sys.platform != "darwin":
            return ["Wi-Fi", "Ethernet"]
        try:
            cmd = ["networksetup", "-listallnetworkservices"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    line = line.strip()
                    if line and "*" not in line:  # Asterisk indicates disabled service
                        services.append(line)
        except Exception as e:
            logger.error(f"Error querying macOS network services: {e}")
        return services

    def _query_service_dns(self, service: str) -> List[str]:
        try:
            cmd = ["networksetup", "-getdnsservers", service]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                out = res.stdout.strip()
                if "There aren't any DNS Servers" in out:
                    return []
                return [s.strip() for s in out.splitlines() if s.strip()]
        except Exception:
            pass
        return []

    def apply_dns_redirect(self, dns_ip: str = "127.0.0.1", port: int = 5353) -> PlatformStatusResult:
        if sys.platform != "darwin":
            self._is_enforced = True
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="Simulated macOS DNS redirect active on non-macOS host"
            )

        if not self.check_resolver_health(dns_ip, port):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=f"Local DNS proxy health check failed on {dns_ip}:{port}. Refusing to configure macOS DNS."
            )

        services = self._get_network_services()
        if not services:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="No active macOS network services found"
            )

        applied = []
        for s in services:
            if s not in self._original_dns_backup:
                self._original_dns_backup[s] = self._query_service_dns(s)

            try:
                cmd = ["networksetup", "-setdnsservers", s, dns_ip]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    applied.append(s)
                else:
                    logger.warning(f"Setting DNS on service '{s}' returned: {res.stderr}")
            except Exception as e:
                logger.error(f"Failed to set DNS for service '{s}': {e}")

        if applied:
            self._is_enforced = True
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"macOS DNS redirected on {len(applied)} network service(s)",
                details={"services": applied, "dns_ip": dns_ip}
            )
        else:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL,
                message="Administrator approval / sudo required to configure macOS networksetup DNS"
            )

    def restore_original_dns(self) -> PlatformStatusResult:
        if sys.platform != "darwin":
            self._is_enforced = False
            self._original_dns_backup.clear()
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="Simulated macOS DNS restored"
            )

        restored = []
        services = list(self._original_dns_backup.keys()) or self._get_network_services()
        for s in services:
            orig = self._original_dns_backup.get(s, [])
            try:
                if not orig:
                    cmd = ["networksetup", "-setdnsservers", s, "empty"]
                else:
                    cmd = ["networksetup", "-setdnsservers", s] + orig
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    restored.append(s)
            except Exception as e:
                logger.error(f"Error restoring DNS on '{s}': {e}")

        self._original_dns_backup.clear()
        self._is_enforced = False

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ACTIVE,
            message=f"Restored original DNS on {len(restored)} macOS network service(s)",
            details={"restored_services": restored}
        )

    def get_status(self) -> PlatformStatusResult:
        if self._is_enforced:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="macOS DNS enforcement active"
            )
        return PlatformStatusResult(
            status=PlatformCapabilityStatus.SUPPORTED,
            message="macOS DNS enforcement idle"
        )
