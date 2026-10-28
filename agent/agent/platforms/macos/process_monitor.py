"""
macOS Process Monitor Adapter.
Operates strictly in AUDIT/WARN mode.
Guarantees NO force-closing of macOS system, accessibility, or security applications.
"""

import sys
import logging
from typing import List, Dict, Any, Set, Optional

from ..base import PlatformProcessMonitor, PlatformCapabilityStatus, PlatformStatusResult

logger = logging.getLogger(__name__)

# Essential macOS System and Accessibility Processes that MUST NEVER be touched
MACOS_PROTECTED_PROCESSES: Set[str] = {
    "launchd", "kernel_task", "windowserver", "finder", "dock", "systemuiserver",
    "controlcenter", "notificationcenter", "spotlight", "loginwindow", "tccd",
    "securityd", "endpointsecurityd", "cfprefsd", "trustd", "syspolicyd",
    "voiceover", "universalaccessd", "assistivetouchd", "zoom", # macOS Accessibility
    "safari", "google chrome", "arc", "terminal", "iterm2", "code"
}

class MacosProcessMonitor(PlatformProcessMonitor):
    """
    macOS Process Monitor.
    Runs in AUDIT/WARN mode only. On macOS, arbitrary force-closing of processes
    without MDM/EndpointSecurity entitlements is unsafe and restricted.
    """

    def __init__(self, protected_processes: Optional[Set[str]] = None):
        self.protected_processes = set(p.lower() for p in (protected_processes or MACOS_PROTECTED_PROCESSES))

    def get_status(self) -> PlatformStatusResult:
        try:
            import psutil
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="macOS audit process monitor active (Audit/Warn mode)",
                details={"mode": "audit_warn_only", "protected_count": len(self.protected_processes)}
            )
        except ImportError:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="psutil library missing on macOS"
            )

    def get_running_processes(self) -> List[Dict[str, Any]]:
        processes = []
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'create_time', 'username']):
                try:
                    info = proc.info
                    name = (info.get('name') or '').lower()
                    processes.append({
                        "pid": info.get('pid'),
                        "name": name,
                        "exe": info.get('exe') or '',
                        "create_time": info.get('create_time'),
                        "username": info.get('username') or '',
                        "is_protected": name in self.protected_processes
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except Exception as e:
            logger.error(f"Error enumerating macOS processes: {e}")
        return processes

    def handle_process_action(self, pid: int, process_name: str, action: str) -> PlatformStatusResult:
        proc_name_clean = process_name.lower().strip()

        # Guard: Protected macOS system/accessibility process
        if proc_name_clean in self.protected_processes:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"macOS process '{proc_name_clean}' is protected. Audit log recorded.",
                details={"action_taken": "logged", "protected": True}
            )

        if action in ("log", "warn"):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"macOS process '{proc_name_clean}' ({action}) recorded in compliance audit log.",
                details={"action_taken": action, "pid": pid}
            )

        if action == "close":
            # On macOS, force termination of applications without MDM is not allowed on personal devices
            logger.info(f"macOS agent does not force-kill processes; logging warning for '{proc_name_clean}'")
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.REQUIRES_MDM,
                message=f"Direct process termination for '{proc_name_clean}' requires MDM or Apple Endpoint Security entitlement. Downgraded to audit warning.",
                details={"action_taken": "warned", "pid": pid}
            )

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.UNAVAILABLE,
            message=f"Action '{action}' unavailable on macOS"
        )
