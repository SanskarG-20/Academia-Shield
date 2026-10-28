"""
Unit tests for process rule matching and critical OS process safeguards.
"""

from datetime import datetime, timezone, timedelta
from agent.monitoring.process_monitor import ProcessMonitor
from agent.platform.base import BasePlatformAdapter
from agent.policy.policy_manager import VerifiedPolicy, AppRule, ScheduleWindow

class DummyPlatformAdapter(BasePlatformAdapter):
    def __init__(self):
        self.notifications = []
        self.terminated = []

    def is_admin(self) -> bool:
        return False

    def show_notification(self, title: str, message: str) -> None:
        self.notifications.append((title, message))

    def terminate_process_gracefully(self, pid: int, process_name: str) -> bool:
        self.terminated.append((pid, process_name))
        return True

    def get_os_info(self) -> dict:
        return {"os_name": "TestOS", "os_version": "1.0"}

def test_process_monitor_safeguards(tmp_path):
    adapter = DummyPlatformAdapter()
    pm = ProcessMonitor(platform_adapter=adapter)
    
    now = datetime.now(timezone.utc)
    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        sha256_hash="test",
        schedule_windows=[ScheduleWindow("s1", "Lab", now - timedelta(minutes=5), now + timedelta(minutes=50))],
        app_rules=[AppRule("svchost.exe", "close", 10), AppRule("calculator.exe", "close", 10)]
    )

    violations = pm.scan_and_enforce(policy)
    
    # Critical process 'svchost.exe' MUST NEVER be terminated
    for v in violations:
        assert v["process_name"] != "svchost.exe"
        assert v["process_name"] != "explorer.exe"
        assert v["process_name"] != "python.exe"
