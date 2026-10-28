import os
import sys
import time
import ctypes
import platform
import subprocess
import logging
from typing import Dict
from .base import BasePlatformAdapter

LOGGER = logging.getLogger(__name__)

class WindowsPlatformAdapter(BasePlatformAdapter):
    """Windows-specific implementation for process management and user notifications."""

    def __init__(self):
        self._last_notifications: Dict[str, float] = {}
        self._last_notification_time: float = 0.0

    def is_admin(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def show_notification(self, title: str, message: str) -> None:
        """Show visible Windows notification with debounce and deduplication."""
        now = time.time()
        key = f"{title}_{message}"

        # Suppress identical messages within 60 seconds
        if key in self._last_notifications and (now - self._last_notifications[key] < 60.0):
            LOGGER.debug("Suppressing duplicate toast notification: %s", key)
            return

        # Throttle any toast notification to at most once per 6 seconds
        if now - self._last_notification_time < 6.0:
            LOGGER.debug("Throttling toast notification: %s", key)
            return

        self._last_notifications[key] = now
        self._last_notification_time = now

        LOGGER.info("[NOTIFICATION] %s - %s", title, message)
        try:
            safe_title = title.replace('"', '`"')
            safe_message = message.replace('"', '`"')
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode("{safe_title}")) > $null
            $textNodes.Item(1).AppendChild($template.CreateTextNode("{safe_message}")) > $null
            $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Academia Shield").Show($toast)
            """
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

    def terminate_process_gracefully(self, pid: int, process_name: str) -> bool:
        """Close explicitly blocked process using psutil and taskkill."""
        # 1. Try direct psutil termination first (instant, native)
        try:
            import psutil
            try:
                p = psutil.Process(pid)
                p.kill()
                LOGGER.info("Terminated application %s (PID: %s)", process_name, pid)
                return True
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                return True
            except psutil.AccessDenied:
                pass
        except Exception:
            pass

        # 2. Force terminate process tree with taskkill /F /T /PID
        try:
            res = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                LOGGER.info("Terminated application process %s (PID: %s)", process_name, pid)
                return True

            # 3. Fallback: taskkill by executable image name
            if process_name and process_name.strip():
                clean_exe = process_name.strip()
                if not clean_exe.endswith(".exe"):
                    clean_exe = f"{clean_exe}.exe"
                res_im = subprocess.run(["taskkill", "/F", "/IM", clean_exe], capture_output=True, text=True, timeout=3)
                return res_im.returncode == 0
            return False
        except Exception as err:
            LOGGER.error("Failed terminating process %s (PID: %s): %s", process_name, pid, err)
            return False

    def get_os_info(self) -> Dict[str, str]:
        return {
            "os_name": "Windows",
            "os_version": f"{platform.system()} {platform.release()} ({platform.version()})"
        }
