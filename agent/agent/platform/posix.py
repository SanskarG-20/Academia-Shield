"""
POSIX (macOS / Linux) Platform Adapter.
"""

import os
import signal
import platform
import subprocess
import logging
from typing import Dict
from .base import BasePlatformAdapter

LOGGER = logging.getLogger(__name__)

class PosixPlatformAdapter(BasePlatformAdapter):
    """POSIX implementation for macOS and Linux."""

    def is_admin(self) -> bool:
        try:
            return os.geteuid() == 0
        except Exception:
            return False

    def show_notification(self, title: str, message: str) -> None:
        LOGGER.info("[NOTIFICATION] %s - %s", title, message)
        try:
            if platform.system() == "Darwin":
                script = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", script], capture_output=True, timeout=2)
            else:
                subprocess.run(["notify-send", title, message], capture_output=True, timeout=2)
        except Exception:
            pass

    def terminate_process_gracefully(self, pid: int, process_name: str) -> bool:
        try:
            # Send SIGTERM first for graceful exit
            os.kill(pid, signal.SIGTERM)
            LOGGER.info("Sent SIGTERM to process %s (PID: %s)", process_name, pid)
            return True
        except Exception as err:
            LOGGER.error("Failed sending SIGTERM to %s (PID: %s): %s", process_name, pid, err)
            return False

    def get_os_info(self) -> Dict[str, str]:
        return {
            "os_name": platform.system(),
            "os_version": f"{platform.system()} {platform.release()}"
        }
