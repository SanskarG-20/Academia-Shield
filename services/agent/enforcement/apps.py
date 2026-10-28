"""Request a normal close for matching user applications; never kill processes."""

import logging
import ntpath
import os
import platform
import time

LOGGER = logging.getLogger("academia_shield_agent")
_LAST_CLOSE_REQUEST = {}
_CLOSE_COOLDOWN_SECONDS = 60

# OS, security, desktop, installer and shell processes are never targets.
PROTECTED = {
    "system", "registry", "csrss.exe", "smss.exe", "wininit.exe",
    "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
    "dwm.exe", "explorer.exe", "taskmgr.exe", "cmd.exe",
    "powershell.exe", "pwsh.exe", "conhost.exe", "regedit.exe",
    "mmc.exe", "msiexec.exe", "securityhealthservice.exe",
    "msmpeng.exe", "academiashield.exe", "python.exe", "pythonw.exe",
}


def _request_windows_close(pid):
    """Post WM_CLOSE to unowned visible top-level windows of one process."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    requested = 0

    def visit(hwnd, _):
        nonlocal requested
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value == pid and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):
            if user32.PostMessageW(hwnd, 0x0010, 0, 0):  # WM_CLOSE, GW_OWNER = 4
                requested += 1
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return requested > 0


def enforce_blocked_apps(blocked_apps, process_iter=None, current_username=None,
                         windows_dir=None, request_close=None):
    """Ask only this user's GUI apps to close; unsaved-work prompts may remain."""
    if platform.system() != "Windows" and request_close is None:
        return []
    names = {str(name).strip().casefold() for name in blocked_apps
             if str(name).strip().casefold().endswith(".exe")}
    names -= PROTECTED
    if not names:
        return []

    if process_iter is None or current_username is None:
        import psutil
        if process_iter is None:
            process_iter = lambda: psutil.process_iter(["pid", "name", "username", "exe"])
        if current_username is None:
            try:
                current_username = psutil.Process(os.getpid()).username()
            except Exception:
                LOGGER.warning("Cannot identify agent account; skipping application close requests")
                return []

    if request_close is None:
        request_close = _request_windows_close
    windows_root = ntpath.normcase(ntpath.normpath(windows_dir or os.environ.get("SystemRoot", r"C:\Windows")))
    now = time.monotonic()
    for pid, requested_at in list(_LAST_CLOSE_REQUEST.items()):
        if now - requested_at >= _CLOSE_COOLDOWN_SECONDS:
            del _LAST_CLOSE_REQUEST[pid]
    requested = []
    for process in process_iter():
        try:
            info = process.info
            name = str(info.get("name") or "").casefold()
            pid = info.get("pid")
            owner = str(info.get("username") or "").casefold()
            executable = str(info.get("exe") or "")
            normalized = ntpath.normcase(ntpath.normpath(executable))
            if (name not in names or not isinstance(pid, int) or pid <= 4 or pid == os.getpid()
                    or owner != current_username.casefold() or not ntpath.isabs(executable)
                    or normalized.startswith(windows_root + "\\")):
                continue
            if time.monotonic() - _LAST_CLOSE_REQUEST.get(pid, float("-inf")) < _CLOSE_COOLDOWN_SECONDS:
                continue
            if request_close(pid):
                _LAST_CLOSE_REQUEST[pid] = time.monotonic()
                requested.append(name)
        except Exception as error:
            LOGGER.debug("Could not request application close: %s", error)
    return requested
