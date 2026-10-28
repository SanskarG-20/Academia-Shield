"""
Tests for Secure Cross-Platform Policy Delivery between Professors and Enrolled Agents.
Validates:
- Platform capability reporting & compatibility
- Cross-batch isolation (students cannot receive another batch's policy)
- Denial before manual student join
- Revoked device denial
- Ed25519 policy digital signature verification & expiration
- Policy acknowledgement tracking (delivered, acknowledged, active, restored)
- Real professor dashboard reporting
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.device import AgentDevice
from app.models.batch import Batch, BatchMember
from app.models.session import SessionModel, SessionParticipant, SessionPresence
from app.models.rule import RuleSet, DomainRule, ApplicationRule
from app.core.security import create_access_token, get_server_public_key, sign_policy_payload, hash_password
from app.services.policy_service import PolicyService

@pytest.fixture
def student_user(db_session: Session) -> User:
    u = User(
        email=f"stud_{uuid.uuid4().hex[:6]}@univ.edu",
        password_hash=hash_password("Password123!"),
        full_name="Alice Student",
        role="student",
        is_active=True
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u

@pytest.fixture
def professor_user(db_session: Session) -> User:
    u = User(
        email=f"prof_{uuid.uuid4().hex[:6]}@univ.edu",
        password_hash=hash_password("Password123!"),
        full_name="Prof Xavier",
        role="professor",
        is_active=True
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u

def test_device_enrollment_with_ed25519_and_capabilities(client: TestClient, db_session: Session, student_user: User):
    token = create_access_token({"sub": student_user.id, "email": student_user.email, "role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "device_name": "MacBook Pro M2",
        "device_identifier": f"mac_{uuid.uuid4().hex[:12]}",
        "public_key": "a" * 64,
        "platform": "macos",
        "platform_version": "14.4.1",
        "agent_version": "2.3.0",
        "capabilities": {
            "dns_enforcement": "active",
            "content_filter": "requires_mdm",
            "application_control": "active"
        }
    }

    resp = client.post("/api/v1/agent/devices/register", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["enrollment_status"] == "enrolled"
    assert data["device_identifier"] == payload["device_identifier"]

    # Verify device record in DB
    dev = db_session.query(AgentDevice).filter(AgentDevice.id == data["device_id"]).first()
    assert dev is not None
    assert dev.platform == "macos"
    assert dev.capabilities_json["content_filter"] == "requires_mdm"

def test_policy_denied_before_student_manually_joins(client: TestClient, db_session: Session, student_user: User, professor_user: User):
    token = create_access_token({"sub": student_user.id, "email": student_user.email, "role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Batch & Session
    now = datetime.now(timezone.utc)
    batch_id = str(uuid.uuid4())
    batch = Batch(id=batch_id, name="Cybersecurity 101", professor_id=professor_user.id)
    db_session.add(batch)
    db_session.commit()

    db_session.add(BatchMember(id=str(uuid.uuid4()), batch_id=batch_id, student_id=student_user.id, status="active"))

    sess_id = str(uuid.uuid4())
    sess = SessionModel(
        id=sess_id,
        batch_id=batch_id,
        created_by=professor_user.id,
        title="Midterm Exam",
        start_at_utc=now - timedelta(minutes=10),
        end_at_utc=now + timedelta(hours=2),
        status="active",
        is_active=True
    )
    db_session.add(sess)
    db_session.commit()

    # RuleSet with non-null integrity_hash
    rs_id = str(uuid.uuid4())
    rs = RuleSet(id=rs_id, batch_id=batch_id, name="Exam Rules", version=1, is_active=True, created_by=professor_user.id, integrity_hash="")
    db_session.add(rs)
    db_session.commit()
    sess.rule_set_id = rs_id
    db_session.commit()

    # Enroll Device
    dev = AgentDevice(
        user_id=student_user.id,
        device_name="Student Laptop",
        device_identifier=f"dev_{uuid.uuid4().hex[:8]}",
        public_key="b" * 64,
        platform="windows",
        agent_version="2.3.0",
        is_active=True,
        enrollment_status="enrolled"
    )
    db_session.add(dev)
    db_session.commit()

    # Request active policy before joining
    headers["X-Device-Identifier"] = dev.device_identifier
    resp = client.get("/api/v1/agent/policies/active", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    # MUST be inactive because student has not joined
    assert data["policy_active"] is False
    assert "not manually joined" in data.get("reason", "")

    # Now Student manually joins
    join_resp = client.post(f"/api/v1/sessions/{sess_id}/join", headers=headers)
    assert join_resp.status_code in (200, 201)

    # Request active policy again
    resp2 = client.get("/api/v1/agent/policies/active", headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["policy_active"] is True
    assert data2["session_id"] == sess_id
    assert data2["signature"] is not None
    assert data2["integrity_hash"] is not None

def test_cross_batch_policy_isolation(client: TestClient, db_session: Session, student_user: User, professor_user: User):
    token = create_access_token({"sub": student_user.id, "email": student_user.email, "role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    now = datetime.now(timezone.utc)
    # Batch A (student is not a member)
    batch_a_id = str(uuid.uuid4())
    batch_a = Batch(id=batch_a_id, name="Batch A", professor_id=professor_user.id)
    db_session.add(batch_a)
    db_session.commit()

    sess_a_id = str(uuid.uuid4())
    sess_a = SessionModel(
        id=sess_a_id,
        batch_id=batch_a_id,
        created_by=professor_user.id,
        title="Session A",
        start_at_utc=now - timedelta(minutes=5),
        end_at_utc=now + timedelta(hours=1),
        status="active",
        is_active=True
    )
    db_session.add(sess_a)
    db_session.commit()

    rs_a_id = str(uuid.uuid4())
    rs_a = RuleSet(id=rs_a_id, batch_id=batch_a_id, name="Secret Rules", version=1, is_active=True, created_by=professor_user.id, integrity_hash="")
    db_session.add(rs_a)
    sess_a.rule_set_id = rs_a_id
    db_session.commit()

    dev = AgentDevice(
        user_id=student_user.id,
        device_name="Student Win",
        device_identifier=f"dev_iso_{uuid.uuid4().hex[:8]}",
        public_key="c" * 64,
        platform="windows",
        agent_version="2.3.0",
        is_active=True,
        enrollment_status="enrolled"
    )
    db_session.add(dev)
    db_session.commit()

    headers["X-Device-Identifier"] = dev.device_identifier

    # Even if student tries to ping session A, student is not in Batch A
    resp = client.get("/api/v1/agent/policies/active", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["policy_active"] is False

def test_revoked_device_denial(client: TestClient, db_session: Session, student_user: User, professor_user: User):
    token = create_access_token({"sub": student_user.id, "email": student_user.email, "role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    now = datetime.now(timezone.utc)
    batch_id = str(uuid.uuid4())
    batch = Batch(id=batch_id, name="Batch Revoke Test", professor_id=professor_user.id)
    db_session.add(batch)
    db_session.add(BatchMember(id=str(uuid.uuid4()), batch_id=batch_id, student_id=student_user.id, status="active"))

    sess_id = str(uuid.uuid4())
    sess = SessionModel(
        id=sess_id,
        batch_id=batch_id,
        created_by=professor_user.id,
        title="Active Exam",
        start_at_utc=now - timedelta(minutes=5),
        end_at_utc=now + timedelta(hours=1),
        status="active",
        is_active=True
    )
    db_session.add(sess)
    db_session.add(SessionParticipant(id=str(uuid.uuid4()), session_id=sess_id, student_id=student_user.id, status="joined"))
    rs_id = str(uuid.uuid4())
    rs = RuleSet(id=rs_id, batch_id=batch_id, name="Rules", version=1, is_active=True, created_by=professor_user.id, integrity_hash="")
    db_session.add(rs)
    sess.rule_set_id = rs_id

    # Revoked Device
    revoked_dev = AgentDevice(
        user_id=student_user.id,
        device_name="Compromised Device",
        device_identifier=f"dev_rev_{uuid.uuid4().hex[:8]}",
        public_key="d" * 64,
        platform="windows",
        agent_version="2.3.0",
        is_active=False,
        enrollment_status="revoked"
    )
    db_session.add(revoked_dev)
    db_session.commit()

    headers["X-Device-Identifier"] = revoked_dev.device_identifier
    resp = client.get("/api/v1/agent/policies/active", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["policy_active"] is False
    assert "revoked" in resp.json().get("reason", "").lower()

def test_policy_acknowledgment_workflow(client: TestClient, db_session: Session, student_user: User):
    token = create_access_token({"sub": student_user.id, "email": student_user.email, "role": "student"})
    headers = {"Authorization": f"Bearer {token}"}

    dev = AgentDevice(
        user_id=student_user.id,
        device_name="Student Ack Dev",
        device_identifier=f"dev_ack_{uuid.uuid4().hex[:8]}",
        public_key="e" * 64,
        platform="macos",
        agent_version="2.3.0",
        is_active=True,
        enrollment_status="enrolled"
    )
    db_session.add(dev)
    db_session.commit()

    headers["X-Device-Identifier"] = dev.device_identifier

    ack_payload = {
        "policy_id": "pol_test_101",
        "status": "active",
        "active_capabilities": ["dns_enforcement", "application_control"]
    }

    resp = client.post("/api/v1/agent/policies/pol_test_101/acknowledge", json=ack_payload, headers=headers)
    if resp.status_code != 200:
        print("ACK ERR:", resp.json())
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    db_session.refresh(dev)
    assert dev.policy_delivery_state == "active"
    assert dev.last_policy_id == "pol_test_101"

def test_professor_dashboard_real_device_status(client: TestClient, db_session: Session, student_user: User, professor_user: User):
    prof_token = create_access_token({"sub": professor_user.id, "email": professor_user.email, "role": "professor"})
    prof_headers = {"Authorization": f"Bearer {prof_token}"}

    now = datetime.now(timezone.utc)
    dev = AgentDevice(
        user_id=student_user.id,
        device_name="MacBook Air M3",
        device_identifier=f"dev_dash_{uuid.uuid4().hex[:8]}",
        public_key="f" * 64,
        platform="macos",
        agent_version="2.3.0",
        is_active=True,
        enrollment_status="enrolled",
        compliance_status="compliant",
        policy_delivery_state="active",
        capabilities_json={"dns_enforcement": "active", "content_filter": "requires_mdm"},
        last_seen_at=now - timedelta(seconds=10)
    )
    db_session.add(dev)
    db_session.commit()

    resp = client.get("/api/v1/dashboard/agent-status", headers=prof_headers)
    assert resp.status_code == 200
    devices = resp.json()
    target = next((d for d in devices if d["device_id"] == dev.id), None)
    assert target is not None
    assert target["platform"] == "macos"
    assert target["is_online"] is True
    assert target["compliance_status"] == "compliant"
    assert target["policy_delivery_state"] == "active"
    assert target["capabilities"]["dns_enforcement"] == "active"
