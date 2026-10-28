"""
Comprehensive Unit Tests for Custom Schedule Evaluator & Session State Service.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.services.schedule_evaluator import ScheduleEvaluator, ScheduleEvaluationResult

def test_schedule_evaluator_valid_timezone_check():
    assert ScheduleEvaluator.is_valid_iana_timezone("UTC") is True
    assert ScheduleEvaluator.is_valid_iana_timezone("Asia/Kolkata") is True
    assert ScheduleEvaluator.is_valid_iana_timezone("America/New_York") is True
    assert ScheduleEvaluator.is_valid_iana_timezone("Europe/London") is True
    assert ScheduleEvaluator.is_valid_iana_timezone("Invalid/Fake_Zone") is False
    assert ScheduleEvaluator.is_valid_iana_timezone("") is False

def test_one_time_session_evaluation():
    base_time = datetime(2026, 8, 9, 10, 0, 0, tzinfo=timezone.utc)
    start_utc = base_time + timedelta(hours=1)
    end_utc = start_utc + timedelta(hours=2)

    # 1. Before start -> upcoming
    res_before = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        now_utc=base_time
    )
    assert res_before.state == "upcoming"
    assert res_before.next_occurrence is not None
    assert res_before.next_occurrence.start_utc == start_utc

    # 2. During active window -> active
    during_time = start_utc + timedelta(minutes=30)
    res_during = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        now_utc=during_time
    )
    assert res_during.state == "active"
    assert res_during.current_occurrence is not None
    assert res_during.current_occurrence.start_utc == start_utc

    # 3. After end -> expired
    after_time = end_utc + timedelta(minutes=10)
    res_after = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        now_utc=after_time
    )
    assert res_after.state == "expired"

def test_daily_recurrence_evaluation():
    start_utc = datetime(2026, 8, 9, 8, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(2026, 8, 9, 10, 0, 0, tzinfo=timezone.utc)

    # Day 1 active window
    day1_active = datetime(2026, 8, 9, 8, 30, 0, tzinfo=timezone.utc)
    res1 = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        recurrence_type="daily",
        recurrence_interval=1,
        now_utc=day1_active
    )
    assert res1.state == "active"
    assert res1.current_occurrence.start_utc == start_utc

    # Day 2 active window (occurred 24h later)
    day2_active = datetime(2026, 8, 10, 8, 30, 0, tzinfo=timezone.utc)
    res2 = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        recurrence_type="daily",
        recurrence_interval=1,
        now_utc=day2_active
    )
    assert res2.state == "active"
    assert res2.current_occurrence.start_utc == datetime(2026, 8, 10, 8, 0, 0, tzinfo=timezone.utc)

def test_weekly_recurrence_selected_weekdays():
    # Monday Aug 10, 2026
    start_utc = datetime(2026, 8, 10, 9, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(2026, 8, 10, 11, 0, 0, tzinfo=timezone.utc)

    # Active Monday
    mon_time = datetime(2026, 8, 10, 9, 30, 0, tzinfo=timezone.utc)
    res_mon = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        tz_name="UTC",
        recurrence_type="weekly",
        recurrence_interval=1,
        recurrence_days_of_week=["monday", "wednesday"],
        now_utc=mon_time
    )
    assert res_mon.state == "active"

    # Tuesday Aug 11 -> upcoming (next is Wednesday Aug 12)
    tue_time = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)
    res_tue = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        tz_name="UTC",
        recurrence_type="weekly",
        recurrence_interval=1,
        recurrence_days_of_week=["monday", "wednesday"],
        now_utc=tue_time
    )
    assert res_tue.state == "upcoming"
    assert res_tue.next_occurrence.start_utc == datetime(2026, 8, 12, 9, 0, 0, tzinfo=timezone.utc)

def test_cancelled_and_ended_status_evaluation():
    start_utc = datetime(2026, 8, 9, 8, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(2026, 8, 9, 10, 0, 0, tzinfo=timezone.utc)
    during_time = datetime(2026, 8, 9, 8, 30, 0, tzinfo=timezone.utc)

    # Cancelled session status
    res_canc = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        status="cancelled",
        now_utc=during_time
    )
    assert res_canc.state == "cancelled"

    # Ended session status
    res_ended = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        status="ended",
        now_utc=during_time
    )
    assert res_ended.state == "ended"

def test_excessive_clock_skew_returns_invalid_time():
    start_utc = datetime(2026, 8, 9, 8, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(2026, 8, 9, 10, 0, 0, tzinfo=timezone.utc)
    during_time = datetime(2026, 8, 9, 8, 30, 0, tzinfo=timezone.utc)

    res_skew = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        now_utc=during_time,
        clock_skew_seconds=180.0,  # Exceeds 120s
        max_allowed_skew_seconds=120.0
    )
    assert res_skew.state == "invalid_time"
    assert "Clock skew" in res_skew.reason

def test_dst_transition_handling():
    # US Eastern Time: Nov 1, 2026 DST transition
    # 09:00 AM EDT (13:00 UTC) -> 09:00 AM EST (14:00 UTC)
    start_utc = datetime(2026, 11, 1, 13, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(2026, 11, 1, 15, 0, 0, tzinfo=timezone.utc)

    res_dst = ScheduleEvaluator.evaluate(
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        tz_name="America/New_York",
        recurrence_type="none",
        now_utc=datetime(2026, 11, 1, 14, 0, 0, tzinfo=timezone.utc)
    )
    assert res_dst.state == "active"
