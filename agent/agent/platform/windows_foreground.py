"""
Windows Foreground Window Detector.

Uses Win32 user32 APIs (GetForegroundWindow and GetWindowThreadProcessId) via ctypes
to identify the process PID currently owning the active foreground window.
"""

import sys
import ctypes
import logging
from typing import Optional

LOGGER = logging.getLogger(__name__)

class WindowsForegroundDetector:
    """Detects active foreground window PID on Windows systems."""

    def __init__(self):
        self.is_windows = sys.platform == "win32"

    def get_foreground_process_id(self) -> Optional[int]:
        """Return the PID owning the active foreground window on Windows."""
        if not self.is_windows:
            return None

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return int(pid.value) if pid.value else None
        except Exception as err:
            LOGGER.debug("GetForegroundWindow ctypes error: %s", err)
            return None

    def get_foreground_window_title(self) -> Optional[str]:
        """Return the window title of the current foreground window."""
        if not self.is_windows:
            return None

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return None

            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value.strip() or None
        except Exception as err:
            LOGGER.debug("GetWindowTextW ctypes error: %s", err)
            return None

    def close_foreground_window(self) -> bool:
        """Send WM_CLOSE signal to the current foreground window to dismiss prohibited non-browser apps."""
        if not self.is_windows:
            return False

        try:
            # Safeguard: Never close critical system tools or agent runtime
            pid = self.get_foreground_process_id()
            if pid:
                try:
                    import psutil
                    proc_name = psutil.Process(pid).name().lower()
                    protected_windows = {
                        "explorer.exe", "taskmgr.exe", "python.exe", "cmd.exe", "powershell.exe"
                    }
                    if proc_name in protected_windows:
                        LOGGER.warning("Refusing to close protected foreground window: %s (PID: %s)", proc_name, pid)
                        return False
                except Exception:
                    pass

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                return True
        except Exception as err:
            LOGGER.debug("Close window error: %s", err)
        return False

