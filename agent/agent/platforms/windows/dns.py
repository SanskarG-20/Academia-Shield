"""
Windows DNS Enforcement Adapter.

Delegates all adapter mutation and restoration to the durable
WindowsDNSAdapterManager.  This adapter can never hold the only copy of the
original configuration: the journal is written to disk before the first change
and survives crashes, reboots and forced termination.

Guarantees:
- Refuses to redirect an adapter unless the resolver listens on DNS port 53.
- Backs up the exact pre-enforcement DNS state in a machine-wide journal.
- Restoration is verified before the journal is removed.
- Only the physical default-route adapter is touched.
"""

import sys
import logging
from typing import Optional

from ..base import PlatformDnsEnforcement, PlatformCapabilityStatus, PlatformStatusResult
from ...platform.windows_dns import WindowsDNSAdapterManager, probe_local_resolver

logger = logging.getLogger(__name__)


class WindowsDnsEnforcement(PlatformDnsEnforcement):
    """Windows DNS manager backed by the crash-safe adapter journal."""

    def __init__(self, manager: Optional[WindowsDNSAdapterManager] = None):
        self._manager = manager or WindowsDNSAdapterManager()
        self._is_enforced = False

    def check_resolver_health(self, host: str = "127.0.0.1", port: int = 5353) -> bool:
        """Verify that the local Academia Shield DNS resolver responds."""
        return probe_local_resolver(host=host, port=port)

    def apply_dns_redirect(self, dns_ip: str = "127.0.0.1", port: int = 5353) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            self._is_enforced = True
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="Simulated Windows DNS redirect active on non-Windows host",
            )

        # Windows always sends DNS to port 53.  A resolver on any other port
        # cannot answer adapter traffic, so redirecting would black-hole DNS.
        if port != 53:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=(
                    f"Refusing adapter DNS redirect: resolver listens on port {port}, "
                    "but Windows DNS requires port 53."
                ),
            )

        if not self.check_resolver_health(dns_ip, port):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=f"Local DNS resolver health check failed on {dns_ip}:{port}. Refusing to alter system DNS.",
            )

        configured = self._manager.configure_local_dns(
            target_dns=dns_ip,
            resolver_healthy=True,
            resolver_port=port,
        )
        if configured:
            self._is_enforced = True
            status = self._manager.get_status()
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="DNS redirection applied and journaled",
                details=status,
            )

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL,
            message=(
                "DNS redirection was not applied. Administrator privileges and a physical "
                "default-route adapter are required."
            ),
        )

    def restore_original_dns(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            self._is_enforced = False
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="Simulated DNS restored",
            )

        restored = self._manager.restore_original_dns()
        self._is_enforced = False
        if restored:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="Original DNS settings verified and restored",
            )
        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ERROR,
            message=(
                "DNS restoration pending. The recovery journal was kept and the "
                "background recovery guard will retry."
            ),
        )

    def get_status(self) -> PlatformStatusResult:
        journal = self._manager.get_status()
        if journal.get("enforcement_active"):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="Windows DNS enforcement active",
                details=journal,
            )
        return PlatformStatusResult(
            status=PlatformCapabilityStatus.SUPPORTED,
            message="Windows DNS enforcement idle (original settings intact)",
            details=journal,
        )
