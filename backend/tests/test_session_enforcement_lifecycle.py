"""
Comprehensive tests for Session Enforcement Lifecycle & Presence Decoupling.
Rules:
1. Professor starts session -> Student joins active session -> policy enforcement starts on student's enrolled device.
2. Student leaves website portal -> status becomes 'left', but policy enforcement MUST remain active.
3. Agent policy endpoint /api/v1/agent/policies/active continues to return active policy after student leaves portal.
4. Professor ending session (/api/v1/sessions/{id}/end) revokes all policy assignments and ends enforcement.
5. Emergency stop (/api/v1/sessions/{id}/emergency-stop) immediately halts restrictions and audits the reason.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.models.user import User
from app.models.batch import Batch, BatchMember
from app.models.rule import RuleSet
from app.models.session import SessionModel, SessionParticipant
from app.models.device import AgentDevice, AgentPolicyAssignment, AgentPolicy
from app.models.audit_log import AuditLog
from app.core.security import hash_password, create_access_token, create_device_access_token


def test_session_enforcement_persists_after_student_leaves_portal(client, db_session):
    now = datetime.now(timezone.utc)

    # 1. Create Professor and Student
    prof = User(
        email="prof_enforce@test.edu",
        password_hash=hash_password("Secret123!"),
        full_name="Professor Enforce",
        role="professor",
        is_active=True
    )
    student = User(
        email="student_enforce@test.edu",
        password_hash=hash_password("Secret123!"),
        full_name="Student Enforce",
        role="student",
        is_active=True
    )
    db_session.add_all([prof, student])
    db_session.commit()

    prof_token = create_access_token({"sub": prof.id, "role": "professor", "email": "prof_enforce@test.edu"})
    student_token = create_access_token({"sub": student.id, "role": "student", "email": "student_enforce@test.edu"})

    # 2. Create Batch & enroll Student
    batch = Batch(
        name="Network Security Lab",
        batch_code="NETSEC1",
        professor_id=prof.id,
        is_active=True
    )
    db_session.add(batch)
    db_session.commit()

    bm = BatchMember(batch_id=batch.id, student_id=student.id, status="active")
    db_session.add(bm)

    # 3. Create RuleSet with blocked domains & apps
    from app.models.rule import DomainRule, ApplicationRule
    ruleset = RuleSet(
        name="Exam Strict Rules",
        created_by=prof.id,
        batch_id=batch.id,
        integrity_hash="a" * 64,
        version=1,
        is_active=True
    )
    db_session.add(ruleset)
    db_session.commit()

    dom1 = DomainRule(rule_set_id=ruleset.id, domain_pattern="instagram.com", action="block")
    dom2 = DomainRule(rule_set_id=ruleset.id, domain_pattern="reddit.com", action="block")
    app1 = ApplicationRule(rule_set_id=ruleset.id, executable_name="discord.exe", action="close")
    app2 = ApplicationRule(rule_set_id=ruleset.id, executable_name="spotify.exe", action="close")
    db_session.add_all([dom1, dom2, app1, app2])
    db_session.commit()

    # 4. Enroll Student Device
    device = AgentDevice(
        user_id=student.id,
        device_name="Student MacBook Pro",
        device_identifier="DEV-ENFORCE-001",
        public_key="ed25519_pub_key_001",
        platform="windows",
        agent_version="2.3.0",
        enrollment_status="enrolled",
        is_active=True,
        last_seen_at=now
    )
    db_session.add(device)
    db_session.commit()

    device_token = create_device_access_token(device.id, student.id, "windows")

    # 5. Create and Start Active Session
    session_obj = SessionModel(
        title="Midterm Exam",
        batch_id=batch.id,
        created_by=prof.id,
        rule_set_id=ruleset.id,
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=5),
        end_at_utc=now + timedelta(hours=2),
        started_at=now - timedelta(minutes=5),
        session_code="SEC101",
        policy_version=1
    )
    db_session.add(session_obj)
    db_session.commit()

    # 6. Student Joins Session
    join_resp = client.post(
        f"/api/v1/student/sessions/{session_obj.id}/join",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert join_resp.status_code == 200, join_resp.text
    join_data = join_resp.json()
    assert join_data["joined"] is True
    assert "Protection will remain active" in join_data["message"]

    # Verify AgentPolicyAssignment created as active
    assignment = db_session.query(AgentPolicyAssignment).filter(
        AgentPolicyAssignment.session_id == session_obj.id,
        AgentPolicyAssignment.student_id == student.id
    ).first()
    assert assignment is not None
    assert assignment.state == "active"

    # 7. Agent queries /api/v1/agent/policies/active -> Policy Active = True
    pol_resp = client.get(
        "/api/v1/agent/policies/active",
        headers={
            "Authorization": f"Bearer {device_token}",
            "X-Device-Identifier": "DEV-ENFORCE-001"
        }
    )
    assert pol_resp.status_code == 200, pol_resp.text
    pol_data = pol_resp.json()
    assert pol_data["policy_active"] is True
    domain_patterns = [d["domain_pattern"] for d in pol_data.get("domain_rules", [])]
    app_names = [a["executable_name"] for a in pol_data.get("application_rules", [])]
    assert "instagram.com" in domain_patterns
    assert "discord.exe" in app_names

    # 8. Student Leaves Session Portal via /leave
    leave_resp = client.post(
        f"/api/v1/student/sessions/{session_obj.id}/leave",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert leave_resp.status_code == 200, leave_resp.text
    leave_data = leave_resp.json()
    assert "Device protection remains active" in leave_data["message"]

    # Check participant status is 'left'
    participant = db_session.query(SessionParticipant).filter(
        SessionParticipant.session_id == session_obj.id,
        SessionParticipant.student_id == student.id
    ).first()
    assert participant.status == "left"
    assert participant.left_at is not None

    # CRITICAL CHECK: AgentPolicyAssignment MUST STILL BE ACTIVE!
    db_session.refresh(assignment)
    assert assignment.state == "active"

    # CRITICAL CHECK: Agent queries active policy again -> STILL ACTIVE!
    pol_resp2 = client.get(
        "/api/v1/agent/policies/active",
        headers={
            "Authorization": f"Bearer {device_token}",
            "X-Device-Identifier": "DEV-ENFORCE-001"
        }
    )
    assert pol_resp2.status_code == 200, pol_resp2.text
    pol_data2 = pol_resp2.json()
    assert pol_data2["policy_active"] is True
    assert pol_data2["session_id"] == session_obj.id

    # 9. Professor Live Monitor checks status: student shows Left Portal, but Enforcing count is 1
    mon_resp = client.get(
        f"/api/v1/professor/sessions/{session_obj.id}/live",
        headers={"Authorization": f"Bearer {prof_token}"}
    )
    assert mon_resp.status_code == 200, mon_resp.text
    mon_data = mon_resp.json()
    assert mon_data["enforcing_count"] >= 1
    student_mon = next(s for s in mon_data["students"] if s["student_id"] == student.id)
    assert student_mon["participant_status"] == "left"
    assert student_mon["enforcement_status"] == "active"

    # 10. Professor Ends Session (/api/v1/sessions/{session_id}/end)
    end_resp = client.post(
        f"/api/v1/sessions/{session_obj.id}/end",
        headers={"Authorization": f"Bearer {prof_token}"}
    )
    assert end_resp.status_code == 200, end_resp.text
    assert end_resp.json()["status"] == "ended"

    # Assignment state is now revoked
    db_session.expire_all()
    updated_assignment = db_session.query(AgentPolicyAssignment).filter(
        AgentPolicyAssignment.id == assignment.id
    ).first()
    assert updated_assignment.state == "revoked"

    # CRITICAL CHECK: Agent queries active policy -> Policy Active = False
    pol_resp3 = client.get(
        "/api/v1/agent/policies/active",
        headers={
            "Authorization": f"Bearer {device_token}",
            "X-Device-Identifier": "DEV-ENFORCE-001"
        }
    )
    assert pol_resp3.status_code == 200
    assert pol_resp3.json()["policy_active"] is False


def test_emergency_stop_session(client, db_session):
    now = datetime.now(timezone.utc)

    # Setup prof, student, batch, session
    prof = User(email="prof_emg@test.edu", password_hash=hash_password("Pass123!"), full_name="Prof Emergency", role="professor", is_active=True)
    student = User(email="student_emg@test.edu", password_hash=hash_password("Pass123!"), full_name="Student Emergency", role="student", is_active=True)
    db_session.add_all([prof, student])
    db_session.commit()

    prof_token = create_access_token({"sub": prof.id, "role": "professor", "email": "prof_emg@test.edu"})
    student_token = create_access_token({"sub": student.id, "role": "student", "email": "student_emg@test.edu"})

    batch = Batch(name="Emergency Test Batch", batch_code="EMGBAT", professor_id=prof.id, is_active=True)
    db_session.add(batch)
    db_session.commit()
    db_session.add(BatchMember(batch_id=batch.id, student_id=student.id, status="active"))

    from app.models.rule import DomainRule
    ruleset = RuleSet(name="Test Rules", created_by=prof.id, batch_id=batch.id, integrity_hash="b" * 64, version=1, is_active=True)
    db_session.add(ruleset)
    db_session.commit()
    db_session.add(DomainRule(rule_set_id=ruleset.id, domain_pattern="badsite.com", action="block"))
    db_session.commit()

    device = AgentDevice(user_id=student.id, device_name="Test Rig", device_identifier="EMG-DEV-01", public_key="pubkey", platform="windows", agent_version="2.3.0", enrollment_status="enrolled", is_active=True)
    db_session.add(device)
    db_session.commit()

    session_obj = SessionModel(
        title="Fire Drill Exam",
        batch_id=batch.id,
        created_by=prof.id,
        rule_set_id=ruleset.id,
        status="active",
        is_active=True,
        start_at_utc=now,
        end_at_utc=now + timedelta(hours=1),
        started_at=now,
        policy_version=1
    )
    db_session.add(session_obj)
    db_session.commit()

    # Student joins
    client.post(f"/api/v1/student/sessions/{session_obj.id}/join", headers={"Authorization": f"Bearer {student_token}"})

    # Professor triggers Emergency Stop
    emg_resp = client.post(
        f"/api/v1/sessions/{session_obj.id}/emergency-stop",
        json={"reason": "Campus network fire drill evacuation"},
        headers={"Authorization": f"Bearer {prof_token}"}
    )
    assert emg_resp.status_code == 200, emg_resp.text
    session_data = emg_resp.json()
    assert session_data["status"] == "ended"

    db_session.refresh(session_obj)
    assert session_obj.emergency_stopped_at is not None
    assert session_obj.emergency_stop_reason == "Campus network fire drill evacuation"
    assert session_obj.emergency_stopped_by == prof.id

    # Verify audit log exists
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == session_obj.id,
        AuditLog.action == "EMERGENCY_STOP"
    ).first()
    assert audit is not None
    assert "fire drill" in audit.metadata_json["details"]
