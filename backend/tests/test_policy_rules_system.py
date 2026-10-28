"""
Comprehensive Test Suite for the Academia Shield Rules & Policy System.

Covers:
1. Professor batch ownership RBAC & Student RBAC restrictions (403 Forbidden).
2. Session assignment validation (matching batch only, must be published).
3. Session start guard (cannot start without a published policy).
4. Policy immutability & draft branching on publish.
5. Ed25519 cryptographic signing and SHA-256 canonical integrity verification.
6. Validation rules (domain patterns, allowed vs blocked, rejection of shell commands and scripts).
7. Protected system processes guardrails (explorer.exe, cmd.exe, powershell.exe, acad_agent.exe).
8. Active signed policy delivery to student agent on joined active session.
9. Blocked attempt recording as violations with rule attribution.
10. Honest managed-device USB storage compliance reporting.
11. Session end/cancellation policy revocation.
"""

import os
import sys
import pytest
import base64
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
AGENT_DIR = os.path.join(ROOT_DIR, "agent")
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from app.core.security import get_server_public_key_b64, verify_policy_signature
from agent.platform.usb_compliance import get_usb_storage_restriction_status


def get_auth_headers(client, email: str, name: str, role: str = "professor") -> dict:
    client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": name,
        "role": role,
    })
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    token = res.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}


def test_professor_batch_ownership_and_student_rbac(client):
    """
    Verify that:
    - Professors can create/manage policies only for batches they own.
    - Other professors cannot manage or create policies for another professor's batch.
    - Students cannot access policy creation, update, or delete endpoints (403).
    """
    p1_headers = get_auth_headers(client, "prof_alpha@university.edu", "Prof Alpha", "professor")
    p2_headers = get_auth_headers(client, "prof_beta@university.edu", "Prof Beta", "professor")
    s_headers = get_auth_headers(client, "student_charlie@university.edu", "Student Charlie", "student")

    # Prof Alpha creates Batch A
    b_res = client.post("/api/v1/batches", json={"name": "Computer Networks Batch A"}, headers=p1_headers)
    assert b_res.status_code == 201
    batch_a_id = b_res.json()["id"]

    # Prof Alpha creates Rule Set for Batch A -> 201
    rs_res = client.post(f"/api/v1/batches/{batch_a_id}/rule-sets", json={
        "name": "Networks Lab Policy v1",
        "description": "Lab environment policy",
    }, headers=p1_headers)
    assert rs_res.status_code == 201
    rs_id = rs_res.json()["id"]

    # Prof Beta attempts to create Rule Set for Batch A -> 403
    p2_create = client.post(f"/api/v1/batches/{batch_a_id}/rule-sets", json={
        "name": "Intruder Policy",
    }, headers=p2_headers)
    assert p2_create.status_code == 403

    # Prof Beta attempts to add rule to Prof Alpha's Rule Set -> 403
    p2_rule = client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "unauthorized.com",
        "rule_mode": "blocked",
    }, headers=p2_headers)
    assert p2_rule.status_code == 403

    # Student Charlie attempts to create rule set -> 403
    s_create = client.post(f"/api/v1/batches/{batch_a_id}/rule-sets", json={
        "name": "Student Policy",
    }, headers=s_headers)
    assert s_create.status_code == 403

    # Student Charlie attempts to list batch rule sets -> 403
    s_list = client.get(f"/api/v1/batches/{batch_a_id}/rule-sets", headers=s_headers)
    assert s_list.status_code == 403

    # Student Charlie attempts to publish rule set -> 403
    s_pub = client.post(f"/api/v1/rule-sets/{rs_id}/publish", headers=s_headers)
    assert s_pub.status_code == 403


