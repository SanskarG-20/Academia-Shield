"""
Custom Schedule Evaluator Domain Service.

Evaluates academic session schedules (one-time, daily, weekly) using Python's zoneinfo
for IANA timezone conversions and DST transition handling.
Returns current occurrence, next occurrence, active start/end window, and session state.
"""

import zoneinfo
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

@dataclass
class OccurrenceWindow:
    """Calculated start and end boundaries for an occurrence in UTC."""
    start_utc: datetime
    end_utc: datetime
    is_current_active: bool = False

@dataclass
class ScheduleEvaluationResult:
    """Deterministic evaluation outcome for a session schedule."""
    state: str  # upcoming, active, ended, cancelled, expired, invalid_time
    current_occurrence: Optional[OccurrenceWindow] = None
    next_occurrence: Optional[OccurrenceWindow] = None
    reason: Optional[str] = None

class ScheduleEvaluator:
    """Domain service for recurrence calculations and schedule evaluation."""

    @staticmethod
    def is_valid_iana_timezone(tz_name: str) -> bool:
        """Check if tz_name is a valid IANA timezone string."""
        if not tz_name:
            return False
        clean_name = tz_name.strip()
        if clean_name.upper() in ("UTC", "GMT", "ETC/UTC", "ETC/GMT"):
            return True
        try:
            zoneinfo.ZoneInfo(clean_name)
            return True
        except Exception:
            return False

    @staticmethod
    def calculate_occurrences(
        start_at_utc: datetime,
        end_at_utc: datetime,
        tz_name: str = "UTC",
        recurrence_type: str = "none",
        recurrence_interval: int = 1,
        recurrence_days_of_week: Optional[List[Any]] = None,
        recurrence_until_utc: Optional[datetime] = None,
        now_utc: Optional[datetime] = None,
        max_horizon_days: int = 90
    ) -> Tuple[Optional[OccurrenceWindow], Optional[OccurrenceWindow]]:
        """
        Calculate the current active occurrence window and the next upcoming occurrence window.
        Uses local IANA timezone for calendar day alignment and DST shifts.
        """
        now = now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        # Resolve local timezone safely
        if tz_name and tz_name.strip().upper() in ("UTC", "GMT", "ETC/UTC", "ETC/GMT"):
            local_tz = timezone.utc
        else:
            try:
                local_tz = zoneinfo.ZoneInfo(tz_name.strip())
            except Exception:
                local_tz = timezone.utc

        start_utc = start_at_utc.astimezone(timezone.utc) if start_at_utc.tzinfo else start_at_utc.replace(tzinfo=timezone.utc)
        end_utc = end_at_utc.astimezone(timezone.utc) if end_at_utc.tzinfo else end_at_utc.replace(tzinfo=timezone.utc)

        duration = end_utc - start_utc

        rec_type = (recurrence_type or "none").strip().lower()

        # 1. One-time schedule
        if rec_type == "none":
            is_active = (start_utc <= now <= end_utc)
            current_occ = OccurrenceWindow(start_utc=start_utc, end_utc=end_utc, is_current_active=is_active) if (start_utc <= now <= end_utc) else None
            next_occ = OccurrenceWindow(start_utc=start_utc, end_utc=end_utc, is_current_active=False) if (now < start_utc) else None
            return current_occ, next_occ

        # 2. Recurring schedules (daily / weekly)
        until_utc = None
        if recurrence_until_utc:
            until_utc = recurrence_until_utc.astimezone(timezone.utc) if recurrence_until_utc.tzinfo else recurrence_until_utc.replace(tzinfo=timezone.utc)

        current_occ = None
        next_occ = None

        interval = max(1, recurrence_interval or 1)

        # Parse target weekdays for weekly recurrence
        target_weekdays = set()
        if rec_type == "weekly" and recurrence_days_of_week:
            for day in recurrence_days_of_week:
                if isinstance(day, str):
                    d_lower = day.strip().lower()
                    if d_lower in DAY_NAMES:
                        target_weekdays.add(DAY_NAMES.index(d_lower))
                elif isinstance(day, int) and 0 <= day <= 6:
                    target_weekdays.add(day)

        if rec_type == "weekly" and not target_weekdays:
            start_local = start_utc.astimezone(local_tz)
            target_weekdays.add(start_local.weekday())

        curr_start = start_utc
        max_limit = now + timedelta(days=max_horizon_days)

        iteration = 0
        while curr_start <= max_limit:
            curr_end = curr_start + duration

            if until_utc and curr_start > until_utc:
                break

            curr_local = curr_start.astimezone(local_tz)

            is_valid_day = True
            if rec_type == "weekly":
                if curr_local.weekday() not in target_weekdays:
                    is_valid_day = False

            if is_valid_day:
                if curr_start <= now <= curr_end:
                    current_occ = OccurrenceWindow(start_utc=curr_start, end_utc=curr_end, is_current_active=True)
                elif now < curr_start and next_occ is None:
                    next_occ = OccurrenceWindow(start_utc=curr_start, end_utc=curr_end, is_current_active=False)

            if current_occ and next_occ:
                break

            # Advance to next candidate
            if rec_type == "daily":
                curr_start = curr_start + timedelta(days=interval)
            elif rec_type == "weekly":
                curr_start = curr_start + timedelta(days=1)

            iteration += 1
            if iteration > 1000:
                break

        return current_occ, next_occ

    @staticmethod
    def evaluate(
        start_at_utc: datetime,
        end_at_utc: datetime,
        status: str = "scheduled",
        tz_name: str = "UTC",
        recurrence_type: str = "none",
        recurrence_interval: int = 1,
        recurrence_days_of_week: Optional[List[Any]] = None,
        recurrence_until_utc: Optional[datetime] = None,
        now_utc: Optional[datetime] = None,
        clock_skew_seconds: float = 0.0,
        max_allowed_skew_seconds: float = 120.0
    ) -> ScheduleEvaluationResult:
        """
        Evaluate full session state.
        """
        if abs(clock_skew_seconds) > max_allowed_skew_seconds:
            return ScheduleEvaluationResult(
                state="invalid_time",
                reason=f"Clock skew ({abs(clock_skew_seconds):.1f}s) exceeds maximum allowed limit ({max_allowed_skew_seconds}s)"
            )

        norm_status = (status or "scheduled").strip().lower()
        if norm_status == "cancelled":
            return ScheduleEvaluationResult(state="cancelled", reason="Session explicitly cancelled by administrator")
        if norm_status == "ended":
            return ScheduleEvaluationResult(state="ended", reason="Session explicitly ended by administrator")

        current_occ, next_occ = ScheduleEvaluator.calculate_occurrences(
            start_at_utc=start_at_utc,
            end_at_utc=end_at_utc,
            tz_name=tz_name,
            recurrence_type=recurrence_type,
            recurrence_interval=recurrence_interval,
            recurrence_days_of_week=recurrence_days_of_week,
            recurrence_until_utc=recurrence_until_utc,
            now_utc=now_utc
        )

        if current_occ:
            return ScheduleEvaluationResult(
                state="active",
                current_occurrence=current_occ,
                next_occurrence=next_occ
            )

        if next_occ:
            return ScheduleEvaluationResult(
                state="upcoming",
                current_occurrence=None,
                next_occurrence=next_occ
            )

        return ScheduleEvaluationResult(
            state="expired",
            reason="All schedule occurrences have concluded"
        )
