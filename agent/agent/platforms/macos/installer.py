"""
macOS Platform Installer & Uninstaller.
Manages .app registration, launchd service, secure Keychain initialization,
and clean uninstallation that restores network settings.
"""

import sys
import os
import shutil
import logging
from typing import Optional, Dict, Any

from ..base import PlatformInstaller, PlatformUninstaller, PlatformCapabilityStatus, PlatformStatusResult
from .storage import MacosSecureStorage
from .service import MacosServiceLifecycle
from .dns import MacosDnsEnforcement

logger = logging.getLogger(__name__)

MACOS_APP_DATA_DIR = os.path.expanduser("~/Library/Application Support/AcademiaShield")

class MacosInstaller(PlatformInstaller):
    def install(self, options: Optional[Dict[str, Any]] = None) -> PlatformStatusResult:
        opts = options or {}
        os.makedirs(MACOS_APP_DATA_DIR, exist_ok=True)

        # Initialize Keychain store
        storage = MacosSecureStorage()
        storage.store_secret("__init_test", "ok")
        storage.delete_secret("__init_test")

        if opts.get("install_launchd", False) and sys.platform == "darwin":
            svc = MacosServiceLifecycle()
            svc.install_service()

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ACTIVE,
            message="Academia Shield Agent installed on macOS",
            details={"app_data_dir": MACOS_APP_DATA_DIR}
        )


class MacosUninstaller(PlatformUninstaller):
    def uninstall(self, purge_data: bool = False) -> PlatformStatusResult:
        # Step 1: Revert any DNS changes
        dns = MacosDnsEnforcement()
        dns.restore_original_dns()

        # Step 2: Unload and remove launchd agent
        if sys.platform == "darwin":
            svc = MacosServiceLifecycle()
            svc.uninstall_service()

        # Step 3: Clear Keychain secrets
        storage = MacosSecureStorage()
        storage.clear_all()

        # Step 4: Remove application support files
        if purge_data and os.path.exists(MACOS_APP_DATA_DIR):
            try:
                shutil.rmtree(MACOS_APP_DATA_DIR, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Could not purge {MACOS_APP_DATA_DIR}: {e}")

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ACTIVE,
            message="Academia Shield Agent uninstalled and system settings restored on macOS"
        )