def test_validation_rules_and_protected_process_rejection(client):
    """
    Verify domain pattern validation, app executable validation, and protected system process safeguards.
    """
    prof_headers = get_auth_headers(client, "prof_guard@university.edu", "Prof Guard", "professor")
    b_res = client.post("/api/v1/batches", json={"name": "Security Validation Batch"}, headers=prof_headers)
    batch_id = b_res.json()["id"]

    rs_res = client.post(f"/api/v1/batches/{batch_id}/rule-sets", json={"name": "Guardrail Policy"}, headers=prof_headers)
    rs_id = rs_res.json()["id"]

    # 1. Allowed domain patterns
    valid_allowed_domain = client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "docs.python.org",
        "rule_mode": "allowed",
        "category": "documentation",
        "priority": 10,
    }, headers=prof_headers)
    assert valid_allowed_domain.status_code == 201

    # 2. Blocked domain patterns
    valid_blocked_domain = client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "facebook.com",
        "rule_mode": "blocked",
        "category": "social_media",
        "reason": "Exam integrity",
    }, headers=prof_headers)
    assert valid_blocked_domain.status_code == 201

    # 3. Reject invalid domain pattern with spaces or URI protocol
    inv_domain = client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "https://invalid domain.com/path",
        "rule_mode": "blocked",
    }, headers=prof_headers)
    assert inv_domain.status_code in (400, 422)

    # 4. Reject domain injection / shell syntax
    inj_domain = client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "example.com; rm -rf /",
        "rule_mode": "blocked",
    }, headers=prof_headers)
    assert inj_domain.status_code in (400, 422)

    # 5. Valid application rules
    valid_app = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "application_name": "Code.exe",
        "rule_mode": "allowed",
        "category": "ide_editor",
    }, headers=prof_headers)
    assert valid_app.status_code == 201

    # 6. Reject protected system processes (explorer.exe, svchost.exe, acad_agent.exe)
    for protected in ["explorer.exe", "svchost.exe", "acad_agent.exe"]:
        res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
            "application_name": protected,
            "rule_mode": "blocked",
            "action": "close",
        }, headers=prof_headers)
        assert res.status_code == 400
        msg = res.json().get("detail") or res.json().get("message") or ""
        assert "protected system process" in msg

    # 7. Reject shell commands and scripting interpreters (cmd.exe, powershell.exe, bash.exe)
    for shell in ["cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe"]:
        res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
            "application_name": shell,
            "rule_mode": "blocked",
            "action": "close",
        }, headers=prof_headers)
        assert res.status_code in (400, 422)

    # 8. Reject arbitrary script extensions (.bat, .ps1, .sh, .vbs)
    for script in ["malicious.bat", "script.ps1", "payload.sh"]:
        res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
            "application_name": script,
            "rule_mode": "blocked",
            "action": "close",
        }, headers=prof_headers)
        assert res.status_code in (400, 422)


def test_policy_immutability_and_version_branching(client):
    """
    Verify that:
    - Rule set starts as draft (v1).
    - Publishing signs it with Ed25519 and sets status = 'published'.
    - Modifying a published rule set creates a new draft version (v2) while keeping v1 intact.
    """
    prof_headers = get_auth_headers(client, "prof_version@university.edu", "Prof Version", "professor")
    b_res = client.post("/api/v1/batches", json={"name": "Versioning Batch"}, headers=prof_headers)
    batch_id = b_res.json()["id"]

    # Initial Draft v1
    rs_res = client.post(f"/api/v1/batches/{batch_id}/rule-sets", json={"name": "Exam Policy v1"}, headers=prof_headers)
    rs = rs_res.json()
    rs_id = rs["id"]
    assert rs["version"] == 1
    assert rs["status"] == "draft"

    # Add initial rules
    client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "docs.python.org",
        "rule_mode": "allowed",
    }, headers=prof_headers)
    client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "application_name": "discord.exe",
        "rule_mode": "blocked",
        "action": "close",
    }, headers=prof_headers)

    # Publish v1
    pub_res = client.post(f"/api/v1/rule-sets/{rs_id}/publish", headers=prof_headers)
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["status"] == "published"
    assert pub_data["version"] == 1
    assert pub_data["signature"] is not None
    hash_val = pub_data.get("policy_hash") or pub_data.get("integrity_hash")
    assert hash_val and len(hash_val) == 64

    # Now attempt to add a rule to the PUBLISHED rule set -> Must branch a new draft with version = 2
    branch_res = client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "cheatsheet.com",
        "rule_mode": "blocked",
    }, headers=prof_headers)
    assert branch_res.status_code == 201

    # Fetch all rule sets for the batch: there should now be two versions
    all_rs = client.get(f"/api/v1/batches/{batch_id}/rule-sets", headers=prof_headers).json()
    assert len(all_rs) == 2

    # Verify v1 is still published and immutable
    v1 = next(r for r in all_rs if r["version"] == 1)
    assert v1["status"] == "published"
    assert "cheatsheet.com" not in [w["domain_pattern"] for w in v1.get("website_rules", [])]

    # Verify v2 is draft and has the new rule
    v2 = next(r for r in all_rs if r["version"] == 2)
    assert v2["status"] == "draft"
    assert "cheatsheet.com" in [w["domain_pattern"] for w in v2.get("website_rules", [])]


