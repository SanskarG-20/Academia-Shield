"""Windows foreground window activity tracker."""

import time
import ctypes
import ctypes.wintypes
import logging
import threading

from activity.base import BaseActivityTracker

LOGGER = logging.getLogger("academia_shield")


class WindowsActivityTracker(BaseActivityTracker):
    """Tracks foreground window changes on Windows using Win32 API polling.

    Uses a lightweight 1-second polling loop to detect window focus changes.
    This is more reliable than SetWinEventHook for PyInstaller-bundled executables
    and doesn't require pywin32.
    """

    def __init__(self, poll_interval=1.0, **kwargs):
        super().__init__(**kwargs)
        self._poll_interval = poll_interval
        self._thread = None
        self._last_hwnd = None
        self._last_title = None
        self._last_process = None

    def _get_foreground_info(self):
        """Return (process_name, window_title) of the current foreground window."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return "Desktop", "Desktop"

            # Get window title
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
            else:
                title = "Desktop"

            # Get process name from window handle
            pid = ctypes.wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            process_name = "Unknown"
            if pid.value:
                # Open process with PROCESS_QUERY_LIMITED_INFORMATION (0x1000)
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
                if handle:
                    try:
                        buf = ctypes.create_unicode_buffer(260)
                        size = ctypes.wintypes.DWORD(260)
                        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                            handle, 0, buf, ctypes.byref(size)
                        ):
                            # Extract just the filename from the full path
                            full_path = buf.value
                            process_name = full_path.rsplit("\\", 1)[-1] if "\\" in full_path else full_path
                    finally:
                        ctypes.windll.kernel32.CloseHandle(handle)

            return process_name, title

        except Exception as e:
            LOGGER.debug("Error getting foreground info: %s", e)
            return "Unknown", "Unknown"

    def _poll_loop(self):
        """Background polling loop — checks foreground window every second."""
        LOGGER.info("Windows activity tracker started (poll interval: %.1fs)", self._poll_interval)

        while self._running:
            try:
                process_name, title = self._get_foreground_info()

                # Detect change: different window handle content
                if process_name != self._last_process or title != self._last_title:
                    self._last_process = process_name
                    self._last_title = title
                    self._on_window_change(process_name, title)

            except Exception as e:
                LOGGER.debug("Activity poll error: %s", e)

            # Sleep in small increments for responsive shutdown
            for _ in range(int(self._poll_interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def start(self):
        if self._running:
            return
        self._last_process = None
        self._last_title = None
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="activity-tracker")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        LOGGER.info("Windows activity tracker stopped.")
