"""
Agent Platform Adapters Package.
"""
import sys
from .base import BasePlatformAdapter
from .windows import WindowsPlatformAdapter
from .posix import PosixPlatformAdapter

def get_platform_adapter() -> BasePlatformAdapter:
    """Return platform adapter based on host OS."""
    if sys.platform == "win32":
        return WindowsPlatformAdapter()
    return PosixPlatformAdapter()

from .windows_dns import WindowsDNSAdapterManager
from .windows_hosts import HostsEnforcementEngine
from .usb_compliance import USBComplianceManager

__all__ = [
    "BasePlatformAdapter",
    "WindowsPlatformAdapter",
    "PosixPlatformAdapter",
    "WindowsDNSAdapterManager",
    "HostsEnforcementEngine",
    "USBComplianceManager",
    "get_platform_adapter"
]
