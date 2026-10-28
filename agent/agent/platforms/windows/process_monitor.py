"""
Windows Process Monitor Adapter.
Performs psutil-based application monitoring with safe actions: log, warn, close.
Guarantees system, accessibility, and security processes are never terminated.
"""

import sys
import os
import logging
from typing import List, Dict, Any, Set, Optional

from ..base import PlatformProcessMonitor, PlatformCapabilityStatus, PlatformStatusResult

logger = logging.getLogger(__name__)

# Protected Windows and Accessibility Processes that MUST NEVER be killed
PROTECTED_PROCESSES: Set[str] = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe", "winlogon.exe",
    "dwm.exe", "explorer.exe", "sihost.exe", "taskhostw.exe", "ctfmon.exe",
    "magnify.exe", "narrator.exe", "osk.exe", "atbroker.exe", # Windows Accessibility
    "nvvsvc.exe", "audiodg.exe", "spoolsv.exe", "securityhealthservice.exe", "msmpeng.exe",
    "acad_agent.exe", "academiashield.exe"
}

class WindowsProcessMonitor(PlatformProcessMonitor):
    """
    Monitors running processes on Windows and executes safe policy actions.
    Actions supported:
    - 'log': Record violation in audit log / telemetry.
    - 'warn': Post warning telemetry and notification without terminating.
    - 'close': Graceful request to close (terminate) non-protected processes.
    """

    def __init__(self, protected_processes: Optional[Set[str]] = None):
        self.protected_processes = set(p.lower() for p in (protected_processes or PROTECTED_PROCESSES))

    def get_status(self) -> PlatformStatusResult:
        try:
            import psutil
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message="psutil process monitor active on Windows",
                details={"protected_count": len(self.protected_processes)}
            )
        except ImportError:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="psutil library missing"
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
            logger.error(f"Error enumerating Windows processes: {e}")
        return processes

    def handle_process_action(self, pid: int, process_name: str, action: str) -> PlatformStatusResult:
        proc_name_clean = process_name.lower().strip()
        
        # Security Guard: Never terminate protected system/accessibility/security processes
        if proc_name_clean in self.protected_processes:
            logger.info(f"Process '{proc_name_clean}' (PID: {pid}) is protected. Action '{action}' downgraded to 'log'.")
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"Process '{proc_name_clean}' is protected by safety whitelist. Logged only.",
                details={"action_taken": "logged", "protected": True}
            )

        if action == "log":
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"Process '{proc_name_clean}' violation logged.",
                details={"action_taken": "logged"}
            )

        if action == "warn":
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"Warning issued for process '{proc_name_clean}'.",
                details={"action_taken": "warned"}
            )

        if action == "close":
            try:
                import psutil
                if not psutil.pid_exists(pid):
                    return PlatformStatusResult(
                        status=PlatformCapabilityStatus.ACTIVE,
                        message=f"Process PID {pid} already exited.",
                        details={"action_taken": "noop"}
                    )
                proc = psutil.Process(pid)
                # First try graceful termination
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except psutil.TimeoutExpired:
                    proc.kill()

                logger.info(f"Safely closed unauthorized process '{proc_name_clean}' (PID {pid})")
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ACTIVE,
                    message=f"Successfully closed unauthorized process '{proc_name_clean}'",
                    details={"action_taken": "closed", "pid": pid}
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL,
                    message=f"Access denied or process gone closing '{proc_name_clean}': {e}",
                    details={"action_taken": "failed", "pid": pid}
                )
            except Exception as e:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ERROR,
                    message=f"Unexpected error closing '{proc_name_clean}': {e}"
                )

        return PlatformStatusResult(
            status=PlatformCapabilityStatus.UNAVAILABLE,
            message=f"Unknown process action '{action}'"
        )
