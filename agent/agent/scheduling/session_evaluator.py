"""
Client-Side Agent Session Evaluator.

Evaluates policy session schedules against corrected server time.
Outputs deterministic state: upcoming, active, ended, cancelled, expired, invalid_time.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from .server_clock import ServerClock
from ..policy.policy_manager import VerifiedPolicy

LOGGER = logging.getLogger(__name__)

class AgentSessionEvaluator:
    """Evaluates policy schedules on the Local Agent using corrected server time."""

    def __init__(self, server_clock: Optional[ServerClock] = None):
        self.server_clock = server_clock or ServerClock()

    def evaluate_policy_session(
        self,
        policy: Optional[VerifiedPolicy],
        local_now_utc: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluate policy schedule and return dictionary:
        {
          "state": "active" | "upcoming" | "ended" | "cancelled" | "expired" | "invalid_time",
          "session_id": "...",
          "corrected_now": datetime,
          "reason": "..."
        }
        """
        if not policy:
            return {
                "state": "expired",
                "session_id": None,
                "reason": "No policy supplied"
            }

        # Check server clock validity
        if not self.server_clock.is_time_valid():
            if self.server_clock.is_clock_skew_excessive():
                reason = f"Clock skew exceeds allowed limit ({abs(self.server_clock.get_server_offset_seconds()):.1f}s > {self.server_clock.max_allowed_skew_seconds}s)"
            elif self.server_clock.is_sync_stale():
                reason = "Server time sync is stale"
            else:
                reason = "Server time unverified"

            return {
                "state": "invalid_time",
                "session_id": policy.schedule_windows[0].session_id if policy.schedule_windows else None,
                "reason": reason
            }

        corrected_now = self.server_clock.get_corrected_utc_time(local_now_utc)

        # Check overall policy expiration
        if policy.is_expired(corrected_now):
            return {
                "state": "expired",
                "session_id": policy.schedule_windows[0].session_id if policy.schedule_windows else None,
                "corrected_now": corrected_now,
                "reason": "Policy overall expiration date exceeded"
            }

        if not policy.schedule_windows:
            return {
                "state": "expired",
                "session_id": None,
                "corrected_now": corrected_now,
                "reason": "No schedule windows defined"
            }

        # Check active session window
        active_window = None
        upcoming_window = None

        for window in policy.schedule_windows:
            # Trust backend status field first — professor controls start/stop via dashboard.
            # If backend says "Active", enforce it immediately regardless of timestamps.
            if window.status and window.status.strip().lower() == "active":
                active_window = window
                break

            start_dt = window.start_time if window.start_time.tzinfo else window.start_time.replace(tzinfo=timezone.utc)
            end_dt = window.end_time if window.end_time.tzinfo else window.end_time.replace(tzinfo=timezone.utc)

            if start_dt <= corrected_now <= end_dt:
                active_window = window
                break
            elif corrected_now < start_dt:
                if upcoming_window is None or start_dt < (upcoming_window.start_time if upcoming_window.start_time.tzinfo else upcoming_window.start_time.replace(tzinfo=timezone.utc)):
                    upcoming_window = window

        if active_window:
            return {
                "state": "active",
                "session_id": active_window.session_id,
                "corrected_now": corrected_now,
                "start_time": active_window.start_time,
                "end_time": active_window.end_time,
                "title": active_window.title,
                "reason": f"Active session (status={active_window.status})"
            }

        if upcoming_window:
            return {
                "state": "upcoming",
                "session_id": upcoming_window.session_id,
                "corrected_now": corrected_now,
                "start_time": upcoming_window.start_time,
                "end_time": upcoming_window.end_time,
                "title": upcoming_window.title,
                "reason": "Upcoming session window"
            }

        return {
            "state": "ended",
            "session_id": policy.schedule_windows[0].session_id,
            "corrected_now": corrected_now,
            "reason": "All schedule windows have concluded"
        }

