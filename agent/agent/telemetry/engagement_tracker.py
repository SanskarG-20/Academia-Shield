"""
Privacy-Minimized Real-Time Student Engagement Telemetry Tracker for Academia Shield Local Agent.
Tracks 8 aggregated signals over 5-minute rolling windows:
- academic_active_seconds
- non_academic_active_seconds
- idle_seconds
- application_switch_count
- unauthorized_application_attempt_count
- blocked_website_attempt_count
- policy_violation_count
- session_elapsed_seconds

Never collects screenshots, keystrokes, browser content, file contents, memory dumps, or passwords.
"""

import sys
import time
import uuid
import ctypes
import logging
from datetime import datetime, timezone
from typing import Optional, Set

try:
    import psutil
except ImportError:
    psutil = None

from ..platform.windows_foreground import WindowsForegroundDetector
from .activity_classifier import ActivityClassificationResult, ActivityClassifier, get_os_idle_seconds

logger = logging.getLogger("agent.engagement_tracker")

# Standard academic tools and developer environments
ACADEMIC_PROCESS_ALLOWLIST: Set[str] = {
    "code.exe", "pycharm64.exe", "idea64.exe", "clion64.exe", "webstorm64.exe",
    "devenv.exe", "eclipse.exe", "sublime_text.exe", "notepad++.exe", "notepad.exe",
    "cmd.exe", "powershell.exe", "windowsterminal.exe", "bash.exe", "git-bash.exe",
    "python.exe", "pythonw.exe", "java.exe", "javaw.exe", "node.exe", "cargo.exe",
    "winword.exe", "excel.exe", "powerpnt.exe", "acrobat.exe", "acroreader.exe",
    "pdfxedit.exe", "foxitreader.exe", "texmaker.exe", "texstudio.exe", "jupyter.exe"
}

# Browsers are considered academic during sessions when allowed
BROWSER_PROCESSES: Set[str] = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"
}


def _get_system_idle_seconds() -> float:
    """Detect system-wide user inactivity in seconds on Windows."""
    if sys.platform != "win32":
        return 0.0

    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    except Exception as err:
        logger.debug("Failed to read user idle time: %s", err)

_get_system_idle_seconds = get_os_idle_seconds


