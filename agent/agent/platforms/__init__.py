"""
Unified Platform Adapter Factory for Academia Shield.
"""

import sys
from typing import Dict, Any

from .base import (
    PlatformCapabilityStatus,
    PlatformStatusResult,
    PlatformSecureStorage,
    PlatformServiceLifecycle,
    PlatformProcessMonitor,
    PlatformDnsEnforcement,
    PlatformBrowserCompliance,
    PlatformApplicationControlCompliance,
    PlatformUsbStorageCompliance,
    PlatformInstaller,
    PlatformUninstaller
)

from .windows import (
    WindowsSecureStorage,
    WindowsServiceLifecycle,
    WindowsProcessMonitor,
    WindowsDnsEnforcement,
    WindowsBrowserCompliance,
    WindowsApplicationControlCompliance,
    WindowsUsbStorageCompliance,
    WindowsInstaller,
    WindowsUninstaller
)

from .macos import (
    MacosSecureStorage,
    MacosServiceLifecycle,
    MacosProcessMonitor,
    MacosDnsEnforcement,
    MacosBrowserCompliance,
    MacosApplicationControlCompliance,
    MacosUsbStorageCompliance,
    MacosInstaller,
    MacosUninstaller
)

class PlatformBundle:
    def __init__(
        self,
        platform_name: str,
        storage: PlatformSecureStorage,
        service: PlatformServiceLifecycle,
        process_monitor: PlatformProcessMonitor,
        dns: PlatformDnsEnforcement,
        browser_compliance: PlatformBrowserCompliance,
        app_control_compliance: PlatformApplicationControlCompliance,
        usb_compliance: PlatformUsbStorageCompliance,
        installer: PlatformInstaller,
        uninstaller: PlatformUninstaller
    ):
        self.platform_name = platform_name
        self.storage = storage
        self.service = service
        self.process_monitor = process_monitor
        self.dns = dns
        self.browser_compliance = browser_compliance
        self.app_control_compliance = app_control_compliance
        self.usb_compliance = usb_compliance
        self.installer = installer
        self.uninstaller = uninstaller

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "platform": self.platform_name,
            "service_status": self.service.get_status().to_dict(),
            "process_monitor_status": self.process_monitor.get_status().to_dict(),
            "dns_enforcement_status": self.dns.get_status().to_dict(),
            "browser_compliance": self.browser_compliance.check_compliance().to_dict(),
            "app_control_compliance": self.app_control_compliance.check_compliance().to_dict(),
            "usb_storage_compliance": self.usb_compliance.check_compliance().to_dict()
        }


def get_platform_bundle(force_platform: str = None) -> PlatformBundle:
    target_platform = force_platform or sys.platform

    if target_platform.startswith("win"):
        return PlatformBundle(
            platform_name="windows",
            storage=WindowsSecureStorage(),
            service=WindowsServiceLifecycle(),
            process_monitor=WindowsProcessMonitor(),
            dns=WindowsDnsEnforcement(),
            browser_compliance=WindowsBrowserCompliance(),
            app_control_compliance=WindowsApplicationControlCompliance(),
            usb_compliance=WindowsUsbStorageCompliance(),
            installer=WindowsInstaller(),
            uninstaller=WindowsUninstaller()
        )
    elif target_platform == "darwin" or target_platform == "macos":
        return PlatformBundle(
            platform_name="macos",
            storage=MacosSecureStorage(),
            service=MacosServiceLifecycle(),
            process_monitor=MacosProcessMonitor(),
            dns=MacosDnsEnforcement(),
            browser_compliance=MacosBrowserCompliance(),
            app_control_compliance=MacosApplicationControlCompliance(),
            usb_compliance=MacosUsbStorageCompliance(),
            installer=MacosInstaller(),
            uninstaller=MacosUninstaller()
        )
    else:
        # Generic posix / linux fallback
        return PlatformBundle(
            platform_name="generic",
            storage=WindowsSecureStorage(),
            service=WindowsServiceLifecycle(),
            process_monitor=WindowsProcessMonitor(),
            dns=WindowsDnsEnforcement(),
            browser_compliance=WindowsBrowserCompliance(),
            app_control_compliance=WindowsApplicationControlCompliance(),
            usb_compliance=WindowsUsbStorageCompliance(),
            installer=WindowsInstaller(),
            uninstaller=WindowsUninstaller()
        )