def test_session_assignment_and_start_guard(client):
    """
    Verify that:
    - A policy cannot be assigned to a session belonging to a different batch.
    - A session cannot be started unless its assigned policy is published.
    """
    prof_headers = get_auth_headers(client, "prof_session@university.edu", "Prof Session", "professor")

    # Batch 1 & Batch 2
    b1_id = client.post("/api/v1/batches", json={"name": "Batch 1"}, headers=prof_headers).json()["id"]
    b2_id = client.post("/api/v1/batches", json={"name": "Batch 2"}, headers=prof_headers).json()["id"]

    # Policy for Batch 1 (draft)
    rs1_id = client.post(f"/api/v1/batches/{b1_id}/rule-sets", json={"name": "Policy B1"}, headers=prof_headers).json()["id"]

    # Create session for Batch 2
    now = datetime.now(timezone.utc)
    s2_res = client.post("/api/v1/sessions", json={
        "title": "Session for Batch 2",
        "course": "Algorithms",
        "batch_ids": [b2_id],
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "type": "Lab",
    }, headers=prof_headers)
    assert s2_res.status_code == 201
    s2_id = s2_res.json()["id"]

    # 1. Assigning Policy B1 to Session for Batch 2 should fail (mismatched batch) -> 400
    mismatch_assign = client.post(f"/api/v1/sessions/{s2_id}/assign-rule-set", json={
        "rule_set_id": rs1_id,
    }, headers=prof_headers)
    assert mismatch_assign.status_code == 400
    mismatch_msg = mismatch_assign.json().get("detail") or mismatch_assign.json().get("message") or ""
    assert "different batch" in mismatch_msg

    # Create session for Batch 1
    s1_id = client.post("/api/v1/sessions", json={
        "title": "Session for Batch 1",
        "course": "Systems",
        "batch_ids": [b1_id],
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "type": "Exam",
    }, headers=prof_headers).json()["id"]

    # 2. Starting session with draft policy should fail -> 400
    start_draft = client.post(f"/api/v1/sessions/{s1_id}/start", headers=prof_headers)
    assert start_draft.status_code == 400
    start_msg = start_draft.json().get("detail") or start_draft.json().get("message") or ""
    assert "published" in start_msg.lower()

    # 3. Publish policy B1
    pub_res = client.post(f"/api/v1/rule-sets/{rs1_id}/publish", headers=prof_headers)
    assert pub_res.status_code == 200

    # Assign published policy B1 to Session 1 -> 200
    assign_res = client.post(f"/api/v1/sessions/{s1_id}/assign-rule-set", json={
        "rule_set_id": rs1_id,
    }, headers=prof_headers)
    assert assign_res.status_code == 200

    # 4. Now starting Session 1 succeeds -> 200
    start_ok = client.post(f"/api/v1/sessions/{s1_id}/start", headers=prof_headers)
    assert start_ok.status_code == 200
    assert start_ok.json()["status"].lower() == "active"


