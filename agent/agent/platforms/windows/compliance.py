"""
Windows Managed Compliance Reporter.
Audits device compliance for Windows App Control (WDAC), Microsoft Edge managed policies,
and removable USB storage policies.
Does NOT install custom kernel drivers or bypass enterprise MDM/GPO.
"""

import sys
import os
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

class WindowsBrowserCompliance(PlatformBrowserCompliance):
    r"""
    Checks if Microsoft Edge / Chrome has managed enterprise or kiosk policies configured
    via Windows Registry (HKLM\Software\Policies\Microsoft\Edge).
    """

    def check_compliance(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="Browser compliance check simulated on non-Windows host",
                details={"managed_browser": "simulated", "url_blocklist_active": True}
            )
        try:
            import winreg
            edge_key_path = r"SOFTWARE\Policies\Microsoft\Edge"
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, edge_key_path) as key:
                    num_values = winreg.QueryInfoKey(key)[1]
                    return PlatformStatusResult(
                        status=PlatformCapabilityStatus.ACTIVE,
                        message="Microsoft Edge enterprise policy is managed by Institution GPO/MDM",
                        details={"policy_values_count": num_values}
                    )
            except FileNotFoundError:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.REQUIRES_MDM,
                    message="No Enterprise Edge policy found in Registry. Standard student browser profile active.",
                    details={"managed": False}
                )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=f"Failed to query Edge registry policies: {e}"
            )


class WindowsApplicationControlCompliance(PlatformApplicationControlCompliance):
    """
    Checks Windows App Control (WDAC) / AppLocker enforcement status via WMI / PowerShell.
    """

    def check_compliance(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="Application control compliance check simulated on non-Windows host"
            )
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance -Namespace root/Microsoft/Windows/CI -ClassName MSFT_CIPolicyStatus -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Status"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                status_val = res.stdout.strip()
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ACTIVE,
                    message=f"Windows App Control (WDAC) is active (status: {status_val})",
                    details={"wdac_status": status_val}
                )
            else:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.REQUIRES_MDM,
                    message="WDAC / AppLocker is not enforced by institutional policy. Using agent process monitor.",
                    details={"wdac_enforced": False}
                )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message=f"Unable to query WDAC status: {e}"
            )


class WindowsUsbStorageCompliance(PlatformUsbStorageCompliance):
    r"""
    Checks USB Storage restriction policy in Registry:
    HKLM\SYSTEM\CurrentControlSet\Services\USBSTOR (Start = 4 means disabled)
    or RemovableStorageDevices policy.
    """

    def check_compliance(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message="USB Storage compliance simulated on non-Windows host",
                details={"usb_storage_blocked": False}
            )
        try:
            import winreg
            key_path = r"SYSTEM\CurrentControlSet\Services\USBSTOR"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                start_val, _ = winreg.QueryValueEx(key, "Start")
                if start_val == 4:
                    return PlatformStatusResult(
                        status=PlatformCapabilityStatus.ACTIVE,
                        message="USB Removable Storage is blocked by institution policy (USBSTOR Start=4)",
                        details={"usb_storage_blocked": True, "start_value": 4}
                    )
                else:
                    return PlatformStatusResult(
                        status=PlatformCapabilityStatus.SUPPORTED,
                        message="USB Removable Storage is enabled on this system",
                        details={"usb_storage_blocked": False, "start_value": start_val}
                    )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.SUPPORTED,
                message=f"Standard USB storage config (audit error: {e})",
                details={"usb_storage_blocked": False}
            )
