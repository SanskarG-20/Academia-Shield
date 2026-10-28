"""
USB Storage Compliance & Removable Storage Enforcement Interface.

Manages Windows removable storage policies (pen drives, external disks) during active sessions:
- Checks Windows RemovableStorageDevices GPO policy & USBSTOR service restrictions
- Detects attached removable USB flash drives
- Provides honest compliance reporting (active, inactive, unsupported, requires_managed_device, error)
- Never claims USB is blocked or attempts custom blocking on personal/development devices
"""

import sys
import logging
from typing import Dict, Any, List

LOGGER = logging.getLogger(__name__)

# Standard Windows Registry GPO paths for removable storage restrictions
GPO_STORAGE_KEY = r"SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices"
GPO_REMOVABLE_DISKS_KEY = r"SOFTWARE\Policies\Microsoft\Windows\RemovableStorageDevices\{53f5630d-b6bf-11d0-94f2-00a0c91efb8b}"
GPO_DENY_ALL = "Deny_All"
USBSTOR_START_KEY = r"SYSTEM\CurrentControlSet\Services\USBSTOR"

class USBComplianceManager:
    """Device compliance and active USB storage status manager."""

    def __init__(self, mode: str = "AUDIT"):
        self.mode = mode
        self._is_blocked = False

    def get_usb_storage_restriction_status(self) -> str:
        """
        Return honest USB storage restriction compliance status:
        - active: real MDM/GPO policy confirmed enabled
        - inactive: supported system but policy disabled
        - requires_managed_device: personal/development device without MDM/GPO policy
        - unsupported: platform does not support managed policy inspection
        - error: exception during query
        """
        if sys.platform != "win32":
            return "unsupported"

        try:
            if self.is_usb_storage_restricted():
                return "active"
            # Personal / dev devices require MDM or GPO enrollment
            if self.mode in ("DEVELOPMENT_ENFORCEMENT", "AUDIT", "personal", "development"):
                return "requires_managed_device"
            return "inactive"
        except Exception as err:
            LOGGER.error("Error evaluating USB storage restriction status: %s", err)
            return "error"

    def is_usb_storage_restricted(self) -> bool:
        """
        Check if real Windows Removable Storage restrictions (GPO / USBSTOR) are active.
        """
        if sys.platform != "win32":
            return False

        try:
            import winreg
            # 1. Check GPO RemovableStorageDevices policy
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GPO_STORAGE_KEY, 0, winreg.KEY_READ) as key:
                    deny_all, _ = winreg.QueryValueEx(key, GPO_DENY_ALL)
                    if deny_all == 1:
                        return True
            except FileNotFoundError:
                pass
            except Exception as err:
                LOGGER.debug("Error querying GPO removable storage policy: %s", err)

            # 2. Check USBSTOR service disabled state (4 = Disabled via IT policy)
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, USBSTOR_START_KEY, 0, winreg.KEY_READ) as key:
                    start_val, _ = winreg.QueryValueEx(key, "Start")
                    if start_val == 4:
                        return True
            except FileNotFoundError:
                pass
            except Exception as err:
                LOGGER.debug("Error querying USBSTOR service state: %s", err)

        except Exception as err:
            LOGGER.warning("Could not evaluate USB compliance: %s", err)

        return False

    def apply_usb_storage_block(self) -> bool:
        """
        Apply managed-device USB storage restriction only on institutional managed devices.
        Never builds custom drivers or blocks USB on personal devices.
        """
        if self.mode in ("DEVELOPMENT_ENFORCEMENT", "AUDIT", "personal", "development"):
            LOGGER.info("USB storage restriction requires a college-managed MDM/GPO policy; skipping automatic modification on personal/dev device.")
            return False

        if sys.platform != "win32":
            return False

        try:
            import winreg

            # 1. Set GPO RemovableStorageDevices Deny_All = 1
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, GPO_STORAGE_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, GPO_DENY_ALL, 0, winreg.REG_DWORD, 1)

            # 2. Set Removable Disks Deny_Write = 1 and Deny_Read = 1
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, GPO_REMOVABLE_DISKS_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "Deny_Write", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "Deny_Read", 0, winreg.REG_DWORD, 1)

            # 3. Disable USBSTOR service for newly inserted drives (Start = 4)
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, USBSTOR_START_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "Start", 0, winreg.REG_DWORD, 4)
            except Exception as e:
                LOGGER.debug("Note on USBSTOR update: %s", e)

            self._is_blocked = True
            LOGGER.info("Managed USB storage policy applied successfully.")
            return True

        except PermissionError:
            LOGGER.warning("Admin privileges required to apply managed USB storage policy.")
            return False
        except Exception as err:
            LOGGER.error("Failed to apply managed USB storage policy: %s", err)
            return False

    def restore_usb_storage_access(self) -> bool:
        """
        Restore normal USB storage access when session ends or agent terminates.
        """
        if sys.platform != "win32":
            self._is_blocked = False
            return True

        try:
            import winreg

            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GPO_STORAGE_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, GPO_DENY_ALL, 0, winreg.REG_DWORD, 0)
            except FileNotFoundError:
                pass

            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GPO_REMOVABLE_DISKS_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "Deny_Write", 0, winreg.REG_DWORD, 0)
                    winreg.SetValueEx(key, "Deny_Read", 0, winreg.REG_DWORD, 0)
            except FileNotFoundError:
                pass

            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, USBSTOR_START_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "Start", 0, winreg.REG_DWORD, 3)
            except Exception as e:
                LOGGER.debug("Note on USBSTOR restore: %s", e)

            self._is_blocked = False
            LOGGER.info("USB Storage access restored to normal.")
            return True

        except PermissionError:
            LOGGER.warning("Admin privileges required to restore USB storage settings.")
            return False
        except Exception as err:
            LOGGER.error("Failed to restore USB storage access: %s", err)
            return False

    def detect_removable_drives(self) -> List[str]:
        """
        Detect currently mounted removable disk drives (e.g. ['E:', 'F:']).
        """
        removable_drives = []
        if sys.platform != "win32":
            return removable_drives

        try:
            import ctypes
            import string

            # DRIVE_REMOVABLE = 2 in Windows API
            DRIVE_REMOVABLE = 2
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for letter in string.ascii_uppercase:
                if bitmask & 1:
                    drive_path = f"{letter}:\\"
                    drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_path)
                    if drive_type == DRIVE_REMOVABLE:
                        removable_drives.append(f"{letter}:")
                bitmask >>= 1
        except Exception as err:
            LOGGER.debug("Error scanning removable drives: %s", err)

        return removable_drives

    def get_compliance_status(self) -> Dict[str, Any]:
        """Return compliance payload for heartbeat/status reporting."""
        status_val = self.get_usb_storage_restriction_status()
        restricted = (status_val == "active")
        detected_drives = self.detect_removable_drives()
        note = (
            "USB restriction active via MDM/GPO" if restricted else
            "USB storage restriction requires a college-managed MDM/GPO policy."
        )
        return {
            "usb_storage_restricted": restricted,
            "usb_storage_restriction_status": status_val,
            "mode": self.mode,
            "compliance_note": note,
            "active_removable_drives": detected_drives
        }

def get_usb_storage_restriction_status(mode: str = "AUDIT") -> tuple:
    """Convenience helper to retrieve USB storage restriction compliance status and note."""
    manager = USBComplianceManager(mode=mode)
    status = manager.get_usb_storage_restriction_status()
    note = manager.get_compliance_status().get("compliance_note", "")
    return status, note
