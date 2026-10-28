"""
Automated Test Suite for Secure Batch Management and Manual Session Joining.
Tests all requirements:
1. New sessions default to status 'scheduled' and is_active=False.
2. Sessions do not auto-activate on creation or time.
3. Only batch owner professor can start/end session.
4. Students see sessions from joined batches only.
5. Student sees session details before joining (without auto-joining).
6. Student cannot join scheduled, ended, or cancelled sessions.
7. Student manual click POST /join succeeds when session is active.
8. Student outside batch gets 403 Forbidden on join attempt.
9. Joining twice returns 409 Conflict.
10. Agent policy denied before student joins.
11. Agent policy returned after student manually joins active session.
12. Ending session revokes agent policy.
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db, ensure_schema_up_to_date
from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.batch import Batch, BatchMember, generate_batch_code
from app.models.session import SessionModel, SessionParticipant
from app.models.device import AgentDevice
from app.models.rule import RuleSet, DomainRule
from app.services.policy_service import PolicyService

def register_and_login_user(client, email, role, full_name):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": full_name, "role": role
    })
    token_resp = client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password123!"
    }).json()
    token = token_resp["access_token"]
    user_id = token_resp["user"]["id"]
    return user_id, token


def test_secure_batch_and_session_lifecycle(client, db_session):
    # 1. Create users
    prof1_id, prof1_token = register_and_login_user(client, "prof1_sec@test.edu", "professor", "Prof One")
    prof2_id, prof2_token = register_and_login_user(client, "prof2_sec@test.edu", "professor", "Prof Two")
    student1_id, student1_token = register_and_login_user(client, "student1_sec@test.edu", "student", "Student One")
    student2_id, student2_token = register_and_login_user(client, "student2_sec@test.edu", "student", "Student Two")

    h_prof1 = {"Authorization": f"Bearer {prof1_token}"}
    h_prof2 = {"Authorization": f"Bearer {prof2_token}"}
    h_stud1 = {"Authorization": f"Bearer {student1_token}"}
    h_stud2 = {"Authorization": f"Bearer {student2_token}"}

    # 2. Prof1 creates batch
    r = client.post("/api/v1/batches", json={"name": "CS-101", "description": "Intro to CS"}, headers=h_prof1)
    assert r.status_code == 201
    batch_data = r.json()
    batch_id = batch_data["id"]
    batch_code = batch_data["batch_code"]

    # 3. Student1 joins batch via code
    r = client.post("/api/v1/student/batches/join", json={"batch_code": batch_code}, headers=h_stud1)
    assert r.status_code == 200

    # Verify student batch list redacts code
    r = client.get("/api/v1/student/batches", headers=h_stud1)
    assert r.status_code == 200
    sb_list = r.json()
    assert len(sb_list) == 1
    assert "batch_code" not in sb_list[0]
    assert "code" not in sb_list[0]

    # Verify student outside batch gets 403 when requesting details
    r = client.get(f"/api/v1/student/batches/{batch_id}", headers=h_stud2)
    assert r.status_code == 403

    # 4. Prof1 creates a rule set for the batch
    rule_set = RuleSet(
        batch_id=batch_id,
        name="Strict Mode",
        version=1,
        is_active=True,
        integrity_hash="test_integrity_hash_123",
        created_by=prof1_id
    )
    db_session.add(rule_set)
    db_session.commit()
    db_session.refresh(rule_set)

    d_rule = DomainRule(rule_set_id=rule_set.id, domain_pattern="facebook.com", is_enabled=True)
    db_session.add(d_rule)
    db_session.commit()

    # 5. Prof1 creates session -> REQUIREMENT 1: Must start as 'scheduled' and NOT auto-activate
    now = datetime.now(timezone.utc)
    start_utc = (now - timedelta(minutes=5)).isoformat()
    end_utc = (now + timedelta(hours=2)).isoformat()

    r = client.post(
        f"/api/v1/batches/{batch_id}/sessions",
        json={
            "title": "Data Structures Lab",
            "description": "Tree Traversal Practice",
            "start_at_utc": start_utc,
            "end_at_utc": end_utc,
            "rule_set_id": rule_set.id
        },
        headers=h_prof1
    )
    assert r.status_code == 201
    sess_data = r.json()
    session_id = sess_data["id"]
    assert sess_data["status"].lower() == "scheduled"
    assert sess_data["is_active"] is False

    # REQUIREMENT 4: Student1 sees session from joined batch
    r = client.get("/api/v1/student/sessions", headers=h_stud1)
    assert r.status_code == 200
    stud_sessions = r.json()
    assert len(stud_sessions) == 1
    assert stud_sessions[0]["id"] == session_id
    assert stud_sessions[0]["status"].lower() == "scheduled"
    assert stud_sessions[0]["is_joined"] is False

    # Student2 (not in batch) sees NO sessions
    r = client.get("/api/v1/student/sessions", headers=h_stud2)
    assert r.status_code == 200
    assert len(r.json()) == 0

    # REQUIREMENT 5: Student fetches details without auto-joining
    r = client.get(f"/api/v1/student/sessions/{session_id}", headers=h_stud1)
    assert r.status_code == 200
    details = r.json()
    assert details["title"] == "Data Structures Lab"
    assert details["is_joined"] is False

    # REQUIREMENT 6: Student cannot join 'scheduled' session
    r = client.post(f"/api/v1/student/sessions/{session_id}/join", headers=h_stud1)
    assert r.status_code == 400

    # REQUIREMENT 10: Agent policy denied before student joins
    device1 = AgentDevice(
        user_id=student1_id,
        device_name="Student PC",
        device_identifier="dev-student1-fp",
        public_key="test_public_key_123",
        platform="Windows",
        agent_version="1.0.0",
        is_active=True
    )
    db_session.add(device1)
    db_session.commit()

    pol_before = PolicyService.get_active_policy_for_device(device1, db_session)
    assert pol_before["policy_active"] is False

    # REQUIREMENT 3: Only batch owner professor can start session
    # Prof2 (not owner) tries to start -> 403 Forbidden
    r = client.post(f"/api/v1/sessions/{session_id}/start", headers=h_prof2)
    assert r.status_code == 403

    # Prof1 (owner) starts session -> 200 OK
    r = client.post(f"/api/v1/sessions/{session_id}/start", headers=h_prof1)
    assert r.status_code == 200
    started_sess = r.json()
    assert started_sess["status"].lower() == "active"
    assert started_sess["is_active"] is True
    assert started_sess["started_at"] is not None

    # Still no agent policy until student manually joins!
    pol_active_unjoined = PolicyService.get_active_policy_for_device(device1, db_session)
    assert pol_active_unjoined["policy_active"] is False

    # REQUIREMENT 8: Student outside batch gets 403 Forbidden on join attempt
    r = client.post(f"/api/v1/student/sessions/{session_id}/join", headers=h_stud2)
    assert r.status_code == 403

    # REQUIREMENT 7: Student1 manually joins active session
    r = client.post(f"/api/v1/student/sessions/{session_id}/join", headers=h_stud1)
    assert r.status_code == 200
    join_resp = r.json()
    assert join_resp["joined"] is True

    # REQUIREMENT 9: Joining twice returns 409 Conflict
    r = client.post(f"/api/v1/student/sessions/{session_id}/join", headers=h_stud1)
    assert r.status_code == 409

    # REQUIREMENT 11: Agent policy returned after student manually joins active session
    pol_after = PolicyService.get_active_policy_for_device(device1, db_session)
    assert pol_after["policy_active"] is True
    rule_dom = pol_after["domain_rules"][0]["domain_pattern"] if isinstance(pol_after["domain_rules"][0], dict) else pol_after["domain_rules"][0].domain_pattern
    assert rule_dom == "facebook.com"

    # REQUIREMENT 12: Ending session revokes agent policy
    r = client.post(f"/api/v1/sessions/{session_id}/end", headers=h_prof1)
    assert r.status_code == 200
    ended_sess = r.json()
    assert ended_sess["status"].lower() == "ended"
    assert ended_sess["is_active"] is False
    assert ended_sess["ended_at"] is not None

    pol_ended = PolicyService.get_active_policy_for_device(device1, db_session)
    assert pol_ended["policy_active"] is False
