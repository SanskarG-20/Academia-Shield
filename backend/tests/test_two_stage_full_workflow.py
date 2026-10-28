"""
Two-Stage Academia Shield Full Workflow Integration Tests.
Verifies the complete lifecycle:
Stage 1: Real Website/Backend Control System
Stage 2: Downloadable Windows/macOS Local Agent Connection & Policy Enforcement
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.batch import Batch, BatchMember, generate_batch_code
from app.models.session import SessionModel, SessionParticipant, SessionPresence
from app.models.rule import RuleSet, DomainRule, ApplicationRule
from app.models.device import AgentDevice, DeviceEnrollmentToken, AgentPolicy
from app.core.security import (
    hash_password,
    create_access_token,
    create_device_access_token,
    hash_token,
    verify_policy_signature,
    get_server_public_key
)


@pytest.fixture
def auth_users(db_session: Session):
    now = datetime.now(timezone.utc)

    # Professor 1
    prof1 = User(
        email="prof1@institution.edu",
        password_hash=hash_password("ProfPassword123!"),
        full_name="Prof. Alan Turing",
        role="professor",
        is_active=True,
        institutional_id="PROF-001"
    )
    # Professor 2 (Unrelated)
    prof2 = User(
        email="prof2@institution.edu",
        password_hash=hash_password("ProfPassword123!"),
        full_name="Prof. Grace Hopper",
        role="professor",
        is_active=True,
        institutional_id="PROF-002"
    )
    # Student 1
    stud1 = User(
        email="student1@institution.edu",
        password_hash=hash_password("StudentPassword123!"),
        full_name="Alice Student",
        role="student",
        is_active=True,
        institutional_id="STU-001"
    )
    # Student 2 (In different batch)
    stud2 = User(
        email="student2@institution.edu",
        password_hash=hash_password("StudentPassword123!"),
        full_name="Bob Student",
        role="student",
        is_active=True,
        institutional_id="STU-002"
    )
    db_session.add_all([prof1, prof2, stud1, stud2])
    db_session.commit()


    tokens = {
        "prof1": create_access_token({"sub": prof1.id, "role": "professor"}),
        "prof2": create_access_token({"sub": prof2.id, "role": "professor"}),
        "stud1": create_access_token({"sub": stud1.id, "role": "student"}),
        "stud2": create_access_token({"sub": stud2.id, "role": "student"}),
    }
    users = {"prof1": prof1, "prof2": prof2, "stud1": stud1, "stud2": stud2}
    return users, tokens


def test_full_two_stage_connected_workflow(client: TestClient, db_session: Session, auth_users):
    """
    Comprehensive End-to-End Test:
    1. Student generates single-use enrollment token.
    2. Agent enrolls device with token.
    3. Student joins batch.
    4. Professor creates session with safe website/app rules.
    5. Policy is NOT accessible while session is Scheduled.
    6. Professor starts session -> Policy is STILL NOT accessible until student manually joins.
    7. Student joins active session -> Agent receives signed policy.
    8. Agent acknowledges policy and heartbeats -> Professor Live Monitor shows active status.
    9. Professor ends session -> Policy is revoked and agent returns to idle.
    """
    users, tokens = auth_users
    prof1, stud1 = users["prof1"], users["stud1"]
    prof1_token, stud1_token = tokens["prof1"], tokens["stud1"]

    # --------------------------------------------------------------------------
    # Step 1: Student checks device status -> NOT_ENROLLED
    # --------------------------------------------------------------------------
    res = client.get("/api/v1/agent/devices/me", headers={"Authorization": f"Bearer {stud1_token}"})
    assert res.status_code == 200
    assert res.json()["is_enrolled"] is False
    assert res.json()["agent_state"] == "NOT_ENROLLED"

    # --------------------------------------------------------------------------
    # Step 2: Student generates one-time enrollment token from Website
    # --------------------------------------------------------------------------
    res = client.post("/api/v1/agent/enrollment-token", headers={"Authorization": f"Bearer {stud1_token}"})
    assert res.status_code == 200
    token_data = res.json()
    enrollment_token = token_data["enrollment_token"]
    assert len(enrollment_token) == 8
    assert token_data["student_id"] == stud1.id

    # --------------------------------------------------------------------------
    # Step 3: Desktop Agent enrolls using single-use enrollment token
    # --------------------------------------------------------------------------
    agent_pubkey = "a" * 64
    enroll_payload = {
        "enrollment_token": enrollment_token,
        "device_identifier": "WIN-STUDENT-PC-01",
        "device_name": "Alice's Surface Pro",
        "public_key": agent_pubkey,
        "platform": "windows",
        "agent_version": "2.3.0"
    }
    enroll_res = client.post("/api/v1/agent/devices/enroll", json=enroll_payload)
    assert enroll_res.status_code == 200
    enroll_info = enroll_res.json()
    device_id = enroll_info["device_id"]
    agent_access_token = enroll_info["access_token"]
    assert enroll_info["user_id"] == stud1.id

    # Verify single-use: token cannot be reused
    res_reuse = client.post("/api/v1/agent/devices/enroll", json=enroll_payload)
    assert res_reuse.status_code == 400

    # Student checks device status again -> ENROLLED_IDLE
    res = client.get("/api/v1/agent/devices/me", headers={"Authorization": f"Bearer {stud1_token}"})
    assert res.status_code == 200
    assert res.json()["is_enrolled"] is True
    assert res.json()["is_online"] is True
    assert res.json()["agent_state"] == "ENROLLED_IDLE"

    # --------------------------------------------------------------------------
    # Step 4: Professor creates Batch and RuleSet
    # --------------------------------------------------------------------------
    batch_res = client.post(
        "/api/v1/batches",
        json={"name": "CS401 Distributed Systems", "department": "CE"},
        headers={"Authorization": f"Bearer {prof1_token}"}
    )
    assert batch_res.status_code == 201
    batch_id = batch_res.json()["id"]
    batch_code = batch_res.json()["code"]

    # Student joins batch with code
    join_batch_res = client.post(
        "/api/v1/batches/join",
        json={"code": batch_code},
        headers={"Authorization": f"Bearer {stud1_token}"}
    )
    assert join_batch_res.status_code == 200

    # Professor creates RuleSet with website & app rules
    ruleset_res = client.post(
        f"/api/v1/batches/{batch_id}/rule-sets",
        json={"name": "CS401 Exam Strict Rules", "enforcement_level": "strict"},
        headers={"Authorization": f"Bearer {prof1_token}"}
    )
    assert ruleset_res.status_code == 201
    ruleset_id = ruleset_res.json()["id"]


    # Add safe domain rule
    client.post(
        f"/api/v1/rule-sets/{ruleset_id}/domain-rules",
        json={"domain_pattern": "cheating-site.com", "action": "block"},
        headers={"Authorization": f"Bearer {prof1_token}"}
    )
    # Add safe app rule
    client.post(
        f"/api/v1/rule-sets/{ruleset_id}/application-rules",
        json={"executable_name": "discord.exe", "action": "close"},
        headers={"Authorization": f"Bearer {prof1_token}"}
    )

    # --------------------------------------------------------------------------
    # Step 5: Professor creates Session (Starts as Scheduled)
    # --------------------------------------------------------------------------
    now_utc = datetime.now(timezone.utc)
    session_res = client.post(
        "/api/v1/sessions",
        json={
            "title": "CS401 Midterm Exam",
            "batch_id": batch_id,
            "rule_set_id": ruleset_id,
            "start_time": (now_utc + timedelta(minutes=30)).isoformat(),
            "end_time": (now_utc + timedelta(hours=2)).isoformat()
        },
        headers={"Authorization": f"Bearer {prof1_token}"}
    )
    assert session_res.status_code == 201
    session_id = session_res.json()["id"]
    assert session_res.json()["status"].lower() == "scheduled"

    # Agent checks active policy -> NONE (Session is Scheduled)
    agent_headers = {"Authorization": f"Bearer {agent_access_token}", "X-Device-Identifier": "WIN-STUDENT-PC-01"}
    pol_res = client.get("/api/v1/agent/policies/active", headers=agent_headers)
    assert pol_res.status_code == 200
    assert pol_res.json()["policy_active"] is False

    # Student device status -> WAITING_FOR_STUDENT_JOIN / ENROLLED_IDLE
    status_res = client.get("/api/v1/agent/devices/me", headers={"Authorization": f"Bearer {stud1_token}"})
    assert status_res.status_code == 200

    # --------------------------------------------------------------------------
    # Step 6: Professor starts Session
    # --------------------------------------------------------------------------
    start_res = client.post(f"/api/v1/sessions/{session_id}/start", headers={"Authorization": f"Bearer {prof1_token}"})
    assert start_res.status_code == 200
    assert start_res.json()["status"].lower() == "active"

    # Agent checks active policy -> STILL INACTIVE because student hasn't clicked "Join Session"!
    pol_res2 = client.get("/api/v1/agent/policies/active", headers=agent_headers)
    assert pol_res2.status_code == 200
    assert pol_res2.json()["policy_active"] is False

    # --------------------------------------------------------------------------
    # Step 7: Student manually clicks "Join Session"
    # --------------------------------------------------------------------------
    join_res = client.post(f"/api/v1/student/sessions/{session_id}/join", headers={"Authorization": f"Bearer {stud1_token}"})
    assert join_res.status_code == 200

    # --------------------------------------------------------------------------
    # Step 8: Agent fetches active policy -> SUCCESS & SIGNED
    # --------------------------------------------------------------------------
    pol_res3 = client.get("/api/v1/agent/policies/active", headers=agent_headers)
    assert pol_res3.status_code == 200
    active_pol = pol_res3.json()
    assert active_pol["policy_active"] is True
    assert active_pol["session_id"] == session_id
    assert active_pol["signature"] is not None
    assert len(active_pol["domain_rules"]) >= 1
    assert len(active_pol["application_rules"]) >= 1

    # Verify Ed25519 digital signature
    sig_ok = verify_policy_signature(active_pol, active_pol["signature"])
    assert sig_ok is True

    # --------------------------------------------------------------------------
    # Step 9: Agent acknowledges policy & sends heartbeat
    # --------------------------------------------------------------------------
    ack_res = client.post(
        f"/api/v1/agent/policies/{session_id}/acknowledge",
        json={"status": "acknowledged", "policy_version": active_pol["policy_version"], "session_id": session_id},
        headers=agent_headers
    )
    assert ack_res.status_code == 200

    hb_res = client.post(
        "/api/v1/agent/heartbeat",
        json={
            "device_id": device_id,
            "device_identifier": "WIN-STUDENT-PC-01",
            "platform": "windows",
            "agent_version": "2.3.0",
            "agent_installed": True,
            "agent_service_running": True,
            "current_session_id": session_id,
            "dns_enforcement_status": "enforcing",
            "application_control_status": "enforcing"
        },
        headers=agent_headers
    )
    assert hb_res.status_code == 200

    # --------------------------------------------------------------------------
    # Step 10: Professor Live Monitor shows REAL live joined student & active policy
    # --------------------------------------------------------------------------
    live_res = client.get(f"/api/v1/professor/sessions/{session_id}/live", headers={"Authorization": f"Bearer {prof1_token}"})
    assert live_res.status_code == 200
    live_data = live_res.json()
    assert live_data["status"] == "active"
    assert live_data["joined_count"] == 1
    assert len(live_data["students"]) == 1
    student_item = live_data["students"][0]
    assert student_item["student_id"] == stud1.id
    assert student_item["name"] == stud1.full_name
    assert student_item["participant_status"] == "joined"

    # --------------------------------------------------------------------------
    # Step 11: Professor Ends Session -> Policy Revoked
    # --------------------------------------------------------------------------
    end_res = client.post(f"/api/v1/sessions/{session_id}/end", headers={"Authorization": f"Bearer {prof1_token}"})
    assert end_res.status_code == 200
    assert end_res.json()["status"].lower() == "ended"

    # Agent checks active policy -> Inactive / Revoked
    pol_ended = client.get("/api/v1/agent/policies/active", headers=agent_headers)
    assert pol_ended.status_code == 200
    assert pol_ended.json()["policy_active"] is False


    # Agent reports policy restored telemetry
    telemetry_res = client.post(
        "/api/v1/agent/telemetry/events",
        json=[
            {
                "event_type": "policy_restored",
                "session_id": session_id,
                "policy_version": active_pol["policy_version"],
                "action_requested": "restore_dns",
                "action_result": "success",
                "payload": {"details": "Restored original DNS and application policies"}
            }
        ],
        headers=agent_headers
    )
    assert telemetry_res.status_code in (200, 201)


def test_cross_tenant_professor_isolation(client: TestClient, db_session: Session, auth_users):
    """
    Ensure Professor 2 cannot start, view, or end Professor 1's sessions.
    """
    users, tokens = auth_users
    prof1, prof2, stud1 = users["prof1"], users["prof2"], users["stud1"]
    prof1_token, prof2_token = tokens["prof1"], tokens["prof2"]

    batch_res = client.post(
        "/api/v1/batches",
        json={"name": "Prof 1 Private Batch"},
        headers={"Authorization": f"Bearer {prof1_token}"}
    )
    batch_id = batch_res.json()["id"]

    sess_res = client.post(
        "/api/v1/sessions",
        json={"title": "Prof 1 Exam", "batch_id": batch_id},
        headers={"Authorization": f"Bearer {prof1_token}"}
    )
    session_id = sess_res.json()["id"]

    # Professor 2 tries to start Prof 1's session -> 403 Forbidden
    start_res = client.post(f"/api/v1/sessions/{session_id}/start", headers={"Authorization": f"Bearer {prof2_token}"})
    assert start_res.status_code == 403

    # Professor 2 tries to access Prof 1's Live Monitor -> 403 Forbidden
    live_res = client.get(f"/api/v1/professor/sessions/{session_id}/live", headers={"Authorization": f"Bearer {prof2_token}"})
    assert live_res.status_code == 403

    # Professor 2 tries to end Prof 1's session -> 403 Forbidden
    end_res = client.post(f"/api/v1/sessions/{session_id}/end", headers={"Authorization": f"Bearer {prof2_token}"})
    assert end_res.status_code == 403

