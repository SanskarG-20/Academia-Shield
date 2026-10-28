"""
Unit Tests for Server Clock Adapter.
"""

import time
import pytest
from datetime import datetime, timezone, timedelta
from agent.scheduling.server_clock import ServerClock

def test_server_clock_offset_calculation():
    clock = ServerClock(max_allowed_skew_seconds=120.0, stale_threshold_seconds=300.0)

    now_local = datetime.now(timezone.utc)
    server_time = now_local + timedelta(seconds=15)

    offset = clock.update_from_server_time(server_time.isoformat())

    assert abs(offset - 15.0) < 2.0
    assert clock.is_time_valid() is True
    assert clock.is_clock_skew_excessive() is False

def test_server_clock_excessive_skew():
    clock = ServerClock(max_allowed_skew_seconds=120.0)

    now_local = datetime.now(timezone.utc)
    server_time = now_local + timedelta(seconds=200)  # Exceeds 120s limit

    clock.update_from_server_time(server_time.isoformat())

    assert clock.is_clock_skew_excessive() is True
    assert clock.is_time_valid() is False

def test_server_clock_stale_sync():
    clock = ServerClock(stale_threshold_seconds=1.0)  # 1s threshold for test

    now_local = datetime.now(timezone.utc)
    clock.update_from_server_time(now_local.isoformat())

    time.sleep(1.2)  # Wait for sync to become stale

    assert clock.is_sync_stale() is True
    assert clock.is_time_valid() is False

def test_get_corrected_utc_time():
    clock = ServerClock()
    now_local = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)
    server_time = datetime(2026, 8, 9, 12, 0, 30, tzinfo=timezone.utc)

    clock.update_from_server_time(server_time, local_now_utc=now_local)

    corrected = clock.get_corrected_utc_time(local_now_utc=now_local)
    assert corrected == server_time
