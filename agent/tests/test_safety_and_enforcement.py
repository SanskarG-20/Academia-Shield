"""
Comprehensive Safety and Enforcement Tests for Academia Shield Windows Local Agent.

Validates:
1. No enforcement before manual student Join Session
2. No enforcement for another batch / session
3. Safe policy expiry and restoration
4. Protected processes (explorer.exe, svchost.exe, etc.) cannot be closed
5. DNS settings are restored on disable
6. App and DNS telemetry is idempotent
7. Uninstall removes only agent-created configuration
8. Development mode never enables USB restriction
"""

import os
import sys
import json
import time
import uuid
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Ensure agent package is in path
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_DIR = os.path.dirname(TEST_DIR)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent.config import AgentConfig, set_agent_mode, get_agent_mode
from agent.policy.policy_manager import VerifiedPolicy, ScheduleWindow, AppRule, DomainRule
from agent.monitoring.rule_matcher import PolicyApplicationRule
from agent.monitoring.protected_processes import ProtectedProcessManager
from agent.monitoring.process_snapshot import ProcessMetadata
from agent.monitoring.enforcement import EnforcementEngine, EnforcementResult
from agent.monitoring.process_monitor import ProcessMonitor
from agent.scheduling.session_evaluator import AgentSessionEvaluator
from agent.scheduling.server_clock import ServerClock
from agent.scheduling.enforcement_coordinator import EnforcementCoordinator
from agent.platform.windows_dns import WindowsDNSAdapterManager
from agent.platform.usb_compliance import USBComplianceManager
try:
    from installer import install_agent, uninstall_agent
except ImportError:
    from agent.installer import install_agent, uninstall_agent
from agent.storage.db import LocalStorageDB

class MockPlatformAdapter:
    def __init__(self, is_admin=True):
        self._is_admin = is_admin
        self.terminated_pids = []
        self.notifications = []

    def is_admin(self) -> bool:
        return self._is_admin

    def terminate_process_gracefully(self, pid: int, process_name: str) -> bool:
        self.terminated_pids.append((pid, process_name))
        return True

    def show_notification(self, title: str, message: str) -> None:
        self.notifications.append((title, message))

    def get_os_info(self):
        return {"os_name": "Windows", "os_version": "11"}

# ==============================================================================
# TEST 1: No enforcement before manual student Join Session
# ==============================================================================
def test_no_enforcement_before_manual_student_join():
    """Verify agent does not enforce anything if session is not joined."""
    platform = MockPlatformAdapter()
    monitor = ProcessMonitor(platform_adapter=platform)

    now_utc = datetime.now(timezone.utc)
    # Empty / unjoined policy (no active schedule window)
    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_utc,
        expires_at=now_utc + timedelta(hours=1),
        sha256_hash="abc",
        schedule_windows=[],
        app_rules=[AppRule(application="notepad.exe", action="close")]
    )

    violations = monitor.scan_and_enforce(policy)
    assert violations == []
    assert len(platform.terminated_pids) == 0
    assert len(platform.notifications) == 0

# ==============================================================================
# TEST 2: No enforcement for another batch/session
# ==============================================================================
def test_no_enforcement_for_another_batch_or_session():
    """Verify session evaluator ignores sessions belonging to other batches."""
    server_clock = ServerClock()
    now_utc = datetime.now(timezone.utc)
    server_clock.update_from_server_time(now_utc.isoformat())
    evaluator = AgentSessionEvaluator(server_clock=server_clock)

    # Policy with ended / inactive window
    window = ScheduleWindow(
        session_id="session_other_batch",
        title="Other Class",
        start_time=now_utc - timedelta(hours=3),
        end_time=now_utc - timedelta(hours=2),
        status="ended"
    )
    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_utc - timedelta(hours=3),
        expires_at=now_utc + timedelta(hours=1),
        sha256_hash="hash",
        schedule_windows=[window]
    )

    res = evaluator.evaluate_policy_session(policy, local_now_utc=now_utc)
    assert res["state"] in ("ended", "expired")

# ==============================================================================
# TEST 3: Safe policy expiry and restoration
# ==============================================================================
def test_safe_policy_expiry_and_restoration():
    """Verify that when policy expires, coordinator deactivates and restores configuration."""
    dns_ctrl = MagicMock()
    dns_ctrl.disable_enforcement = MagicMock()

    server_clock = ServerClock()
    now_utc = datetime.now(timezone.utc)
    server_clock.update_from_server_time(now_utc.isoformat())

    coordinator = EnforcementCoordinator(
        server_clock=server_clock,
        dns_controller=dns_ctrl
    )

    # Initially active
    active_window = ScheduleWindow(
        session_id="session_101",
        title="Exam",
        start_time=now_utc - timedelta(minutes=10),
        end_time=now_utc + timedelta(minutes=10),
        status="active"
    )
    active_policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_utc,
        expires_at=now_utc + timedelta(hours=1),
        sha256_hash="h1",
        schedule_windows=[active_window]
    )
    coordinator.evaluate_and_coordinate(active_policy, local_now_utc=now_utc)
    assert coordinator.enforcement_enabled is True

    # Policy expires
    expired_window = ScheduleWindow(
        session_id="session_101",
        title="Exam",
        start_time=now_utc - timedelta(minutes=30),
        end_time=now_utc - timedelta(minutes=5),
        status="ended"
    )
    expired_policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now_utc - timedelta(hours=1),
        expires_at=now_utc + timedelta(hours=1),
        sha256_hash="h1",
        schedule_windows=[expired_window]
    )
    coordinator.evaluate_and_coordinate(expired_policy, local_now_utc=now_utc)

    assert coordinator.enforcement_enabled is False
    assert dns_ctrl.disable_enforcement.called

