"""
Unit Tests for Enforcement Coordinator Idempotence and Enforcement Toggles.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta
from agent.scheduling.server_clock import ServerClock
from agent.scheduling.session_evaluator import AgentSessionEvaluator
from agent.scheduling.enforcement_coordinator import EnforcementCoordinator
from agent.policy.policy_manager import VerifiedPolicy, ScheduleWindow

def test_enforcement_coordinator_idempotent_activation(tmp_path):
    clock = ServerClock()
    now_utc = datetime(2026, 8, 9, 10, 0, 0, tzinfo=timezone.utc)
    clock.update_from_server_time(now_utc, local_now_utc=now_utc)

    mock_proc_mon = MagicMock()
    mock_telemetry = MagicMock()
    mock_dns = MagicMock()

    coordinator = EnforcementCoordinator(
        server_clock=clock,
        process_monitor=mock_proc_mon,
        telemetry_manager=mock_telemetry,
        dns_controller=mock_dns
    )

    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_utc - timedelta(hours=1),
        expires_at=now_utc + timedelta(hours=5),
        sha256_hash="hash123",
        schedule_windows=[
            ScheduleWindow(
                session_id="sess_100",
                title="Lab Session",
                start_time=now_utc - timedelta(minutes=10),
                end_time=now_utc + timedelta(minutes=50)
            )
        ]
    )

    # 1. First evaluation -> active transition
    res1 = coordinator.evaluate_and_coordinate(policy, local_now_utc=now_utc)
    assert res1["state"] == "active"
    assert coordinator.enforcement_enabled is True
    assert mock_dns.enable_enforcement.call_count == 1
    assert mock_proc_mon.scan_and_enforce.call_count == 1

    # 2. Second evaluation with same state -> idempotent (no repeated state change telemetry or DNS activation)
    res2 = coordinator.evaluate_and_coordinate(policy, local_now_utc=now_utc)
    assert res2["state"] == "active"
    assert mock_dns.enable_enforcement.call_count == 1  # Not called again
    assert mock_proc_mon.scan_and_enforce.call_count == 2  # Scan loop maintained

def test_enforcement_coordinator_deactivation_on_invalid_time():
    clock = ServerClock(max_allowed_skew_seconds=120.0)
    now_local = datetime(2026, 8, 9, 10, 0, 0, tzinfo=timezone.utc)
    clock.update_from_server_time(now_local + timedelta(seconds=250), local_now_utc=now_local)  # Skew exceeds limit

    mock_proc_mon = MagicMock()
    mock_telemetry = MagicMock()
    mock_dns = MagicMock()

    coordinator = EnforcementCoordinator(
        server_clock=clock,
        process_monitor=mock_proc_mon,
        telemetry_manager=mock_telemetry,
        dns_controller=mock_dns
    )

    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_local,
        expires_at=now_local + timedelta(hours=5),
        sha256_hash="hash123",
        schedule_windows=[
            ScheduleWindow(
                session_id="sess_100",
                title="Lab Session",
                start_time=now_local - timedelta(minutes=10),
                end_time=now_local + timedelta(minutes=50)
            )
        ]
    )

    res = coordinator.evaluate_and_coordinate(policy, local_now_utc=now_local)
    assert res["state"] == "invalid_time"
    assert coordinator.enforcement_enabled is False
    assert mock_dns.disable_enforcement.call_count == 1
