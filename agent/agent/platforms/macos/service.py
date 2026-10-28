"""
macOS Service Lifecycle Adapter (launchd).
Manages user LaunchAgent (~/Library/LaunchAgents) or system LaunchDaemon (/Library/LaunchDaemons).
"""

import sys
import os
import subprocess
import logging
from typing import Dict, Any, Optional

from ..base import PlatformServiceLifecycle, PlatformCapabilityStatus, PlatformStatusResult

logger = logging.getLogger(__name__)

PLIST_LABEL = "org.academiashield.agent"
LAUNCH_AGENT_DIR = os.path.expanduser("~/Library/LaunchAgents")
PLIST_PATH = os.path.join(LAUNCH_AGENT_DIR, f"{PLIST_LABEL}.plist")

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>org.academiashield.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>{executable}</string>
        <string>-m</string>
        <string>agent.main</string>
        <string>--daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/agent.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/agent.stderr.log</string>
</dict>
</plist>
"""

class MacosServiceLifecycle(PlatformServiceLifecycle):
    """
    Manages macOS launchd agent lifecycle.
    """

    def __init__(self, plist_path: str = PLIST_PATH):
        self.plist_path = plist_path

    def get_status(self) -> PlatformStatusResult:
        if sys.platform != "darwin":
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="launchd service manager unavailable on non-macOS host"
            )
        try:
            cmd = ["launchctl", "list"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if PLIST_LABEL in res.stdout:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ACTIVE,
                    message=f"macOS launchd agent '{PLIST_LABEL}' is loaded and running",
                    details={"loaded": True}
                )
            elif os.path.exists(self.plist_path):
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.SUPPORTED,
                    message=f"macOS launchd agent '{PLIST_LABEL}' is installed but not loaded",
                    details={"loaded": False, "plist_exists": True}
                )
            else:
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.UNAVAILABLE,
                    message=f"macOS launchd agent '{PLIST_LABEL}' is not installed",
                    details={"installed": False}
                )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=f"Error querying launchd status: {e}"
            )

    def install_service(self, run_as_system: bool = False) -> PlatformStatusResult:
        if sys.platform != "darwin":
            return PlatformStatusResult(status=PlatformCapabilityStatus.UNAVAILABLE, message="Not on macOS")
        try:
            os.makedirs(LAUNCH_AGENT_DIR, exist_ok=True)
            log_dir = os.path.expanduser("~/Library/Logs/AcademiaShield")
            os.makedirs(log_dir, exist_ok=True)

            plist_content = PLIST_TEMPLATE.format(
                executable=sys.executable,
                log_dir=log_dir
            )
            with open(self.plist_path, "w", encoding="utf-8") as f:
                f.write(plist_content)

            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"launchd plist created at {self.plist_path}"
            )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ERROR,
                message=f"Failed to create launchd plist: {e}"
            )

    def start_service(self) -> PlatformStatusResult:
        if sys.platform != "darwin":
            return PlatformStatusResult(status=PlatformCapabilityStatus.UNAVAILABLE, message="Not on macOS")
        try:
            if not os.path.exists(self.plist_path):
                self.install_service()
            cmd = ["launchctl", "load", "-w", self.plist_path]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return PlatformStatusResult(status=PlatformCapabilityStatus.ACTIVE, message=f"launchd agent '{PLIST_LABEL}' started")
            return PlatformStatusResult(status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL, message=f"launchctl load returned: {res.stderr}")
        except Exception as e:
            return PlatformStatusResult(status=PlatformCapabilityStatus.ERROR, message=str(e))

    def stop_service(self) -> PlatformStatusResult:
        if sys.platform != "darwin":
            return PlatformStatusResult(status=PlatformCapabilityStatus.UNAVAILABLE, message="Not on macOS")
        try:
            if os.path.exists(self.plist_path):
                subprocess.run(["launchctl", "unload", self.plist_path], capture_output=True, timeout=5)
            return PlatformStatusResult(status=PlatformCapabilityStatus.ACTIVE, message=f"launchd agent '{PLIST_LABEL}' stopped")
        except Exception as e:
            return PlatformStatusResult(status=PlatformCapabilityStatus.ERROR, message=str(e))

    def uninstall_service(self) -> PlatformStatusResult:
        if sys.platform != "darwin":
            return PlatformStatusResult(status=PlatformCapabilityStatus.UNAVAILABLE, message="Not on macOS")
        try:
            self.stop_service()
            if os.path.exists(self.plist_path):
                os.remove(self.plist_path)
            return PlatformStatusResult(status=PlatformCapabilityStatus.ACTIVE, message=f"launchd agent '{PLIST_LABEL}' uninstalled")
        except Exception as e:
            return PlatformStatusResult(status=PlatformCapabilityStatus.ERROR, message=str(e))
