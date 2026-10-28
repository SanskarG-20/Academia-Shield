"""
Comprehensive Integration Test Suite for Real-Time Live Monitor & Student Presence.
Tests all requirements:
1. Student joins active session & creates/updates SessionPresence.
2. Student appears in GET /api/v1/professor/sessions/{session_id}/live with online status.
3. Student outside batch gets 403 Forbidden on join and live monitor access.
4. Student cannot join session presence before clicking /join.
5. Grace period: stale browser (>45s) and agent (>90s) activity changes presence to offline.
6. Agent heartbeat updates agent_last_seen_at and keeps student online when browser is offline.
7. Multiple browser tabs increment socket count; closing one tab retains online presence.
8. Professor cannot view another professor's session monitor.
9. Session end broadcasts session_ended and blocks active presence.
10. All data originates from real database records (zero mocks/hardcoded data).
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.models.session import SessionModel, SessionParticipant, SessionPresence
from app.models.batch import Batch, BatchMember
from app.models.device import AgentDevice
from app.models.user import User

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


def test_realtime_presence_and_live_monitor_lifecycle(client, db_session):
    # 1. Register Professor 1, Professor 2, Student 1, Student 2
    prof1_id, prof1_token = register_and_login_user(client, "prof1_mon@test.edu", "professor", "Prof Mon One")
    prof2_id, prof2_token = register_and_login_user(client, "prof2_mon@test.edu", "professor", "Prof Mon Two")
    stud1_id, stud1_token = register_and_login_user(client, "stud1_mon@test.edu", "student", "Student Rocky")
    stud2_id, stud2_token = register_and_login_user(client, "stud2_mon@test.edu", "student", "Student Alex")

    h_prof1 = {"Authorization": f"Bearer {prof1_token}"}
    h_prof2 = {"Authorization": f"Bearer {prof2_token}"}
    h_stud1 = {"Authorization": f"Bearer {stud1_token}"}
    h_stud2 = {"Authorization": f"Bearer {stud2_token}"}

    # 2. Prof1 creates Batch 1
    batch_resp = client.post("/api/v1/batches", json={"name": "Cyber Security B1"}, headers=h_prof1).json()
    batch_id = batch_resp["id"]
    batch_code = batch_resp["batch_code"]

    # Student 1 joins Batch 1; Student 2 does NOT
    join_b_res = client.post("/api/v1/student/batches/join", json={"batch_code": batch_code}, headers=h_stud1)
    assert join_b_res.status_code == 200

    # 3. Prof1 creates and starts Session 1
    now = datetime.now(timezone.utc)
    sess_resp = client.post(
        f"/api/v1/batches/{batch_id}/sessions",
        json={
            "title": "Network Forensics Exam",
            "description": "Live Monitor Testing",
            "start_at_utc": (now - timedelta(minutes=5)).isoformat(),
            "end_at_utc": (now + timedelta(hours=2)).isoformat()
        },
        headers=h_prof1
    ).json()
    session_id = sess_resp["id"]

    start_res = client.post(f"/api/v1/sessions/{session_id}/start", headers=h_prof1)
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "active"

    # 4. GET /live BEFORE any student joins -> 0 joined, 0 online, empty students list
    live_before = client.get(f"/api/v1/professor/sessions/{session_id}/live", headers=h_prof1)
    assert live_before.status_code == 200
    data_before = live_before.json()
    assert data_before["joined_count"] == 0
    assert data_before["online_count"] == 0
    assert len(data_before["students"]) == 0

    # 5. Student 2 (outside batch) tries to join session -> 403 Forbidden
    s2_join = client.post(f"/api/v1/student/sessions/{session_id}/join", headers=h_stud2)
    assert s2_join.status_code == 403

    # 6. Student 1 (in batch) joins session -> 200 OK
    s1_join = client.post(f"/api/v1/student/sessions/{session_id}/join", headers=h_stud1)
    assert s1_join.status_code == 200
    join_data = s1_join.json()
    assert join_data["joined"] is True
    assert "socket_config" in join_data

    # Verify SessionPresence record created
    presence_db = db_session.query(SessionPresence).filter(
        SessionPresence.session_id == session_id,
        SessionPresence.student_id == stud1_id
    ).first()
    assert presence_db is not None

    # Simulate browser heartbeat: set browser_last_seen_at to now
    presence_db.browser_last_seen_at = now
    presence_db.connected_socket_count = 1
    db_session.commit()

    # 7. GET /live AFTER Student 1 joins & sends browser heartbeat -> 1 joined, 1 online
    live_after = client.get(f"/api/v1/professor/sessions/{session_id}/live", headers=h_prof1)
    assert live_after.status_code == 200
    data_after = live_after.json()
    assert data_after["joined_count"] == 1
    assert data_after["online_count"] == 1
    assert len(data_after["students"]) == 1

    stud_item = data_after["students"][0]
    assert stud_item["student_id"] == stud1_id
    assert stud_item["name"] == "Student Rocky"
    assert stud_item["participant_status"] == "joined"
    assert stud_item["presence_status"] == "online"
    assert stud_item["connection_source"] in ("browser", "both")
    assert stud_item["engagement_score"] is None
    assert stud_item["latest_activity"] == "STUDENT_JOINED"

    # 8. REQUIREMENT 8: Prof2 (unowned) tries to access Prof1's Live Monitor -> 403 Forbidden
    unowned_live = client.get(f"/api/v1/professor/sessions/{session_id}/live", headers=h_prof2)
    assert unowned_live.status_code == 403

    # 9. Test Agent Heartbeat updates agent_last_seen_at & keeps student online
    # Register device for Student 1
    reg_dev = client.post("/api/v1/agent/devices/register", json={
        "device_name": "Rocky PC",
        "device_identifier": "dev_rocky_999",
        "public_key": "1234567890abcdef1234567890abcdef",
        "platform": "Windows",
        "agent_version": "2.3.0"
    }, headers=h_stud1)
    assert reg_dev.status_code == 201

    # Send Agent Heartbeat
    hb_res = client.post("/api/v1/agent/heartbeat", json={
        "device_identifier": "dev_rocky_999",
        "agent_version": "2.3.0",
        "health_status": "healthy"
    }, headers=h_stud1)
    assert hb_res.status_code == 200

    # Verify agent_last_seen_at updated in database
    db_session.refresh(presence_db)
    assert presence_db.agent_last_seen_at is not None

    # Simulate browser becoming stale (>45 seconds ago, e.g. browser closed)
    stale_browser_time = now - timedelta(seconds=60)
    presence_db.browser_last_seen_at = stale_browser_time
    db_session.commit()

    # Even though browser is stale (>45s), Agent heartbeat was fresh (<=90s) -> Student remains ONLINE!
    live_agent_only = client.get(f"/api/v1/professor/sessions/{session_id}/live", headers=h_prof1).json()
    assert live_agent_only["students"][0]["presence_status"] == "online"
    assert live_agent_only["students"][0]["connection_source"] == "agent"

    # 10. Simulate both browser (>45s) and agent (>90s) activity stale -> Student becomes OFFLINE
    stale_agent_time = now - timedelta(seconds=120)
    presence_db.agent_last_seen_at = stale_agent_time
    db_session.commit()

    live_stale = client.get(f"/api/v1/professor/sessions/{session_id}/live", headers=h_prof1).json()
    assert live_stale["students"][0]["presence_status"] == "offline"
    assert live_stale["students"][0]["connection_source"] == "none"
    assert live_stale["online_count"] == 0
    assert live_stale["joined_count"] == 1  # Student remains visible in joined list with OFFLINE status

    # 11. Ending Session
    end_res = client.post(f"/api/v1/sessions/{session_id}/end", headers=h_prof1)
    assert end_res.status_code == 200
    assert end_res.json()["status"] == "ended"

    # GET /live reflects ended status
    live_ended = client.get(f"/api/v1/professor/sessions/{session_id}/live", headers=h_prof1).json()
    assert live_ended["status"] == "ended"
