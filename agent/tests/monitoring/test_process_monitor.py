"""
Integration tests for ProcessMonitor orchestrator.
Tests scanning, expired policy shutdown, offline queueing, and mocked foreground detection.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent.monitoring.process_monitor import ProcessMonitor
from agent.monitoring.process_snapshot import ProcessScanner, ProcessMetadata
from agent.policy.policy_manager import VerifiedPolicy, AppRule, ScheduleWindow
from agent.storage.db import LocalStorageDB
from agent.telemetry.telemetry_manager import TelemetryManager

class MockScanner(ProcessScanner):
    def __init__(self, processes):
        super().__init__()
        self.processes = processes

    def scan_processes(self):
        return self.processes

class MockPlatformAdapter:
    def __init__(self, fg_pid=None):
        self.fg_pid = fg_pid
        self.notifications = []
        self.terminated = []

    def get_foreground_process_id(self):
        return self.fg_pid

    def show_notification(self, title, message):
        self.notifications.append((title, message))

    def terminate_process_gracefully(self, pid, process_name):
        self.terminated.append((pid, process_name))
        return True

def test_expired_policy_stops_enforcement(tmp_path):
    db_path = str(tmp_path / "pm_test.db")
    db = LocalStorageDB(db_path=db_path)
    telem = TelemetryManager(db=db)

    adapter = MockPlatformAdapter()
    scanner = MockScanner([ProcessMetadata(pid=501, executable_name="notepad.exe")])
    pm = ProcessMonitor(platform_adapter=adapter, telemetry_manager=telem, scanner=scanner)

    past = datetime.now(timezone.utc) - timedelta(hours=2)
    expired_policy = VerifiedPolicy(
        policy_version=100,
        issued_at=past - timedelta(hours=1),
        expires_at=past,
        sha256_hash="hash",
        schedule_windows=[ScheduleWindow("s_old", "Old Lab", past - timedelta(hours=1), past)],
        app_rules=[AppRule("notepad.exe", "close", 100)]
    )

    violations = pm.scan_and_enforce(expired_policy)
    assert len(violations) == 0
    assert len(adapter.terminated) == 0

def test_active_policy_scan_and_telemetry_queueing(tmp_path):
    db_path = str(tmp_path / "pm_active.db")
    db = LocalStorageDB(db_path=db_path)
    telem = TelemetryManager(db=db)

    adapter = MockPlatformAdapter(fg_pid=601)
    scanner = MockScanner([ProcessMetadata(pid=601, executable_name="notepad.exe", is_foreground=True)])
    pm = ProcessMonitor(platform_adapter=adapter, telemetry_manager=telem, scanner=scanner)

    now = datetime.now(timezone.utc)
    active_policy = VerifiedPolicy(
        policy_version=200,
        issued_at=now,
        expires_at=now + timedelta(hours=2),
        sha256_hash="hash",
        schedule_windows=[ScheduleWindow("sess_active", "Exam", now - timedelta(minutes=5), now + timedelta(hours=1))],
        app_rules=[AppRule("notepad.exe", "warn", 100)]
    )

    # Disable automatic flush during test so queued batch can be asserted
    telem.flush_queue = lambda: None

    violations = pm.scan_and_enforce(active_policy)
    assert len(violations) == 1
    assert violations[0]["executable_name"] == "notepad.exe"
    assert violations[0]["action_requested"] == "warn"

    # Verify event was queued in SQLite offline storage
    queued = db.peek_telemetry_batch(limit=10)
    assert len(queued) >= 1
    assert queued[0]["event_type"] == "application_violation"

def test_foreground_restricted_website_violation_recorded_without_closing_browser(tmp_path):
    class MockForegroundDetector:
        def __init__(self, title=""):
            self.title = title
        def get_foreground_window_title(self):
            return self.title

    from agent.policy.policy_manager import DomainRule

    db_path = str(tmp_path / "pm_web.db")
    db = LocalStorageDB(db_path=db_path)
    telem = TelemetryManager(db=db)

    adapter = MockPlatformAdapter()
    fg_detector = MockForegroundDetector("YouTube - Google Chrome")
    scanner = MockScanner([ProcessMetadata(pid=801, executable_name="chrome.exe", is_foreground=True)])
    scanner.foreground_detector = fg_detector
    pm = ProcessMonitor(platform_adapter=adapter, telemetry_manager=telem, scanner=scanner)

    now = datetime.now(timezone.utc)
    active_policy = VerifiedPolicy(
        policy_version=300,
        issued_at=now,
        expires_at=now + timedelta(hours=2),
        sha256_hash="hash",
        schedule_windows=[ScheduleWindow("sess_web", "Math Lab", now - timedelta(minutes=5), now + timedelta(hours=1))],
        domain_rules=[DomainRule("youtube.com", "block", 10)],
        app_rules=[]  # Empty app rules: ensures monitor runs even when only websites are restricted
    )

    telem.flush_queue = lambda: None

    violations = pm.scan_and_enforce(active_policy)
    assert len(violations) == 1
    assert violations[0]["event_type"] == "dns_block"
    assert violations[0]["resource"] == "youtube.com"
    assert violations[0]["is_violation"] is True

    # Browser must NEVER be terminated!
    assert len(adapter.terminated) == 0

    # Notification was shown to student
    assert len(adapter.notifications) == 1
    assert "Academic Session Restriction" in adapter.notifications[0][0]

    # Queued in SQLite
    queued = db.peek_telemetry_batch(limit=10)
    assert len(queued) >= 1
    assert queued[0]["resource"] == "youtube.com"