class EngagementTracker:
    def __init__(self, api_client=None, idle_threshold_seconds: float = 60.0, window_duration_seconds: Optional[float] = None):
        import os
        if window_duration_seconds is None:
            try:
                window_duration_seconds = float(os.environ.get("ENGAGEMENT_WINDOW_SECONDS", 300.0))
            except (ValueError, TypeError):
                window_duration_seconds = 300.0

        self.api_client = api_client
        self.idle_threshold_seconds = idle_threshold_seconds
        self.window_duration_seconds = window_duration_seconds

        self.fg_detector = WindowsForegroundDetector()
        self.classifier = ActivityClassifier(
            idle_threshold_seconds=self.idle_threshold_seconds,
            idle_detector_fn=lambda: _get_system_idle_seconds(),
            foreground_detector=self.fg_detector
        )

        # Session context
        self.is_active = False
        self.session_id: Optional[str] = None
        self.batch_id: Optional[str] = None
        self.student_id: Optional[str] = None
        self.device_id: Optional[str] = None
        self.policy_version: int = 1
        self.session_start_time: Optional[datetime] = None

        # Window state
        self.window_start_at: Optional[datetime] = None
        self.last_tick_time: float = 0.0
        self.last_foreground_app: Optional[str] = None

        # Metrics for current window
        self.allowed_academic_application_active_seconds: float = 0.0
        self.allowed_academic_website_active_seconds: float = 0.0
        self.academic_active_seconds: float = 0.0
        self.non_academic_active_seconds: float = 0.0
        self.idle_seconds: float = 0.0
        self.unknown_or_unavailable_seconds: float = 0.0

        self.active_resource_sample_count: int = 0
        self.unknown_resource_sample_count: int = 0

        self.application_switch_count: int = 0
        self.unauthorized_application_attempt_count: int = 0
        self.blocked_website_attempt_count: int = 0
        self.policy_violation_count: int = 0

        self.approved_apps_breakdown: dict = {}
        self.approved_websites_breakdown: dict = {}
        self.academic_breakdown: dict = {}

    def start_session(
        self,
        session_id: str,
        batch_id: str,
        student_id: str,
        device_id: str,
        policy_version: int = 1
    ):
        """Initialize engagement tracking for an active session."""
        now_dt = datetime.now(timezone.utc)
        self.is_active = True
        self.session_id = session_id
        self.batch_id = batch_id
        self.student_id = student_id
        self.device_id = device_id
        self.policy_version = policy_version
        self.session_start_time = now_dt
        self.window_start_at = now_dt
        self.last_tick_time = time.time()
        self.last_foreground_app = None

        self._reset_window_metrics()
        logger.info(f"Engagement tracking started for session {session_id} (batch: {batch_id})")

    def _reset_window_metrics(self):
        self.allowed_academic_application_active_seconds = 0.0
        self.allowed_academic_website_active_seconds = 0.0
        self.academic_active_seconds = 0.0
        self.non_academic_active_seconds = 0.0
        self.idle_seconds = 0.0
        self.unknown_or_unavailable_seconds = 0.0
        self.active_resource_sample_count = 0
        self.unknown_resource_sample_count = 0
        self.application_switch_count = 0
        self.unauthorized_application_attempt_count = 0
        self.blocked_website_attempt_count = 0
        self.policy_violation_count = 0
        self.approved_apps_breakdown = {}
        self.approved_websites_breakdown = {}
        self.academic_breakdown = {}

    def record_violation(self, violation_type: str):
        """Record an unauthorized attempt or blocked website occurrence."""
        if not self.is_active:
            return

        self.policy_violation_count += 1
        vtype = violation_type.lower()
        if "app" in vtype or "process" in vtype:
            self.unauthorized_application_attempt_count += 1
        elif "web" in vtype or "dns" in vtype or "url" in vtype:
            self.blocked_website_attempt_count += 1
    def set_idle_threshold(self, threshold_seconds: float):
        """Update idle threshold dynamically from policy."""
        if threshold_seconds and threshold_seconds > 0:
            self.idle_threshold_seconds = float(threshold_seconds)
            self.classifier.set_idle_threshold(self.idle_threshold_seconds)

    def tick(
        self,
        allowed_applications: Optional[Set[str]] = None,
        allowed_websites: Optional[Set[str]] = None,
        blocked_applications: Optional[Set[str]] = None,
        blocked_websites: Optional[Set[str]] = None,
        policy_version: Optional[int] = None,
        dt: Optional[float] = None,
    ) -> Optional[ActivityClassificationResult]:
        """
        Sample system state every interval (e.g. 5 seconds) and classify into exactly one state:
        - allowed_academic_active (actively interacting with allowed app or allowed website)
        - idle (inactivity >= idle_threshold_seconds, even if allowed app or site is open in foreground)
        - non_academic_active
        - unknown_or_unavailable

        Uses proportional idle splitting: if OS reports the user has been idle for longer
        than the tick interval (dt), the ENTIRE tick is counted as idle — even if the
        foreground app is an allowed academic tool.  This prevents inflating academic_active
        time when the student just has VS Code or Chrome open but isn't doing anything.

        Zero sensitive data captured: no full URLs, page contents, keystrokes, screenshots, or files.
        """
        if not self.is_active or not self.session_id:
            return None

        if policy_version is not None:
            self.policy_version = policy_version

        now_mono = time.time()
        if dt is None:
            if self.last_tick_time and self.last_tick_time > 0:
                dt = max(0.0, min(now_mono - self.last_tick_time, 10.0))
            else:
                dt = 5.0
        if dt <= 0.0:
            dt = 5.0
        self.last_tick_time = now_mono

        # Perform mutual classification via ActivityClassifier
        res = self.classifier.classify(
            session_id=self.session_id,
            device_id=self.device_id or "",
            allowed_applications=allowed_applications,
            allowed_websites=allowed_websites,
            blocked_applications=blocked_applications,
            blocked_websites=blocked_websites,
        )

        # Track application switches
        if res.foreground_executable and self.last_foreground_app and res.foreground_executable != self.last_foreground_app:
            self.application_switch_count += 1
        if res.foreground_executable:
            self.last_foreground_app = res.foreground_executable

        # ── Proportional idle splitting ──────────────────────────────────
        # The classifier uses a hard idle threshold (default 60s) before
        # it labels the sample as "idle".  But if the OS reports that the
        # user has been idle for, say, 45 seconds (below the hard threshold),
        # the sample is labelled "allowed_academic_active" — even though the
        # student clearly isn't interacting with anything.
        #
        # Fix: Use a *soft* idle threshold.  If the OS idle duration exceeds
        # the tick interval (dt), the student has NOT interacted at all during
        # this entire tick — count it as idle regardless of what the classifier
        # says.  This ensures that even short idle periods (e.g. 10 seconds of
        # no mouse/keyboard) are properly recorded as idle time.
        #
        # Soft threshold = max(dt, 30% of hard threshold) — any OS-reported
        # idle duration above this is counted as fully idle for this tick.
        soft_idle_threshold = max(dt, self.idle_threshold_seconds * 0.30)
        os_idle_duration = res.idle_duration if res.idle_duration else 0.0
        is_soft_idle = os_idle_duration >= soft_idle_threshold

        # Accumulate metrics based on mutual classification + soft idle override
        if res.classification == "idle" or is_soft_idle:
            # Student is idle: no mouse/keyboard input for >= soft threshold
            # Even if an allowed app (e.g. VS Code) is open, this counts as IDLE, NOT academic!
            self.idle_seconds += dt
        elif res.classification == "allowed_academic_active":
            # True non-idle foreground interaction with approved resources
            if res.resource_subtype == "application":
                self.allowed_academic_application_active_seconds += dt
                self.active_resource_sample_count += 1
                if res.foreground_executable:
                    self.approved_apps_breakdown[res.foreground_executable] = (
                        self.approved_apps_breakdown.get(res.foreground_executable, 0.0) + dt
                    )
            else:
                self.allowed_academic_website_active_seconds += dt
                self.active_resource_sample_count += 1
                if res.domain:
                    self.approved_websites_breakdown[res.domain] = (
                        self.approved_websites_breakdown.get(res.domain, 0.0) + dt
                    )
        elif res.classification == "non_academic_active":
            self.non_academic_active_seconds += dt
            if res.is_violation:
                self.policy_violation_count += 1
                if res.violation_type == "blocked_website":
                    self.blocked_website_attempt_count += 1
                elif res.violation_type == "unauthorized_application":
                    self.unauthorized_application_attempt_count += 1
        elif res.classification == "unknown_or_unavailable":
            self.unknown_or_unavailable_seconds += dt
            self.unknown_resource_sample_count += 1

        # Update aggregated academic active seconds
        self.academic_active_seconds = (
            self.allowed_academic_application_active_seconds +
            self.allowed_academic_website_active_seconds
        )
        self.academic_breakdown = {**self.approved_apps_breakdown, **self.approved_websites_breakdown}

        # Check if 5-minute rolling window threshold has arrived
        now_dt = datetime.now(timezone.utc)
        if self.window_start_at:
            window_elapsed = (now_dt - self.window_start_at).total_seconds()
            if window_elapsed >= self.window_duration_seconds:
                self.flush_window()

        return res

    def flush_window(self, force: bool = False) -> Optional[dict]:
        """Package current feature window and post to backend."""
        if not self.is_active or not self.session_id or not self.window_start_at:
            return None

        now_dt = datetime.now(timezone.utc)
        window_duration = (now_dt - self.window_start_at).total_seconds()

        # Only flush if meaningful time elapsed or forced (e.g. session end)
        if window_duration < 1.0 and not force:
            return None

        # Calculate session elapsed time
        session_elapsed = (now_dt - self.session_start_time).total_seconds() if self.session_start_time else window_duration

        total_classified_seconds = (
            self.allowed_academic_application_active_seconds +
            self.allowed_academic_website_active_seconds +
            self.non_academic_active_seconds +
            self.idle_seconds +
            self.unknown_or_unavailable_seconds
        )

        completeness_pct = round(
            max(0.0, min(100.0, (1.0 - (self.unknown_or_unavailable_seconds / max(total_classified_seconds, 1.0))) * 100.0)),
            1
        )

        payload = {
            "event_id": str(uuid.uuid4()),
            "student_id": self.student_id,
            "device_id": self.device_id,
            "batch_id": self.batch_id,
            "session_id": self.session_id,
            "policy_version": self.policy_version,
            "window_started_at": self.window_start_at.isoformat(),
            "window_ended_at": now_dt.isoformat(),
            "window_start_at": self.window_start_at.isoformat(),
            "window_end_at": now_dt.isoformat(),
            "allowed_academic_application_active_seconds": round(self.allowed_academic_application_active_seconds, 1),
            "allowed_academic_website_active_seconds": round(self.allowed_academic_website_active_seconds, 1),
            "allowed_academic_active_seconds": round(self.academic_active_seconds, 1),
            "academic_active_seconds": round(self.academic_active_seconds, 1),
            "non_academic_active_seconds": round(self.non_academic_active_seconds, 1),
            "idle_seconds": round(self.idle_seconds, 1),
            "unknown_or_unavailable_seconds": round(self.unknown_or_unavailable_seconds, 1),
            "active_resource_sample_count": self.active_resource_sample_count,
            "unknown_resource_sample_count": self.unknown_resource_sample_count,
            "application_switch_count": self.application_switch_count,
            "unauthorized_application_attempt_count": self.unauthorized_application_attempt_count,
            "blocked_website_attempt_count": self.blocked_website_attempt_count,
            "policy_violation_count": self.policy_violation_count,
            "session_elapsed_seconds": round(session_elapsed, 1),
            "feature_completeness_percent": completeness_pct,
            "completeness_percent": completeness_pct,
            "academic_breakdown": {k: round(v, 1) for k, v in self.academic_breakdown.items()},
            "approved_apps_breakdown": {k: round(v, 1) for k, v in self.approved_apps_breakdown.items()},
            "approved_websites_breakdown": {k: round(v, 1) for k, v in self.approved_websites_breakdown.items()}
        }

        logger.info(
            f"Flushing engagement feature window: app_academic={payload['allowed_academic_application_active_seconds']}s, "
            f"web_academic={payload['allowed_academic_website_active_seconds']}s, non_academic={payload['non_academic_active_seconds']}s, "
            f"idle={payload['idle_seconds']}s, unknown={payload['unknown_or_unavailable_seconds']}s, completeness={completeness_pct}%"
        )

        # Reset counters for the next window
        self.window_start_at = now_dt
        self._reset_window_metrics()

        if self.api_client:
            try:
                res = self.api_client.post("/api/v1/agent/telemetry/engagement-windows", json=payload)
                logger.debug("Engagement window submission response: %s", res)
            except Exception as e:
                logger.warning(f"Failed to submit engagement window: {e}")

        return payload

    def end_session(self):
        """Immediately flush final telemetry window and reset tracking state."""
        if not self.is_active:
            return

        logger.info(f"Ending engagement tracking for session {self.session_id}. Flushing final window...")
        self.flush_window(force=True)

        self.is_active = False
        self.session_id = None
        self.batch_id = None
        self.session_start_time = None
        self.window_start_at = None
        self._reset_window_metrics()
