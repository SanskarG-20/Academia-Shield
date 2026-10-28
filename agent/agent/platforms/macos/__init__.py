"""
macOS Platform Adapters for Academia Shield.
"""

from .storage import MacosSecureStorage
from .service import MacosServiceLifecycle
from .process_monitor import MacosProcessMonitor
from .dns import MacosDnsEnforcement
from .compliance import (
    MacosBrowserCompliance,
    MacosApplicationControlCompliance,
    MacosUsbStorageCompliance
)
from .installer import MacosInstaller, MacosUninstaller

__all__ = [
    "MacosSecureStorage",
    "MacosServiceLifecycle",
    "MacosProcessMonitor",
    "MacosDnsEnforcement",
    "MacosBrowserCompliance",
    "MacosApplicationControlCompliance",
    "MacosUsbStorageCompliance",
    "MacosInstaller",
    "MacosUninstaller"
]
