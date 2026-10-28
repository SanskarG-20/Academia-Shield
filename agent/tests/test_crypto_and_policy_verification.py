"""
Tests for Ed25519 Cryptography, Policy Signature Verification, and Update Manifests.
"""

import pytest
import os
import tempfile
from datetime import datetime, timezone, timedelta

from agent.core.auth.crypto import Ed25519Signer
from agent.core.policy.engine import PolicyEngine
from agent.core.storage.database import LocalDatabase
from agent.core.updater.manifest import UpdateManifestVerifier

@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_crypto.db")
    return LocalDatabase(db_path)

def test_ed25519_keypair_generation_and_signing():
    priv, pub = Ed25519Signer.generate_keypair()
    assert len(priv) == 64  # 32-byte hex
    assert len(pub) == 64   # 32-byte hex

    msg = b"Academia Shield Student Session Policy Verification"
    sig = Ed25519Signer.sign_message(priv, msg)
    assert len(sig) == 128  # 64-byte signature hex

    assert Ed25519Signer.verify_signature(pub, sig, msg) is True
    assert Ed25519Signer.verify_signature(pub, sig, b"Tampered Message") is False

def test_policy_engine_clock_skew_and_integrity(temp_db):
    engine = PolicyEngine(temp_db)

    # Valid time within skew
    now_iso = datetime.now(timezone.utc).isoformat()
    assert engine.verify_server_time_skew(now_iso, max_skew=120) is True

    # Invalid time with >120s skew
    stale_iso = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
    assert engine.verify_server_time_skew(stale_iso, max_skew=120) is False

def test_policy_loading_and_rule_matching(temp_db):
    engine = PolicyEngine(temp_db)
    now = datetime.now(timezone.utc)
    
    policy_data = {
        "policy_active": True,
        "session_id": "sess_101",
        "policy_version": 2,
        "server_time_utc": now.isoformat(),
        "expires_at": (now + timedelta(hours=2)).isoformat(),
        "domain_rules": [
            {"id": "r1", "domain_pattern": "cheating.com", "action": "block"},
            {"id": "r2", "domain_pattern": "socialmedia.org", "action": "block"}
        ],
        "application_rules": [
            {"id": "a1", "executable_name": "cheatengine.exe", "action": "close"},
            {"id": "a2", "executable_name": "discord.exe", "action": "warn"}
        ]
    }

    valid, msg = engine.load_and_verify_policy(policy_data)
    assert valid is True

    # Check domain blocking
    blocked, rule_id = engine.should_block_domain("cheating.com")
    assert blocked is True
    assert rule_id == "r1"

    blocked_sub, _ = engine.should_block_domain("sub.socialmedia.org")
    assert blocked_sub is True

    not_blocked, _ = engine.should_block_domain("canvas.edu")
    assert not_blocked is False

    # Check application restriction
    restricted, action, a_rule_id = engine.should_restrict_process("cheatengine.exe")
    assert restricted is True
    assert action == "close"
    assert a_rule_id == "a1"

    restricted_warn, action_warn, _ = engine.should_restrict_process("discord.exe")
    assert restricted_warn is True
    assert action_warn == "warn"

def test_update_manifest_verification():
    priv, pub = Ed25519Signer.generate_keypair()
    verifier = UpdateManifestVerifier(public_key_hex=pub)

    version = "2.4.0"
    platform = "windows"
    sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    download_url = "https://updates.academiashield.org/v2.4.0/agent.exe"

    canonical = f"{version}:{platform}:{sha256}:{download_url}"
    sig = Ed25519Signer.sign_message(priv, canonical.encode("utf-8"))

    manifest = {
        "version": version,
        "platform": platform,
        "sha256": sha256,
        "download_url": download_url,
        "signature": sig
    }

    valid, msg = verifier.verify_manifest(manifest)
    assert valid is True

    # Tampered manifest test
    tampered_manifest = dict(manifest)
    tampered_manifest["sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
    tampered_valid, _ = verifier.verify_manifest(tampered_manifest)
    assert tampered_valid is False
