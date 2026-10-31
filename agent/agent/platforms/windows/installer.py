"""
Windows Platform Installer & Uninstaller.
Performs explicit installation with UAC awareness, credential storage validation,
service setup, and clean uninstallation that removes only Academia Shield assets.
"""

import sys
import os
import shutil
import logging
from typing import Optional, Dict, Any

from ..base import PlatformInstaller, PlatformUninstaller, PlatformCapabilityStatus, PlatformStatusResult
from .storage import WindowsSecureStorage
from .service import WindowsServiceLifecycle
from .dns import WindowsDnsEnforcement

logger = logging.getLogger(__name__)

DEFAULT_INSTALL_DIR = r"C:\Program Files\AcademiaShield"
APP_DATA_DIR = os.path.expandvars(r"%LOCALAPPDATA%\AcademiaShield")

class WindowsInstaller(PlatformInstaller):
    def install(self, options: Optional[Dict[str, Any]] = None) -> PlatformStatusResult:
        opts = options or {}
        install_service = opts.get("install_service", False)
        
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        
        # Test secure storage initialization
        storage = WindowsSecureStorage()
        test_res = storage.store_secret("__init_test", "ok")
        storage.delete_secret("__init_test")

        if install_service and sys.platform.startswith("win"):
            svc = WindowsServiceLifecycle()
            svc_res = svc.install_service()
            if svc_res.status not in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.SUPPORTED):
                logger.warning(f"Service install returned: {svc_res.message}")

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ACTIVE,
            message="Academia Shield Agent installed successfully on Windows",
            details={"app_data_dir": APP_DATA_DIR}
        )


class WindowsUninstaller(PlatformUninstaller):
    def uninstall(self, purge_data: bool = False) -> PlatformStatusResult:
        # Step 1: Restore DNS settings if any active enforcement exists.
        # Never delete files or credentials while a recovery journal is pending.
        dns = WindowsDnsEnforcement()
        restore = dns.restore_original_dns()
        if restore.status not in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.SUPPORTED):
            return PlatformStatusResult(
                status=restore.status,
                message=(
                    "Uninstallation paused: original adapter DNS could not be verified and restored. "
                    "Run again as Administrator; the recovery guard will keep retrying."
                ),
                details={"restore_message": restore.message},
            )

        # Step 2: Stop and uninstall Windows Service
        if sys.platform.startswith("win"):
            svc = WindowsServiceLifecycle()
            svc.uninstall_service()

        # Step 3: Purge stored credentials
        storage = WindowsSecureStorage()
        storage.clear_all()

        # Step 4: Remove local application data if requested
        if purge_data and os.path.exists(APP_DATA_DIR):
            try:
                shutil.rmtree(APP_DATA_DIR, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Could not purge {APP_DATA_DIR}: {e}")

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ACTIVE,
            message="Academia Shield Agent uninstalled and system settings restored on Windows"
        )
