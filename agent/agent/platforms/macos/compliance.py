"""
macOS Managed Compliance Reporter.
Audits macOS Content Filter / Network Extension status, MDM enrollment,
and removable media restrictions.
Does NOT install unauthorized system extensions or bypass Apple security mechanisms.
"""

import sys
import subprocess
import logging
from typing import Dict, Any

from ..base import (
    PlatformBrowserCompliance,
    PlatformApplicationControlCompliance,
    PlatformUsbStorageCompliance,
    PlatformCapabilityStatus,
    PlatformStatusResult
)

logger = logging.getLogger(__name__)

class MacosBrowserCompliance(PlatformBrowserCompliance):
    """
    Checks for managed browser restrictions via macOS Configuration Profiles (MCX/MDM).
    """

    def check_compliance(self) -> PlatformStatusResult:
        if sys.platform != "darwin":
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="macOS browser compliance simulated on non-macOS host"
            )
        try:
            cmd = ["/usr/bin/profiles", "status", "-type", "enrollment"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if "MDM enrollment: Yes" in res.stdout:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ACTIVE,
                    message="macOS device enrolled in institutional MDM with managed payload support",
                    details={"mdm_enrolled": True}
                )
            else:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.REQUIRES_MDM,
                    message="Device is unmanaged/personal. Browser restrictions operate via local DNS filtering.",
                    details={"mdm_enrolled": False}
                )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message=f"Unable to query profiles status: {e}"
            )


class MacosApplicationControlCompliance(PlatformApplicationControlCompliance):
    """
    Audits Apple System Extension / Content Filter and Gatekeeper status.
    """

    def check_compliance(self) -> PlatformStatusResult:
        if sys.platform != "darwin":
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="macOS App Control compliance simulated on non-macOS host"
            )
        try:
            # Check systemextensionsctl
            cmd = ["/usr/bin/systemextensionsctl", "list"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            has_ext = "org.academiashield" in res.stdout
            if has_ext and "[activated enabled]" in res.stdout:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ACTIVE,
                    message="Academia Shield macOS System Extension (Content Filter) is activated and enabled",
                    details={"system_extension_active": True}
                )
            elif has_ext:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL,
                    message="Academia Shield System Extension installed but pending User Approval in System Settings -> Privacy & Security",
                    details={"system_extension_active": False}
                )
            else:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.REQUIRES_MDM,
                    message="macOS Network Extension requires Developer ID signing with Apple Entitlement & MDM profile deployment",
                    details={"system_extension_active": False}
                )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message=f"System Extension inspection error: {e}"
            )


class MacosUsbStorageCompliance(PlatformUsbStorageCompliance):
    """
    Checks macOS storage restriction profiles or disk arbitration status.
    """

    def check_compliance(self) -> PlatformStatusResult:
        if sys.platform != "darwin":
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="macOS USB compliance simulated on non-macOS host",
                details={"usb_storage_blocked": False}
            )
        try:
            # Check for MDM restriction payload com.apple.MCX
            cmd = ["/usr/bin/defaults", "read", "/Library/Preferences/com.apple.MCX", "forceRemovableUnmount"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and "1" in res.stdout:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ACTIVE,
                    message="macOS Removable Storage blocked via institutional MDM profile",
                    details={"usb_storage_blocked": True}
                )
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="macOS Removable Storage allowed (standard student profile)",
                details={"usb_storage_blocked": False}
            )
        except Exception:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="macOS Removable Storage standard profile",
                details={"usb_storage_blocked": False}
            )
