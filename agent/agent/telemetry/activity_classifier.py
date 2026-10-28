"""
ActivityClassifier Service for Academia Shield Local Agent.

Samples the active foreground window and user input activity every 5 seconds to produce
exactly one mutually exclusive classification:
  - 'allowed_academic_active': User is actively interacting with an allowed application or allowed website.
  - 'idle': No user input (mouse/keyboard) detected for at least IDLE_THRESHOLD_SECONDS (default 60s),
            even if an allowed app (e.g. VS Code) or allowed website is open and in the foreground.
  - 'non_academic_active': User is actively interacting with an unapproved application or website.
  - 'unknown_or_unavailable': Browser is in foreground but domain cannot be safely determined.
                              Never assumes an open browser is an allowed website.

Privacy & Safety Guarantee:
Never collects screenshots, keystrokes, typed text, full URLs, page contents,
document contents, passwords, browser history, or search terms.
"""

import sys
import time
import ctypes
import logging
from datetime import datetime, timezone
from typing import Optional, Set, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("agent.activity_classifier")

# Standard academic developer tools & editors
ACADEMIC_PROCESS_ALLOWLIST: Set[str] = {
    "code.exe", "code", "pycharm64.exe", "pycharm.exe", "pycharm",
    "idea64.exe", "idea.exe", "idea", "clion64.exe", "clion.exe", "clion",
    "webstorm64.exe", "webstorm.exe", "webstorm", "devenv.exe", "eclipse.exe",
    "sublime_text.exe", "sublime_text", "notepad++.exe", "notepad.exe",
    "windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe",
    "git-bash.exe", "bash", "zsh", "python.exe", "python3.exe", "python",
    "java.exe", "java", "node.exe", "node", "cargo.exe", "cargo",
    "winword.exe", "excel.exe", "powerpnt.exe", "acrobat.exe", "acroreader.exe",
    "pdfxedit.exe", "foxitreader.exe", "texmaker.exe", "texstudio.exe", "jupyter.exe"
}

# Known web browser executables
BROWSER_PROCESSES: Set[str] = {
    "chrome.exe", "chrome", "google-chrome",
    "msedge.exe", "msedge",
    "firefox.exe", "firefox",
    "brave.exe", "brave",
    "opera.exe", "opera",
    "safari"
}


def get_os_idle_seconds() -> float:
    """
    Detect user input inactivity duration (seconds) via OS native APIs.
    - Windows: GetLastInputInfo
    - macOS: CGEventSourceSecondsSinceLastEventType or IOHIDSystem
    """
    if sys.platform == "win32":
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                return max(0.0, millis / 1000.0)
        except Exception as err:
            logger.debug("Failed reading Windows user idle time: %s", err)

    elif sys.platform == "darwin":
        try:
            import ctypes.util
            core_graphics_path = ctypes.util.find_library("CoreGraphics")
            if core_graphics_path:
                cg = ctypes.cdll.LoadLibrary(core_graphics_path)
                # CGEventSourceSecondsSinceLastEventType(kCGEventSourceStateCombinedSessionState=1, kCGAnyInputEventType=~0)
                cg.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
                cg.CGEventSourceSecondsSinceLastEventType.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
                idle_sec = cg.CGEventSourceSecondsSinceLastEventType(1, 0xFFFFFFFF)
                return max(0.0, float(idle_sec))
        except Exception as err:
            logger.debug("Failed reading macOS CoreGraphics idle time: %s", err)

    return 0.0


@dataclass
class ActivityClassificationResult:
    """Represents the single classification result of a 5-second sample."""
    session_id: str
    device_id: str
    timestamp: datetime
    classification: str  # 'allowed_academic_active', 'idle', 'non_academic_active', 'unknown_or_unavailable'
    foreground_executable: Optional[str] = None
    matched_rule_id: Optional[str] = None
    domain: Optional[str] = None
    idle_duration: float = 0.0
    resource_subtype: Optional[str] = None  # 'application', 'website', or None
    is_violation: bool = False
    violation_type: Optional[str] = None  # 'blocked_website', 'unauthorized_application', or None


