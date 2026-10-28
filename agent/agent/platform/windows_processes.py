"""
Windows Process Operations & Termination Platform Adapter.

Executes process management operations on Windows using native Win32/taskkill calls
with standard grace periods and fallback force termination.
"""

import sys
import subprocess
import logging
from typing import Optional

LOGGER = logging.getLogger(__name__)

class WindowsProcessAdapter:
    """Windows-specific process management helper."""

    @staticmethod
    def terminate_process(pid: int, process_name: str, force: bool = False) -> bool:
        """Terminate process by PID using taskkill."""
        if sys.platform != "win32":
            return False

        try:
            cmd = ["taskkill"]
            if force:
                cmd.append("/F")
            cmd.extend(["/PID", str(pid)])

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
            if res.returncode == 0:
                LOGGER.info("Successfully terminated Windows process %s (PID: %s)", process_name, pid)
                return True
            else:
                LOGGER.debug("Taskkill returned code %s for PID %s: %s", res.returncode, pid, res.stderr)
                return False
        except Exception as err:
            LOGGER.error("Failed executing taskkill on PID %s: %s", pid, err)
            return False