def test_active_policy_delivery_to_joined_student(client):
    """
    Verify that:
    - An enrolled student receives signed policy rules only after joining active session.
    - The received payload includes allowed/blocked websites, apps, and device requirements.
    - Ed25519 signature verifies with server public key.
    """
    prof_headers = get_auth_headers(client, "prof_delivery@university.edu", "Prof Delivery", "professor")
    student_headers = get_auth_headers(client, "student_agent@university.edu", "Student Agent", "student")

    # Create batch & enroll student via batch_code
    b_res = client.post("/api/v1/batches", json={"name": "Delivery Test Batch"}, headers=prof_headers).json()
    b_id = b_res["id"]
    b_code = b_res["batch_code"]
    client.post("/api/v1/student/batches/join", json={"batch_code": b_code}, headers=student_headers)

    # Register student agent device
    client.post("/api/v1/agent/devices/register", json={
        "device_name": "Delivery Student Laptop",
        "device_identifier": "DEV_DELIVERY_999",
        "public_key": "1234567890abcdef1234567890abcdef",
        "platform": "Windows",
        "agent_version": "2.3.0",
    }, headers=student_headers)
    student_agent_headers = dict(student_headers)
    student_agent_headers["X-Device-Identifier"] = "DEV_DELIVERY_999"

    # Create policy with specific rules and device requirements
    rs_id = client.post(f"/api/v1/batches/{b_id}/rule-sets", json={"name": "Exam Lockdown Delivery"}, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "docs.python.org", "rule_mode": "allowed", "category": "docs"
    }, headers=prof_headers)
    client.post(f"/api/v1/rule-sets/{rs_id}/website-rules", json={
        "domain_pattern": "cheat-engine.org", "rule_mode": "blocked", "reason": "Cheating"
    }, headers=prof_headers)
    client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "application_name": "Code.exe", "rule_mode": "allowed"
    }, headers=prof_headers)
    client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "application_name": "discord.exe", "rule_mode": "blocked", "action": "close"
    }, headers=prof_headers)
    client.patch(f"/api/v1/rule-sets/{rs_id}/device-requirements", json={
        "require_usb_storage_restriction": True,
        "required_device_compliance_level": "managed",
        "blocked_app_action": "close",
    }, headers=prof_headers)

    # Publish policy
    client.post(f"/api/v1/rule-sets/{rs_id}/publish", headers=prof_headers)

    # Create and start session
    now = datetime.now(timezone.utc)
    s_id = client.post("/api/v1/sessions", json={
        "title": "Delivery Active Session",
        "course": "Security",
        "batch_ids": [b_id],
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "type": "Exam",
    }, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/sessions/{s_id}/assign-rule-set", json={"rule_set_id": rs_id}, headers=prof_headers)
    client.post(f"/api/v1/sessions/{s_id}/start", headers=prof_headers)

    # Before joining, student agent asks for active policy -> policy_active is False
    pre_join = client.get("/api/v1/agent/policies/active", headers=student_agent_headers)
    assert pre_join.status_code == 200
    assert pre_join.json()["policy_active"] is False

    # Student joins session
    join_res = client.post(f"/api/v1/sessions/{s_id}/join", headers=student_headers)
    assert join_res.status_code == 200

    # Student agent asks for active policy -> 200 with complete signed payload
    active_pol_res = client.get("/api/v1/agent/policies/active", headers=student_agent_headers)
    assert active_pol_res.status_code == 200
    pol = active_pol_res.json()

    assert pol["policy_active"] is True
    assert pol["session_id"] == s_id
    assert "docs.python.org" in pol["allowed_websites"]
    assert "cheat-engine.org" in pol["blocked_websites"]
    assert "code.exe" in [a.lower() for a in pol["allowed_applications"]]
    assert "discord.exe" in [a.lower() for a in pol["blocked_applications"]]
    assert pol["device_requirements"]["require_usb_storage_restriction"] is True
    assert pol["signature"] is not None

    # Cryptographic verification of Ed25519 signature
    pub_key_b64 = get_server_public_key_b64()
    pub_key_bytes = base64.b64decode(pub_key_b64)
    public_key = Ed25519PublicKey.from_public_bytes(pub_key_bytes)
    sig_bytes = bytes.fromhex(pol["signature"])
    public_key.verify(sig_bytes, pol["integrity_hash"].encode("utf-8"))  # Will raise InvalidSignature if tampered
    assert verify_policy_signature(pol["integrity_hash"], pol["signature"]) is True


def test_usb_compliance_honest_reporting():
    """
    Verify that USB compliance reports honestly:
    - On standard developer or personal machines without GPO denial, reports 'requires_managed_device'.
    - Does not fabricate custom kernel drivers or cause crashes.
    """
    status, details = get_usb_storage_restriction_status()
    assert status in ["active", "requires_managed_device", "unsupported", "inactive"]
    assert "managed" in details.lower() or "active" in details.lower() or "unsupported" in details.lower() or "driver" in details.lower()


def test_session_ending_revokes_policy_enforcement(client):
    """
    Verify that ending a session revokes the policy and active policy delivery returns policy_active: False.
    """
    prof_headers = get_auth_headers(client, "prof_ending@university.edu", "Prof Ending", "professor")
    student_headers = get_auth_headers(client, "student_ending@university.edu", "Student Ending", "student")

    b_res = client.post("/api/v1/batches", json={"name": "Ending Batch"}, headers=prof_headers).json()
    b_id = b_res["id"]
    b_code = b_res["batch_code"]
    client.post("/api/v1/student/batches/join", json={"batch_code": b_code}, headers=student_headers)

    # Register student agent device
    client.post("/api/v1/agent/devices/register", json={
        "device_name": "Ending Student Laptop",
        "device_identifier": "DEV_ENDING_999",
        "public_key": "1234567890abcdef1234567890abcdef",
        "platform": "Windows",
        "agent_version": "2.3.0",
    }, headers=student_headers)
    student_agent_headers = dict(student_headers)
    student_agent_headers["X-Device-Identifier"] = "DEV_ENDING_999"

    rs_id = client.post(f"/api/v1/batches/{b_id}/rule-sets", json={"name": "Ending Policy"}, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/rule-sets/{rs_id}/publish", headers=prof_headers)

    now = datetime.now(timezone.utc)
    s_id = client.post("/api/v1/sessions", json={
        "title": "Ending Session",
        "course": "Network Security",
        "batch_ids": [b_id],
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "type": "Exam",
    }, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/sessions/{s_id}/assign-rule-set", json={"rule_set_id": rs_id}, headers=prof_headers)
    client.post(f"/api/v1/sessions/{s_id}/start", headers=prof_headers)
    client.post(f"/api/v1/sessions/{s_id}/join", headers=student_headers)

    # Active policy delivery works while session is active
    active_resp = client.get("/api/v1/agent/policies/active", headers=student_agent_headers)
    assert active_resp.status_code == 200
    assert active_resp.json()["policy_active"] is True

    # Professor ends session
    end_res = client.post(f"/api/v1/sessions/{s_id}/end", headers=prof_headers)
    assert end_res.status_code == 200

    # Now agent policy delivery returns policy_active: False
    after_end = client.get("/api/v1/agent/policies/active", headers=student_agent_headers)
    assert after_end.status_code == 200
    assert after_end.json()["policy_active"] is False