class ActivityClassifier:
    """
    Classifies student foreground interaction every 5 seconds.
    Enforces the rule that an allowed app or website open on screen without user interaction
    is classified strictly as 'idle'.
    """

    def __init__(
        self,
        idle_threshold_seconds: float = 60.0,
        idle_detector_fn=None,
        foreground_detector=None
    ):
        self.idle_threshold_seconds = idle_threshold_seconds
        self._idle_detector_fn = idle_detector_fn or get_os_idle_seconds
        self.foreground_detector = foreground_detector

    def set_idle_threshold(self, threshold_seconds: float):
        """Update idle threshold from policy dynamically."""
        if threshold_seconds and threshold_seconds > 0:
            self.idle_threshold_seconds = float(threshold_seconds)

    def classify(
        self,
        session_id: str,
        device_id: str,
        allowed_applications: Optional[Set[str]] = None,
        allowed_websites: Optional[Set[str]] = None,
        blocked_applications: Optional[Set[str]] = None,
        blocked_websites: Optional[Set[str]] = None,
        app_rule_id_map: Optional[Dict[str, str]] = None,
        web_rule_id_map: Optional[Dict[str, str]] = None,
    ) -> ActivityClassificationResult:
        """
        Produce exactly one mutual classification for the current 5-second sample:
        1. Query OS idle time. If idle_seconds >= idle_threshold_seconds:
           -> 'idle' (even if an allowed app like VS Code is open in the foreground).
        2. If user is active (not idle):
           - Check foreground application / window.
           - If browser: safely verify domain.
             - In allowed_websites -> 'allowed_academic_active' (website)
             - In blocked_websites -> 'non_academic_active' + violation
             - Cannot be safely determined -> 'unknown_or_unavailable'
           - If non-browser application:
             - In allowed_applications -> 'allowed_academic_active' (application)
             - In blocked_applications -> 'non_academic_active' + violation
             - Other unapproved application -> 'non_academic_active'
        """
        now_utc = datetime.now(timezone.utc)
        clean_allowed_apps = {a.lower().strip() for a in (allowed_applications or set()) if a}
        clean_allowed_sites = {w.lower().strip() for w in (allowed_websites or set()) if w}
        clean_blocked_apps = {a.lower().strip() for a in (blocked_applications or set()) if a}
        clean_blocked_sites = {w.lower().strip() for w in (blocked_websites or set()) if w}
        app_rule_ids = app_rule_id_map or {}
        web_rule_ids = web_rule_id_map or {}

        # 1. Query OS Input Inactivity
        idle_sec = self._idle_detector_fn()

        # 2. Query Foreground Process & Window
        fg_app = None
        fg_title = None
        if self.foreground_detector:
            try:
                pid = self.foreground_detector.get_foreground_process_id()
                if pid:
                    import psutil
                    proc = psutil.Process(pid)
                    fg_app = proc.name().lower().strip()
                fg_title = self.foreground_detector.get_foreground_window_title() or ""
            except Exception as e:
                logger.debug("Error querying foreground window: %s", e)

        # 3. RULE: User Inactivity Precedence
        # If user is sitting idle (e.g. no keyboard/mouse for >= idle_threshold_seconds),
        # this sample is classified as IDLE, even if VS Code or an allowed site is open!
        if idle_sec >= self.idle_threshold_seconds:
            return ActivityClassificationResult(
                session_id=session_id,
                device_id=device_id,
                timestamp=now_utc,
                classification="idle",
                foreground_executable=fg_app,
                idle_duration=idle_sec,
                resource_subtype=None,
                is_violation=False
            )

        # 4. User is Active (typing, clicking, or moving mouse within idle threshold)
        if not fg_app:
            return ActivityClassificationResult(
                session_id=session_id,
                device_id=device_id,
                timestamp=now_utc,
                classification="unknown_or_unavailable",
                foreground_executable=None,
                idle_duration=idle_sec,
                resource_subtype=None,
                is_violation=False
            )

        is_browser = (fg_app in BROWSER_PROCESSES)

        if is_browser:
            matched_allowed_site = None
            matched_blocked_site = None
            title_lower = (fg_title or "").lower().strip()

            if title_lower:
                for site in clean_allowed_sites:
                    base_site = site[4:] if site.startswith("www.") else site
                    if site in title_lower or base_site in title_lower:
                        matched_allowed_site = site
                        break

                if not matched_allowed_site:
                    for b in clean_blocked_sites:
                        base_b = b[4:] if b.startswith("www.") else b
                        if b in title_lower or base_b in title_lower:
                            matched_blocked_site = b
                            break

            if matched_allowed_site:
                return ActivityClassificationResult(
                    session_id=session_id,
                    device_id=device_id,
                    timestamp=now_utc,
                    classification="allowed_academic_active",
                    foreground_executable=fg_app,
                    matched_rule_id=web_rule_ids.get(matched_allowed_site),
                    domain=matched_allowed_site,
                    idle_duration=idle_sec,
                    resource_subtype="website",
                    is_violation=False
                )
            elif matched_blocked_site:
                return ActivityClassificationResult(
                    session_id=session_id,
                    device_id=device_id,
                    timestamp=now_utc,
                    classification="non_academic_active",
                    foreground_executable=fg_app,
                    domain=matched_blocked_site,
                    idle_duration=idle_sec,
                    resource_subtype="website",
                    is_violation=True,
                    violation_type="blocked_website"
                )
            elif title_lower and any(tld in title_lower for tld in [".com", ".org", ".net", ".edu", ".io", ".ai", ".gov"]):
                # Verifiably non-academic browsing
                return ActivityClassificationResult(
                    session_id=session_id,
                    device_id=device_id,
                    timestamp=now_utc,
                    classification="non_academic_active",
                    foreground_executable=fg_app,
                    idle_duration=idle_sec,
                    resource_subtype="website",
                    is_violation=False
                )
            else:
                # Browser is foreground but domain cannot be safely extracted (e.g. New Tab, blank title)
                # Never assume an open browser is an allowed website!
                return ActivityClassificationResult(
                    session_id=session_id,
                    device_id=device_id,
                    timestamp=now_utc,
                    classification="unknown_or_unavailable",
                    foreground_executable=fg_app,
                    idle_duration=idle_sec,
                    resource_subtype="website",
                    is_violation=False
                )
        else:
            # Non-browser application
            is_app_allowed = (
                fg_app in clean_allowed_apps or
                fg_app in ACADEMIC_PROCESS_ALLOWLIST
            )
            if is_app_allowed:
                return ActivityClassificationResult(
                    session_id=session_id,
                    device_id=device_id,
                    timestamp=now_utc,
                    classification="allowed_academic_active",
                    foreground_executable=fg_app,
                    matched_rule_id=app_rule_ids.get(fg_app),
                    idle_duration=idle_sec,
                    resource_subtype="application",
                    is_violation=False
                )
            elif fg_app in clean_blocked_apps:
                return ActivityClassificationResult(
                    session_id=session_id,
                    device_id=device_id,
                    timestamp=now_utc,
                    classification="non_academic_active",
                    foreground_executable=fg_app,
                    idle_duration=idle_sec,
                    resource_subtype="application",
                    is_violation=True,
                    violation_type="unauthorized_application"
                )
            else:
                return ActivityClassificationResult(
                    session_id=session_id,
                    device_id=device_id,
                    timestamp=now_utc,
                    classification="non_academic_active",
                    foreground_executable=fg_app,
                    idle_duration=idle_sec,
                    resource_subtype="application",
                    is_violation=False
                )
