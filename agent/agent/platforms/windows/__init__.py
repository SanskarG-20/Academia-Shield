"""
Windows Platform Adapters for Academia Shield.
"""

from .storage import WindowsSecureStorage
from .service import WindowsServiceLifecycle
from .process_monitor import WindowsProcessMonitor
from .dns import WindowsDnsEnforcement
from .compliance import (
    WindowsBrowserCompliance,
    WindowsApplicationControlCompliance,
    WindowsUsbStorageCompliance
)
from .installer import WindowsInstaller, WindowsUninstaller

__all__ = [
    "WindowsSecureStorage",
    "WindowsServiceLifecycle",
    "WindowsProcessMonitor",
    "WindowsDnsEnforcement",
    "WindowsBrowserCompliance",
    "WindowsApplicationControlCompliance",
    "WindowsUsbStorageCompliance",
    "WindowsInstaller",
    "WindowsUninstaller"
]
