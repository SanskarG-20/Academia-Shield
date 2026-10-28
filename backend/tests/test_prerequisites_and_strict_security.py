"""
Comprehensive Tests for Academia Shield Prerequisites and Strict Security Architecture.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app.models.user import User
from app.models.batch import Batch, BatchMember
from app.models.session import SessionModel, SessionParticipant
from app.models.rule import RuleSet, DomainRule, ApplicationRule
from app.models.device import AgentDevice, DeviceComplianceReport
from app.core.security import (
    hash_password,
    create_access_token,
    verify_policy_signature,
    verify_release_manifest_signature,
    get_server_public_key
)

def create_user(db, email, role="student", name="Test User"):
    user = User(
        email=email,
        full_name=name,
        password_hash=hash_password("Password123!"),
        role=role,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def create_device(db, user_id, device_identifier="dev-001", platform="windows", compliance_level="personal"):
    device = AgentDevice(
        user_id=user_id,
        device_name="Test Laptop",
        device_identifier=device_identifier,
        public_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        platform=platform,
        platform_version="10.0.19045",
        agent_version="2.3.0",
        enrollment_status="enrolled",
        compliance_status="compliant",
        compliance_level=compliance_level,
        is_active=True,
        capabilities_json={"dns_enforcement": "active", "application_control": "active"}
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def test_cross_batch_access_denial(client, db_session):
    """Ensure student in Batch A cannot access sessions or policies of Batch B."""
    prof = create_user(db_session, "prof1@test.edu", role="professor", name="Prof One")
    student_a = create_user(db_session, "student_a@test.edu", role="student", name="Student A")
    
    # Professor creates Batch A and Batch B
    batch_a = Batch(professor_id=prof.id, name="CS101", batch_code="CS101A")
    batch_b = Batch(professor_id=prof.id, name="CS102", batch_code="CS102B")
    db_session.add_all([batch_a, batch_b])
    db_session.commit()

    # Student joins Batch A only
    member_a = BatchMember(batch_id=batch_a.id, student_id=student_a.id)
    db_session.add(member_a)
    db_session.commit()

    # Active session created in Batch B
    now = datetime.now(timezone.utc)
    session_b = SessionModel(
        batch_id=batch_b.id,
        created_by=prof.id,
        title="Session Batch B",
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=5),
        end_at_utc=now + timedelta(minutes=50)
    )
    db_session.add(session_b)
    db_session.commit()

    rule_set_b = RuleSet(
        batch_id=batch_b.id,
        name="Batch B Rules",
        version=1,
        is_active=True,
        created_by=prof.id,
        integrity_hash="abc123hash"
    )
    db_session.add(rule_set_b)
    db_session.commit()

    # Student registers device
    device_a = create_device(db_session, student_a.id, "dev-a")

    # Student A queries active policy
    token_a = create_access_token({"sub": student_a.id, "email": student_a.email, "role": "student"})
    res = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token_a}", "X-Device-Identifier": "dev-a"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["policy_active"] is False
    assert "not manually joined" in data["reason"].lower() or "no active" in data["reason"].lower()


def test_policy_denial_before_manual_session_join(client, db_session):
    """Verify policy is never delivered before student manually joins the active session."""
    prof = create_user(db_session, "prof2@test.edu", role="professor", name="Prof Two")
    student = create_user(db_session, "student2@test.edu", role="student", name="Student Two")
    
    batch = Batch(professor_id=prof.id, name="Math201", batch_code="MTH201")
    db_session.add(batch)
    db_session.commit()

    member = BatchMember(batch_id=batch.id, student_id=student.id)
    db_session.add(member)
    db_session.commit()

    now = datetime.now(timezone.utc)
    session = SessionModel(
        batch_id=batch.id,
        created_by=prof.id,
        title="Math Exam",
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=2),
        end_at_utc=now + timedelta(minutes=60)
    )
    db_session.add(session)
    db_session.commit()

    rule_set = RuleSet(
        batch_id=batch.id,
        name="Math Exam Rules",
        version=1,
        is_active=True,
        created_by=prof.id,
        integrity_hash="hashmath"
    )
    db_session.add(rule_set)
    db_session.commit()

    device = create_device(db_session, student.id, "dev-student2")
    token = create_access_token({"sub": student.id, "email": student.email, "role": "student"})

    # Prior to manual join, policy must be inactive
    res = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token}", "X-Device-Identifier": "dev-student2"}
    )
    assert res.status_code == 200
    assert res.json()["policy_active"] is False
    assert "manually joined" in res.json()["reason"].lower()

    # Student manually joins session
    join_res = client.post(
        f"/api/v1/sessions/{session.id}/join",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert join_res.status_code == 200

    # Policy should now be active
    res_after = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token}", "X-Device-Identifier": "dev-student2"}
    )
    assert res_after.status_code == 200
    assert res_after.json()["policy_active"] is True
    assert res_after.json()["signature"] is not None


def test_device_enrollment_and_revocation(client, db_session):
    """Test device registration, policy retrieval, and subsequent revocation."""
    student = create_user(db_session, "student3@test.edu", role="student", name="Student Three")
    token = create_access_token({"sub": student.id, "email": student.email, "role": "student"})

    # 1. Register device
    reg_payload = {
        "device_name": "Student Surface",
        "device_identifier": "surface-12345",
        "public_key": "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
        "platform": "windows",
        "platform_version": "10.0.22621",
        "agent_version": "2.3.0",
        "capabilities": {"dns_enforcement": "active"}
    }
    reg_res = client.post(
        "/api/v1/agent/devices/register",
        json=reg_payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert reg_res.status_code == 201
    device_id = reg_res.json()["device_id"]

    # 2. Revoke device
    revoke_res = client.post(
        f"/api/v1/agent/devices/{device_id}/revoke",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["enrollment_status"] == "revoked"
    assert revoke_res.json()["is_active"] is False

    # 3. Policy check after revocation
    pol_res = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token}", "X-Device-Identifier": "surface-12345"}
    )
    assert pol_res.status_code == 200
    assert pol_res.json()["policy_active"] is False
    assert "revoked" in pol_res.json()["reason"].lower()


def test_invalid_policy_signature_rejection(client, db_session):
    """Verify Ed25519 signature validation rejects tampered payloads."""
    prof = create_user(db_session, "prof4@test.edu", role="professor", name="Prof Four")
    student = create_user(db_session, "student4@test.edu", role="student", name="Student Four")
    
    batch = Batch(professor_id=prof.id, name="CS301", batch_code="CS301C")
    db_session.add(batch)
    db_session.commit()

    member = BatchMember(batch_id=batch.id, student_id=student.id)
    db_session.add(member)
    db_session.commit()

    now = datetime.now(timezone.utc)
    session = SessionModel(
        batch_id=batch.id,
        created_by=prof.id,
        title="Session Signed",
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=5),
        end_at_utc=now + timedelta(minutes=55)
    )
    db_session.add(session)
    db_session.commit()

    rule_set = RuleSet(
        batch_id=batch.id,
        name="Signed Rules",
        version=1,
        is_active=True,
        created_by=prof.id,
        integrity_hash="hashsigned"
    )
    db_session.add(rule_set)
    db_session.commit()

    # Add domain rule
    domain_rule = DomainRule(rule_set_id=rule_set.id, domain_pattern="facebook.com", action="block")
    db_session.add(domain_rule)
    db_session.commit()

    participant = SessionParticipant(session_id=session.id, student_id=student.id, status="joined")
    db_session.add(participant)
    db_session.commit()

    device = create_device(db_session, student.id, "dev-signed")
    token = create_access_token({"sub": student.id, "email": student.email, "role": "student"})

    res = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token}", "X-Device-Identifier": "dev-signed"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["policy_active"] is True
    
    integrity_hash = data["integrity_hash"]
    signature = data["signature"]
    assert signature is not None

    # Valid signature check
    assert verify_policy_signature(integrity_hash, signature) is True

    # Tampered signature check (tampering 1 character in hash)
    tampered_hash = integrity_hash[:-1] + ("0" if integrity_hash[-1] != "0" else "1")
    assert verify_policy_signature(tampered_hash, signature) is False


def test_expired_policy_rejection(client, db_session):
    """Verify expired rule set is rejected with policy_active = False."""
    prof = create_user(db_session, "prof5@test.edu", role="professor", name="Prof Five")
    student = create_user(db_session, "student5@test.edu", role="student", name="Student Five")
    
    batch = Batch(professor_id=prof.id, name="CS501", batch_code="CS501E")
    db_session.add(batch)
    db_session.commit()

    member = BatchMember(batch_id=batch.id, student_id=student.id)
    db_session.add(member)
    db_session.commit()

    now = datetime.now(timezone.utc)
    session = SessionModel(
        batch_id=batch.id,
        created_by=prof.id,
        title="Session Expired",
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=5),
        end_at_utc=now + timedelta(minutes=55)
    )
    db_session.add(session)
    db_session.commit()

    # Rule set expired 10 minutes ago
    rule_set = RuleSet(
        batch_id=batch.id,
        name="Expired Rules",
        version=1,
        is_active=True,
        created_by=prof.id,
        expires_at=now - timedelta(minutes=10),
        integrity_hash="hashexp"
    )
    db_session.add(rule_set)
    db_session.commit()

    participant = SessionParticipant(session_id=session.id, student_id=student.id, status="joined")
    db_session.add(participant)
    db_session.commit()

    device = create_device(db_session, student.id, "dev-exp")
    token = create_access_token({"sub": student.id, "email": student.email, "role": "student"})

    res = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token}", "X-Device-Identifier": "dev-exp"}
    )
    assert res.status_code == 200
    assert res.json()["policy_active"] is False
    assert "expired" in res.json()["reason"].lower()


def test_unsupported_platform_capability_rejection(client, db_session):
    """Verify device reporting unsupported capabilities is rejected."""
    prof = create_user(db_session, "prof6@test.edu", role="professor", name="Prof Six")
    student = create_user(db_session, "student6@test.edu", role="student", name="Student Six")
    
    batch = Batch(professor_id=prof.id, name="CS601", batch_code="CS601F")
    db_session.add(batch)
    db_session.commit()

    member = BatchMember(batch_id=batch.id, student_id=student.id)
    db_session.add(member)
    db_session.commit()

    now = datetime.now(timezone.utc)
    session = SessionModel(
        batch_id=batch.id,
        created_by=prof.id,
        title="Session Caps",
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=5),
        end_at_utc=now + timedelta(minutes=55)
    )
    db_session.add(session)
    db_session.commit()

    rule_set = RuleSet(
        batch_id=batch.id,
        name="Caps Rules",
        version=1,
        is_active=True,
        created_by=prof.id,
        integrity_hash="hashcaps"
    )
    db_session.add(rule_set)
    db_session.commit()

    participant = SessionParticipant(session_id=session.id, student_id=student.id, status="joined")
    db_session.add(participant)
    db_session.commit()

    # Device with explicit unsupported capability flag
    device = create_device(db_session, student.id, "dev-unsupported")
    device.capabilities_json = {"unsupported_capability": True}
    db_session.commit()

    token = create_access_token({"sub": student.id, "email": student.email, "role": "student"})
    res = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token}", "X-Device-Identifier": "dev-unsupported"}
    )
    assert res.status_code == 200
    assert res.json()["policy_active"] is False
    assert "does not support required enforcement capabilities" in res.json()["reason"]


def test_strict_session_denied_for_non_compliant_device(client, db_session):
    """Verify personal / non-managed device is rejected when strict compliance is required."""
    prof = create_user(db_session, "prof7@test.edu", role="professor", name="Prof Seven")
    student = create_user(db_session, "student7@test.edu", role="student", name="Student Seven")
    
    batch = Batch(professor_id=prof.id, name="CS701", batch_code="CS701G")
    db_session.add(batch)
    db_session.commit()

    member = BatchMember(batch_id=batch.id, student_id=student.id)
    db_session.add(member)
    db_session.commit()

    now = datetime.now(timezone.utc)
    session = SessionModel(
        batch_id=batch.id,
        created_by=prof.id,
        title="Strict Exam",
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=5),
        end_at_utc=now + timedelta(minutes=55)
    )
    db_session.add(session)
    db_session.commit()

    rule_set = RuleSet(
        batch_id=batch.id,
        name="Strict Exam Rules",
        version=1,
        is_active=True,
        created_by=prof.id,
        integrity_hash="hashstrict"
    )
    # Set required compliance to strict
    rule_set.compliance_level = "strict"
    db_session.add(rule_set)
    db_session.commit()

    participant = SessionParticipant(session_id=session.id, student_id=student.id, status="joined")
    db_session.add(participant)
    db_session.commit()

    # Personal device (unmanaged)
    device = create_device(db_session, student.id, "dev-personal", compliance_level="personal")
    token = create_access_token({"sub": student.id, "email": student.email, "role": "student"})

    res = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token}", "X-Device-Identifier": "dev-personal"}
    )
    assert res.status_code == 200
    assert res.json()["policy_active"] is False
    assert "strict compliance" in res.json()["reason"].lower()

    # Now upgrade device to strict managed compliance
    device.compliance_level = "strict"
    db_session.commit()

    res_strict = client.get(
        "/api/v1/agent/policies/active",
        headers={"Authorization": f"Bearer {token}", "X-Device-Identifier": "dev-personal"}
    )
    assert res_strict.status_code == 200
    assert res_strict.json()["policy_active"] is True


def test_no_endpoint_accepts_arbitrary_command_payloads(client, db_session):
    """Verify application and domain rule APIs strictly reject shells, scripts, and injection syntax."""
    prof = create_user(db_session, "prof8@test.edu", role="professor", name="Prof Eight")
    token = create_access_token({"sub": prof.id, "email": prof.email, "role": "professor"})

    batch = Batch(professor_id=prof.id, name="CS801", batch_code="CS801H")
    db_session.add(batch)
    db_session.commit()

    rule_set = RuleSet(
        batch_id=batch.id,
        name="Safe Rules",
        version=1,
        is_active=True,
        created_by=prof.id,
        integrity_hash="safehash"
    )
    db_session.add(rule_set)
    db_session.commit()

    # 1. Reject shell command in application rule
    res1 = client.post(
        f"/api/v1/rule-sets/{rule_set.id}/application-rules",
        json={"executable_name": "cmd.exe", "action": "close"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res1.status_code in (400, 422)

    # 2. Reject powershell script
    res2 = client.post(
        f"/api/v1/rule-sets/{rule_set.id}/application-rules",
        json={"executable_name": "attack.ps1", "action": "close"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res2.status_code in (400, 422)

    # 3. Reject command injection characters
    res3 = client.post(
        f"/api/v1/rule-sets/{rule_set.id}/application-rules",
        json={"executable_name": "calc.exe; rm -rf /", "action": "close"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res3.status_code in (400, 422)

    # 4. Reject invalid actions (e.g. exec / run)
    res4 = client.post(
        f"/api/v1/rule-sets/{rule_set.id}/application-rules",
        json={"executable_name": "spotify.exe", "action": "execute"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res4.status_code in (400, 422)

    # 5. Reject command injection in domain rules
    res5 = client.post(
        f"/api/v1/rule-sets/{rule_set.id}/domain-rules",
        json={"domain_pattern": "google.com; cat /etc/passwd", "action": "block"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res5.status_code in (400, 422)





def test_release_manifest_endpoints(client):
    """Verify signed release manifest endpoints for Windows and macOS."""
    # 1. Latest releases
    res = client.get("/api/v1/agent/releases/latest")
    assert res.status_code == 200
    data = res.json()
    assert "windows" in data["releases"]
    assert "macos" in data["releases"]
    
    win_rel = data["releases"]["windows"]
    assert win_rel["platform"] == "windows"
    assert win_rel["download_url"].endswith(".exe")
    assert len(win_rel["sha256"]) == 64
    assert win_rel["signature"] is not None
    assert verify_release_manifest_signature(win_rel, win_rel["signature"]) is True

    mac_rel = data["releases"]["macos"]
    assert mac_rel["platform"] == "macos"
    assert mac_rel["download_url"].endswith(".pkg")
    assert len(mac_rel["sha256"]) == 64
    assert mac_rel["signature"] is not None
    assert verify_release_manifest_signature(mac_rel, mac_rel["signature"]) is True

    # 2. Specific version manifest
    ver_res = client.get("/api/v1/agent/releases/2.3.0/manifest?platform=windows")
    assert ver_res.status_code == 200
    ver_data = ver_res.json()
    assert ver_data["version"] == "2.3.0"
    assert ver_data["platform"] == "windows"
    assert verify_release_manifest_signature(ver_data, ver_data["signature"]) is True

    # 3. Verification key endpoint
    key_res = client.get("/api/v1/agent/verification-key")
    assert key_res.status_code == 200
    assert key_res.json()["public_key"] == get_server_public_key()
    assert key_res.json()["algorithm"] == "Ed25519"