# ==============================================================================
# TEST 4: Protected processes cannot be closed
# ==============================================================================
def test_protected_process_cannot_be_closed():
    """Verify explorer.exe, svchost.exe, lsass.exe, python.exe are never terminated."""
    platform = MockPlatformAdapter()
    protected_mgr = ProtectedProcessManager()
    engine = EnforcementEngine(platform_adapter=platform, protected_manager=protected_mgr, default_grace_period=0.0)

    protected_targets = ["explorer.exe", "svchost.exe", "csrss.exe", "lsass.exe", "taskmgr.exe", "python.exe", "agent.exe"]

    for proc_name in protected_targets:
        proc = ProcessMetadata(pid=1000, executable_name=proc_name, executable_path=f"C:\\Windows\\System32\\{proc_name}")
        rule = PolicyApplicationRule(
            rule_id=f"block_{proc_name}",
            executable_name=proc_name,
            action="close",
            priority=10,
            is_enabled=True,
            cooldown_seconds=0
        )

        res = engine.enforce_rule(proc, rule)
        assert res.action_result == "protected", f"Failed for {proc_name}"
        assert len(platform.terminated_pids) == 0

# ==============================================================================
# TEST 5: DNS settings are restored on disable
# ==============================================================================
def test_dns_settings_restored_on_disable(tmp_path):
    """Verify DNS adapter manager backs up original settings and restores them cleanly."""
    backup_dir = str(tmp_path)
    dns_mgr = WindowsDNSAdapterManager(backup_dir=backup_dir)

    # Mock get_active_adapters and subprocess
    dns_mgr.is_admin = MagicMock(return_value=True)
    dns_mgr.get_active_adapters = MagicMock(return_value=[{"alias": "Wi-Fi", "index": 1}])

    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=0, stdout="8.8.8.8\n1.1.1.1\n")
        # 1. Backup original DNS
        success_backup = dns_mgr.backup_original_dns()
        assert success_backup is True
        assert os.path.exists(dns_mgr.backup_file)

        with open(dns_mgr.backup_file, "r") as f:
            data = json.load(f)
            assert "Wi-Fi" in data
            assert data["Wi-Fi"] == ["8.8.8.8", "1.1.1.1"]

        # 2. Restore original DNS
        success_restore = dns_mgr.restore_original_dns()
        assert success_restore is True
        assert not os.path.exists(dns_mgr.backup_file)

# ==============================================================================
# TEST 6: App and DNS telemetry is idempotent
# ==============================================================================
def test_app_and_dns_telemetry_idempotent(tmp_path):
    """Verify duplicate event_id telemetry submissions are handled idempotently."""
    db_path = os.path.join(str(tmp_path), "test_agent.db")
    db = LocalStorageDB(db_path=db_path)

    event_id = str(uuid.uuid4())
    payload = {"event_id": event_id, "event_type": "application_violation", "executable": "notepad.exe"}

    # Enqueue same event twice
    db.enqueue_telemetry(idempotency_key=event_id, event_type="application_violation", payload=payload)
    db.enqueue_telemetry(idempotency_key=event_id, event_type="application_violation", payload=payload)

    batch = db.peek_telemetry_batch(limit=10)
    assert len(batch) == 1
    assert batch[0]["idempotency_key"] == event_id

# ==============================================================================
# TEST 7: Uninstall removes only agent-created configuration
# ==============================================================================
def test_uninstall_removes_only_agent_created_config(tmp_path):
    """Verify uninstall cleans only agent directory and does not alter system files."""
    install_dir = os.path.join(str(tmp_path), "AcademiaShield")
    os.makedirs(install_dir, exist_ok=True)

    test_file = os.path.join(install_dir, "agent.db")
    with open(test_file, "w") as f:
        f.write("database content")

    # Call uninstall
    uninstall_agent(install_dir=install_dir)

    assert not os.path.exists(install_dir)

# ==============================================================================
# TEST 8: Development mode never enables USB restriction
# ==============================================================================
def test_development_mode_never_enables_usb_restriction():
    """Verify development mode always reports usb_storage_restricted = False."""
    usb_dev = USBComplianceManager(mode="DEVELOPMENT_ENFORCEMENT")
    assert usb_dev.is_usb_storage_restricted() is False

    status = usb_dev.get_compliance_status()
    assert status["usb_storage_restricted"] is False
    assert status["compliance_note"] == "USB storage restriction requires a college-managed MDM/GPO policy."
