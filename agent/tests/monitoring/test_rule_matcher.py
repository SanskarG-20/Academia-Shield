"""
Unit tests for 4-tier ApplicationRuleMatcher and priority conflict resolution.
"""

import sys
import os
import pytest

AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent.monitoring.process_snapshot import ProcessMetadata
from agent.monitoring.rule_matcher import ApplicationRuleMatcher, PolicyApplicationRule

def test_process_metadata_normalization():
    proc = ProcessMetadata(pid=101, executable_name="  Notepad.EXE  ")
    assert proc.executable_name == "notepad.exe"

def test_exact_executable_name_matching():
    matcher = ApplicationRuleMatcher()
    rule = PolicyApplicationRule(rule_id="r1", executable_name="calc.exe", action="close", priority=10)
    matcher.set_rules([rule])

    p_match = ProcessMetadata(pid=102, executable_name="calc.exe")
    p_no_match = ProcessMetadata(pid=103, executable_name="notepad.exe")

    matched = matcher.match_process(p_match)
    assert matched is not None
    assert matched.rule_id == "r1"

    assert matcher.match_process(p_no_match) is None

def test_path_pattern_and_hash_matching():
    matcher = ApplicationRuleMatcher()
    rule_hash = PolicyApplicationRule(
        rule_id="r_hash", executable_name="game.exe", trusted_hash="a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890", action="close", priority=50
    )
    rule_pattern = PolicyApplicationRule(
        rule_id="r_pat", executable_name="app.exe", executable_path_pattern="*/temp/*", action="warn", priority=20
    )
    matcher.set_rules([rule_hash, rule_pattern])

    proc_hash = ProcessMetadata(pid=201, executable_name="unknown.exe", trusted_hash="a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4e5f67890")
    matched_hash = matcher.match_process(proc_hash)
    assert matched_hash is not None
    assert matched_hash.rule_id == "r_hash"

    proc_pat = ProcessMetadata(pid=202, executable_name="app.exe", executable_path="c:/users/temp/app.exe")
    matched_pat = matcher.match_process(proc_pat)
    assert matched_pat is not None

def test_priority_and_allow_block_conflict_resolution():
    matcher = ApplicationRuleMatcher()
    rule_allow = PolicyApplicationRule(rule_id="r_allow", executable_name="editor.exe", action="allow", priority=100)
    rule_block = PolicyApplicationRule(rule_id="r_block", executable_name="editor.exe", action="close", priority=50)
    matcher.set_rules([rule_allow, rule_block])

    proc = ProcessMetadata(pid=301, executable_name="editor.exe")
    matched = matcher.match_process(proc)
    assert matched is not None
    assert matched.action == "allow"
    assert matched.rule_id == "r_allow"
