import pytest
from datetime import datetime, timezone, timedelta
from agent.policy.policy_manager import PolicyManager, VerifiedPolicy, ScheduleWindow, DomainRule, AppRule
from agent.monitoring.rule_matcher import ApplicationRuleMatcher, PolicyApplicationRule
from agent.monitoring.process_snapshot import ProcessMetadata

def test_legacy_config_conversion_duration():
    pm = PolicyManager()
    cfg = {
        "active": True,
        "domains": ["youtube.com", "facebook.com"],
        "applications": ["notepad.exe", "discord"]
    }
    policy_dict = pm._convert_legacy_config_to_policy(cfg)
    policy, err = pm._parse_and_verify(policy_dict, is_offline=False)
    
    assert err is None
    assert policy is not None
    assert not policy.is_expired()
    assert policy.is_session_active()
    
    domains = policy.get_active_blocked_domains()
    apps = policy.get_active_blocked_apps()
    
    assert "youtube.com" in domains
    assert "facebook.com" in domains
    assert "notepad.exe" in apps
    assert "discord" in apps

def test_active_session_status_override():
    now = datetime.now(timezone.utc)
    # Session started with naive local datetime in past or future
    window = ScheduleWindow(
        session_id="sess1",
        title="Lecture",
        start_time=now - timedelta(hours=2),
        end_time=now + timedelta(hours=1),
        status="Active"
    )
    assert window.is_active(now) is True

def test_rule_matcher_executable_variations():
    matcher = ApplicationRuleMatcher()
    rules = [
        PolicyApplicationRule(rule_id="r1", executable_name="discord", action="close"),
        PolicyApplicationRule(rule_id="r2", executable_name="spotify.exe", action="close")
    ]
    matcher.set_rules(rules)

    proc_discord = ProcessMetadata(pid=101, executable_name="Discord.exe")
    proc_spotify = ProcessMetadata(pid=102, executable_name="spotify")

    match1 = matcher.match_process(proc_discord)
    assert match1 is not None
    assert match1.rule_id == "r1"

    match2 = matcher.match_process(proc_spotify)
    assert match2 is not None
    assert match2.rule_id == "r2"
