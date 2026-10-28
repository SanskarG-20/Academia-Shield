"""
Unit tests for ProtectedProcessManager and system process safeguards.
"""

import sys
import os

AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent.monitoring.protected_processes import ProtectedProcessManager, DEFAULT_PROTECTED_PROCESSES

def test_default_protected_processes():
    mgr = ProtectedProcessManager()
    assert mgr.is_protected("explorer.exe") is True
    assert mgr.is_protected("svchost.exe") is True
    assert mgr.is_protected("python.exe") is True
    assert mgr.is_protected("academia_shield_agent.exe") is True
    assert mgr.is_protected("notepad.exe") is False

def test_dynamic_server_policy_protected_merge():
    mgr = ProtectedProcessManager()
    server_list = [{"executable_name": "custom_exam_browser.exe", "description": "Exam Lock"}, "system_tool.exe"]
    mgr.update_from_policy(server_list)

    assert mgr.is_protected("custom_exam_browser.exe") is True
    assert mgr.is_protected("system_tool.exe") is True
    assert mgr.is_protected("explorer.exe") is True
    assert mgr.is_protected("calculator.exe") is False
