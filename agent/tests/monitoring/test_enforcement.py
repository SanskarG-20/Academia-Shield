"""
Unit tests for EnforcementEngine: actions, cooldowns, notifications, and safeguards.
Never terminates real user applications in automated tests (uses mock platform adapters).
"""

import sys
import os
import time
import pytest

AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent.monitoring.process_snapshot import ProcessMetadata
from agent.monitoring.rule_matcher import PolicyApplicationRule
from agent.monitoring.protected_processes import ProtectedProcessManager
from agent.monitoring.enforcement import EnforcementEngine, EnforcementResult

class MockPlatformAdapter:
    def __init__(self, terminate_success: bool = True):
        self.notifications = []
        self.terminated = []
        self.terminate_success = terminate_success

    def show_notification(self, title: str, message: str) -> None:
        self.notifications.append((title, message))

    def terminate_process_gracefully(self, pid: int, process_name: str) -> bool:
        self.terminated.append((pid, process_name))
        return self.terminate_success

def test_protected_process_skip_behavior():
    adapter = MockPlatformAdapter()
    mgr = ProtectedProcessManager()
    engine = EnforcementEngine(platform_adapter=adapter, protected_manager=mgr, default_grace_period=0)

    proc = ProcessMetadata(pid=1001, executable_name="explorer.exe")
    rule = PolicyApplicationRule(rule_id="r1", executable_name="explorer.exe", action="close", priority=10)

    res = engine.enforce_rule(proc, rule)
    assert res.action_result == "protected"
    assert len(adapter.terminated) == 0

def test_warning_notification_action():
    adapter = MockPlatformAdapter()
    engine = EnforcementEngine(platform_adapter=adapter, default_grace_period=0)

    proc = ProcessMetadata(pid=1002, executable_name="game.exe")
    rule = PolicyApplicationRule(rule_id="r_warn", executable_name="game.exe", action="warn", priority=10, reason="Gaming prohibited")

    res = engine.enforce_rule(proc, rule)
    assert res.action_result == "warned"
    assert res.notification_shown is True
    assert len(adapter.notifications) == 1
    assert len(adapter.terminated) == 0

def test_close_graceful_termination_success_and_failure():
    adapter_success = MockPlatformAdapter(terminate_success=True)
    engine_success = EnforcementEngine(platform_adapter=adapter_success, default_grace_period=0)

    proc = ProcessMetadata(pid=1003, executable_name="app.exe")
    rule = PolicyApplicationRule(rule_id="r_close", executable_name="app.exe", action="close", priority=10)

    res_succ = engine_success.enforce_rule(proc, rule)
    assert res_succ.action_result == "closed"
    assert len(adapter_success.terminated) == 1

    adapter_fail = MockPlatformAdapter(terminate_success=False)
    engine_fail = EnforcementEngine(platform_adapter=adapter_fail, default_grace_period=0)
    res_fail = engine_fail.enforce_rule(proc, rule)
    assert res_fail.action_result == "failed"

def test_cooldown_behavior():
    adapter = MockPlatformAdapter()
    engine = EnforcementEngine(platform_adapter=adapter, default_grace_period=0)

    proc = ProcessMetadata(pid=1004, executable_name="chat.exe")
    rule = PolicyApplicationRule(rule_id="r_cd", executable_name="chat.exe", action="warn", cooldown_seconds=60)

    res1 = engine.enforce_rule(proc, rule)
    assert res1.action_result == "warned"

    # Second immediate enforcement on same process/rule must be skipped due to cooldown
    res2 = engine.enforce_rule(proc, rule)
    assert res2.action_result == "skipped"
    assert "cooldown" in res2.reason
