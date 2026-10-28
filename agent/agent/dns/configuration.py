"""
DNS Configuration Lifecycle & Drift Monitoring Engine.

Coordinates local DNS server startup, OS adapter DNS redirection, continuous drift detection,
and safe restoration when sessions end, policies expire, or agent is uninstalled.
"""

import time
import logging
from typing import Optional, Dict, Any
from .resolver import LocalDNSResolver
from .upstream import UpstreamResolver
from ..platform.windows_dns import WindowsDNSAdapterManager

LOGGER = logging.getLogger(__name__)

class DNSConfigurationLifecycle:
    """Orchestrates DNS enforcement, drift detection, and safe restoration."""

    def __init__(self, resolver: Optional[LocalDNSResolver] = None):
        self.resolver = resolver or LocalDNSResolver()
        self.windows_adapter = WindowsDNSAdapterManager()
        self.enforcement_enabled = False
        self.adapter_redirected = False

    def enable_enforcement(self, admin_consent: bool = False) -> bool:
        """
        Start local DNS resolver and conditionally redirect Windows network adapter DNS
        if explicit admin consent is provided and elevated rights exist.
        """
        started = self.resolver.start()
        if not started:
            LOGGER.error("Failed starting local DNS resolver")
            return False

        self.enforcement_enabled = True

        if admin_consent and self.windows_adapter.is_admin():
            redirected = self.windows_adapter.configure_local_dns(target_dns="127.0.0.1")
            self.adapter_redirected = redirected
            if redirected:
                LOGGER.info("Successfully redirected system DNS to local resolver")
        
        return True

    def disable_enforcement(self) -> bool:
        """Stop local resolver and restore original network adapter DNS settings."""
        self.enforcement_enabled = False
        
        # Stop resolver
        self.resolver.stop()

        # Restore original DNS configuration
        restored = False
        if self.adapter_redirected or self.windows_adapter.is_admin():
            restored = self.windows_adapter.restore_original_dns()
            self.adapter_redirected = False

        LOGGER.info("DNS Enforcement disabled and original network settings restored.")
        return restored

    def check_drift_and_health(self) -> Dict[str, Any]:
        """
        Check resolver status, upstream health, cache metrics, and OS adapter drift.
        Returns detailed health dictionary.
        """
        metrics = self.resolver.cache.get_metrics()
        upstream_health = self.resolver.upstream.check_health()
        
        drift_detected = False
        if self.adapter_redirected and self.enforcement_enabled:
            drift_detected = self.windows_adapter.detect_drift(expected_dns="127.0.0.1")

        return {
            "enforcement_enabled": self.enforcement_enabled,
            "adapter_redirected": self.adapter_redirected,
            "resolver_healthy": self.resolver.healthy,
            "upstream_healthy": upstream_health.get("healthy", True),
            "drift_detected": drift_detected,
            "cache_metrics": metrics
        }
