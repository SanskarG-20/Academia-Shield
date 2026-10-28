"""
Unit Tests for Agent Session Evaluator.
"""

import pytest
from datetime import datetime, timezone, timedelta
from agent.scheduling.server_clock import ServerClock
from agent.scheduling.session_evaluator import AgentSessionEvaluator
from agent.policy.policy_manager import VerifiedPolicy, ScheduleWindow

def test_evaluator_active_session():
    clock = ServerClock()
    now_utc = datetime(2026, 8, 9, 10, 30, 0, tzinfo=timezone.utc)
    clock.update_from_server_time(now_utc, local_now_utc=now_utc)

    evaluator = AgentSessionEvaluator(server_clock=clock)

    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_utc - timedelta(hours=1),
        expires_at=now_utc + timedelta(hours=5),
        sha256_hash="hash123",
        schedule_windows=[
            ScheduleWindow(
                session_id="sess_123",
                title="Active Session",
                start_time=now_utc - timedelta(minutes=30),
                end_time=now_utc + timedelta(minutes=30)
            )
        ]
    )

    res = evaluator.evaluate_policy_session(policy, local_now_utc=now_utc)
    assert res["state"] == "active"
    assert res["session_id"] == "sess_123"

def test_evaluator_invalid_time_excessive_skew():
    clock = ServerClock(max_allowed_skew_seconds=120.0)
    now_local = datetime(2026, 8, 9, 10, 0, 0, tzinfo=timezone.utc)
    server_time = now_local + timedelta(seconds=300)  # Skew 300s > 120s

    clock.update_from_server_time(server_time, local_now_utc=now_local)

    evaluator = AgentSessionEvaluator(server_clock=clock)

    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_local,
        expires_at=now_local + timedelta(hours=5),
        sha256_hash="hash123",
        schedule_windows=[
            ScheduleWindow(
                session_id="sess_123",
                title="Active Session",
                start_time=now_local - timedelta(minutes=30),
                end_time=now_local + timedelta(minutes=30)
            )
        ]
    )

    res = evaluator.evaluate_policy_session(policy, local_now_utc=now_local)
    assert res["state"] == "invalid_time"
    assert "Clock skew" in res["reason"]

def test_evaluator_expired_policy():
    clock = ServerClock()
    now_utc = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)
    clock.update_from_server_time(now_utc, local_now_utc=now_utc)

    evaluator = AgentSessionEvaluator(server_clock=clock)

    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_utc - timedelta(hours=10),
        expires_at=now_utc - timedelta(hours=1),  # Expired
        sha256_hash="hash123",
        schedule_windows=[]
    )

    res = evaluator.evaluate_policy_session(policy, local_now_utc=now_utc)
    assert res["state"] == "expired"
