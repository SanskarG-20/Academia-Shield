"""
Unit tests for Policy Manager, SHA-256 integrity, schedules, and expiry.
"""

import json
import hashlib
from datetime import datetime, timezone, timedelta
from agent.policy.policy_manager import PolicyManager, VerifiedPolicy, ScheduleWindow, DomainRule, AppRule
from agent.storage.db import LocalStorageDB

def test_schedule_window_active():
    now = datetime.now(timezone.utc)
    w_active = ScheduleWindow("s1", "Math", now - timedelta(minutes=10), now + timedelta(minutes=10), status="scheduled")
    w_past = ScheduleWindow("s2", "Physics", now - timedelta(hours=2), now - timedelta(hours=1), status="scheduled")
    
    assert w_active.is_active(now) is True
    assert w_past.is_active(now) is False

def test_policy_integrity_and_expiry(tmp_path):
    db_path = str(tmp_path / "test_policy.db")
    db = LocalStorageDB(db_path=db_path)
    
    now = datetime.now(timezone.utc)
    raw_policy = {
        "policy_version": 1001,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "active_sessions": [{
            "id": "sess_1",
            "title": "Computer Networks",
            "start_time": (now - timedelta(minutes=5)).isoformat(),
            "end_time": (now + timedelta(minutes=25)).isoformat()
        }],
        "domain_rules": [{"domain": "facebook.com", "action": "block", "priority": 10}],
        "app_rules": [{"application": "steam.exe", "action": "close", "priority": 10}],
        "poll_interval": 8
    }
    calc_sha = hashlib.sha256(json.dumps(raw_policy, sort_keys=True).encode("utf-8")).hexdigest()
    raw_policy["sha256"] = calc_sha

    pm = PolicyManager(db=db)
    verified, parse_err = pm._parse_and_verify(raw_policy, is_offline=False)
    
    assert parse_err is None
    assert verified is not None
    assert verified.policy_version == 1001
    assert verified.is_expired(now) is False
    assert verified.is_session_active(now) is True
    assert verified.get_active_blocked_domains(now) == ["facebook.com"]
    assert verified.get_active_blocked_apps(now) == ["steam.exe"]

def test_policy_expired_stops_enforcement(tmp_path):
    db_path = str(tmp_path / "test_policy_exp.db")
    db = LocalStorageDB(db_path=db_path)
    
    past = datetime.now(timezone.utc) - timedelta(hours=5)
    raw_expired = {
        "policy_version": 999,
        "issued_at": (past - timedelta(hours=1)).isoformat(),
        "expires_at": past.isoformat(),
        "active_sessions": [{
            "id": "sess_old",
            "title": "Old Session",
            "start_time": (past - timedelta(hours=1)).isoformat(),
            "end_time": past.isoformat()
        }],
        "domain_rules": [{"domain": "reddit.com", "action": "block", "priority": 10}],
        "app_rules": [{"application": "discord.exe", "action": "close", "priority": 10}],
        "poll_interval": 8
    }
    
    pm = PolicyManager(db=db)
    verified, parse_err = pm._parse_and_verify(raw_expired, is_offline=True)
    
    assert verified.is_expired() is True
    # Expired policy must safely return empty lists for enforcement
    assert verified.get_active_blocked_domains() == []
    assert verified.get_active_blocked_apps() == []

def test_parse_fallback_and_websites_format(tmp_path):
    db_path = str(tmp_path / "test_policy_fallback.db")
    db = LocalStorageDB(db_path=db_path)
    
    fallback_data = {
        "policy_active": True,
        "policy_id": "global_policy",
        "version": 42,
        "mode": "Blocklist",
        "websites": ["facebook.com", "instagram.com"],
        "applications": ["discord.exe", "spotify.exe"],
    }
    
    pm = PolicyManager(db=db)
    verified, parse_err = pm._parse_and_verify(fallback_data, is_offline=False)
    
    assert parse_err is None
    assert verified is not None
    assert verified.policy_version == 42
    assert [r.domain for r in verified.domain_rules] == ["facebook.com", "instagram.com"]
    assert [r.application for r in verified.app_rules] == ["discord.exe", "spotify.exe"]
    assert verified.is_expired() is False

def test_expired_policy_warning_deduplication(tmp_path, caplog):
    import logging
    db_path = str(tmp_path / "test_policy_dedup.db")
    db = LocalStorageDB(db_path=db_path)
    
    past = datetime.now(timezone.utc) - timedelta(days=2)
    raw_expired = {
        "policy_version": 888,
        "issued_at": (past - timedelta(hours=1)).isoformat(),
        "expires_at": past.isoformat(),
        "domains": ["tiktok.com"],
    }
    db.save_policy(raw_expired)
    
    class FakeOfflineClient:
        def fetch_policy(self):
            raise ConnectionError("Offline")
        def fetch_config(self):
            return None
    
    pm = PolicyManager(db=db, api_client=FakeOfflineClient())
    
    with caplog.at_level(logging.WARNING):
        # 1st sync - should log warning
        p1, msg1 = pm.sync_policy()
        assert "EXPIRED" in msg1
        warn_count_1 = sum(1 for r in caplog.records if "EXPIRED" in r.message and r.levelno == logging.WARNING)
        assert warn_count_1 == 1
        
        # 2nd sync with same expired policy - should NOT log warning again (deduplicated)
        p2, msg2 = pm.sync_policy()
        assert "EXPIRED" in msg2
        warn_count_2 = sum(1 for r in caplog.records if "EXPIRED" in r.message and r.levelno == logging.WARNING)
        assert warn_count_2 == 1

def test_save_policy_with_none_values(tmp_path):
    db_path = str(tmp_path / "test_policy_none.db")
    db = LocalStorageDB(db_path=db_path)
    
    # Payload from server when policy_active is False contains None for policy_version, issued_at, etc.
    policy_with_nones = {
        "policy_active": False,
        "policy_version": None,
        "issued_at": None,
        "expires_at": None,
        "sha256": None,
        "reason": "No active session"
    }
    
    assert db.save_policy(policy_with_nones) is True
    cached = db.get_latest_policy()
    assert cached is not None
    assert cached["policy_active"] is False

