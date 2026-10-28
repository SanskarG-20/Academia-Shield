"""
Windows Service Lifecycle Adapter.
Manages the Academia Shield Windows Service using sc.exe / win32serviceutil.
Ensures transparent user consent or administrative deployment.
"""

import sys
import os
import subprocess
import logging
from typing import Dict, Any, Optional

from ..base import PlatformServiceLifecycle, PlatformCapabilityStatus, PlatformStatusResult

logger = logging.getLogger(__name__)

SERVICE_NAME = "AcademiaShieldService"
DISPLAY_NAME = "Academia Shield Local Agent Service"

class WindowsServiceLifecycle(PlatformServiceLifecycle):
    """
    Manages Windows service installation, start, stop, and status.
    """

    def __init__(self, service_name: str = SERVICE_NAME):
        self.service_name = service_name

    def get_status(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="Windows Service manager unavailable on non-Windows host"
            )
        try:
            res = subprocess.run(["sc.exe", "query", self.service_name], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                if "RUNNING" in res.stdout:
                    return PlatformStatusResult(
                        status=PlatformCapabilityStatus.ACTIVE,
                        message=f"Service '{self.service_name}' is running",
                        details={"state": "RUNNING"}
                    )
                elif "STOPPED" in res.stdout:
                    return PlatformStatusResult(
                        status=PlatformCapabilityStatus.SUPPORTED,
                        message=f"Service '{self.service_name}' is stopped",
                        details={"state": "STOPPED"}
                    )
                else:
                    return PlatformStatusResult(
                        status=PlatformCapabilityStatus.SUPPORTED,
                        message=f"Service '{self.service_name}' is installed",
                        details={"output": res.stdout.strip()}
                    )
            else:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.UNAVAILABLE,
                    message=f"Service '{self.service_name}' is not installed",
                    details={"installed": False}
                )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=f"Failed to query Windows service status: {e}"
            )

    def install_service(self, run_as_system: bool = False) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="Windows Service installation only supported on Windows"
            )
        try:
            exe_path = sys.executable
            # If frozen or running as script
            bin_path = f'"{exe_path}" -m agent.main --service'
            cmd = [
                "sc.exe", "create", self.service_name,
                f"binPath= {bin_path}",
                f"DisplayName= {DISPLAY_NAME}",
                "start= auto"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ACTIVE,
                    message=f"Service '{self.service_name}' successfully installed"
                )
            elif "Access is denied" in res.stderr or "5" in res.stderr:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL,
                    message="Administrator privileges required to register Windows service"
                )
            else:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ERROR,
                    message=f"Failed to install service: {res.stderr or res.stdout}"
                )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=f"Exception installing Windows service: {e}"
            )

    def start_service(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            return PlatformStatusResult(status=PlatformCapabilityStatus.UNAVAILABLE, message="Not on Windows")
        try:
            res = subprocess.run(["sc.exe", "start", self.service_name], capture_output=True, text=True, timeout=10)
            if res.returncode == 0 or "already running" in res.stderr.lower():
                return PlatformStatusResult(status=PlatformCapabilityStatus.ACTIVE, message=f"Service '{self.service_name}' started")
            else:
                return PlatformStatusResult(status=PlatformCapabilityStatus.ERROR, message=f"Failed to start service: {res.stderr}")
        except Exception as e:
            return PlatformStatusResult(status=PlatformCapabilityStatus.ERROR, message=str(e))

    def stop_service(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            return PlatformStatusResult(status=PlatformCapabilityStatus.UNAVAILABLE, message="Not on Windows")
        try:
            res = subprocess.run(["sc.exe", "stop", self.service_name], capture_output=True, text=True, timeout=10)
            return PlatformStatusResult(status=PlatformCapabilityStatus.ACTIVE, message=f"Service '{self.service_name}' stop requested")
        except Exception as e:
            return PlatformStatusResult(status=PlatformCapabilityStatus.ERROR, message=str(e))

    def uninstall_service(self) -> PlatformStatusResult:
        if not sys.platform.startswith("win"):
            return PlatformStatusResult(status=PlatformCapabilityStatus.UNAVAILABLE, message="Not on Windows")
        try:
            self.stop_service()
            res = subprocess.run(["sc.exe", "delete", self.service_name], capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return PlatformStatusResult(status=PlatformCapabilityStatus.ACTIVE, message=f"Service '{self.service_name}' uninstalled")
            return PlatformStatusResult(status=PlatformCapabilityStatus.SUPPORTED, message=f"Service delete status: {res.stdout}")
        except Exception as e:
            return PlatformStatusResult(status=PlatformCapabilityStatus.ERROR, message=str(e))
