"""
Comprehensive Test Suite for Section 2.6 Scheduler Prerequisites.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.models.audit_log import AuditLog
from app.models.session import SessionModel

def create_user_and_headers(client, email: str, role: str):
    client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": f"Test {role.capitalize()}",
        "role": role
    })
    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    token = login_res.json()["access_token"]
    user_data = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    return user_data, {"Authorization": f"Bearer {token}"}

def test_system_server_time_endpoint(client):
    res = client.get("/api/v1/system/time")
    assert res.status_code == 200
    data = res.json()
    assert "server_time_utc" in data
    assert data["time_zone"] == "UTC"
    assert data["max_allowed_clock_skew_seconds"] == 120

def test_session_creation_validations_and_audit_logging(client, db_session):
    prof_data, headers = create_user_and_headers(client, "prof_sched_val@univ.edu", "professor")

    # 1. Create Class
    c_res = client.post(
        "/api/v1/classes",
        json={"name": "Scheduler Lab Class", "course_code": "SCHED101", "description": "Test class"},
        headers=headers
    )
    assert c_res.status_code == 201
    class_id = c_res.json()["id"]

    # 2. Test Invalid IANA Timezone -> 422
    now = datetime.now(timezone.utc)
    inv_tz_res = client.post(
        f"/api/v1/classes/{class_id}/sessions",
        json={
            "title": "Invalid TZ Session",
            "start_at_utc": now.isoformat(),
            "end_at_utc": (now + timedelta(hours=1)).isoformat(),
            "timezone": "Invalid/Fake_Timezone",
            "recurrence_type": "none"
        },
        headers=headers
    )
    assert inv_tz_res.status_code == 422

    # 3. Test Naive Datetime -> 422
    naive_dt_str = "2026-08-09T12:00:00"  # No timezone offset
    naive_res = client.post(
        f"/api/v1/classes/{class_id}/sessions",
        json={
            "title": "Naive Datetime Session",
            "start_at_utc": naive_dt_str,
            "end_at_utc": (now + timedelta(hours=1)).isoformat(),
            "timezone": "UTC",
            "recurrence_type": "none"
        },
        headers=headers
    )
    assert naive_res.status_code == 422

    # 4. Test End Before Start -> 422
    end_before_res = client.post(
        f"/api/v1/classes/{class_id}/sessions",
        json={
            "title": "End Before Start Session",
            "start_at_utc": (now + timedelta(hours=2)).isoformat(),
            "end_at_utc": (now + timedelta(hours=1)).isoformat(),
            "timezone": "UTC",
            "recurrence_type": "none"
        },
        headers=headers
    )
    assert end_before_res.status_code == 422

    # 5. Test Invalid Recurrence -> 422
    inv_rec_res = client.post(
        f"/api/v1/classes/{class_id}/sessions",
        json={
            "title": "Bad Recurrence Session",
            "start_at_utc": now.isoformat(),
            "end_at_utc": (now + timedelta(hours=1)).isoformat(),
            "timezone": "UTC",
            "recurrence_type": "invalid_recurrence_type"
        },
        headers=headers
    )
    assert inv_rec_res.status_code == 422

    # 6. Test Valid One-Time & Weekly Session Creation
    valid_res = client.post(
        f"/api/v1/classes/{class_id}/sessions",
        json={
            "title": "Valid Operating Systems Session",
            "start_at_utc": now.isoformat(),
            "end_at_utc": (now + timedelta(hours=2)).isoformat(),
            "timezone": "Asia/Kolkata",
            "recurrence_type": "weekly",
            "recurrence_interval": 1,
            "recurrence_days_of_week": ["monday", "wednesday"]
        },
        headers=headers
    )
    assert valid_res.status_code == 201
    sess_data = valid_res.json()
    assert sess_data["title"] == "Valid Operating Systems Session"
    assert sess_data["timezone"] == "Asia/Kolkata"
    assert sess_data["recurrence_type"] == "weekly"
    assert sess_data["policy_version"] == 1
    assert "server_time_utc" in sess_data

    # Verify AuditLog created
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_id == sess_data["id"],
        AuditLog.action == "session_created"
    ).first()
    assert audit is not None
    assert audit.actor_user_id == prof_data["id"]

def test_session_rbac_ownership_and_student_access(client, db_session):
    prof_data, prof_headers = create_user_and_headers(client, "prof_rbac_own@univ.edu", "professor")
    stud_data, stud_headers = create_user_and_headers(client, "stud_rbac_own@univ.edu", "student")

    # Professor 1 creates Class 1
    c1_res = client.post(
        "/api/v1/classes",
        json={"name": "Math 101", "course_code": "MATH101"},
        headers=prof_headers
    )
    c1_id = c1_res.json()["id"]

    now = datetime.now(timezone.utc)
    s1_res = client.post(
        f"/api/v1/classes/{c1_id}/sessions",
        json={
            "title": "Calculus Lecture",
            "start_at_utc": now.isoformat(),
            "end_at_utc": (now + timedelta(hours=1)).isoformat(),
            "timezone": "UTC"
        },
        headers=prof_headers
    )
    session_id = s1_res.json()["id"]

    # Student not enrolled -> GET sessions returns 403
    unauth_list = client.get(f"/api/v1/classes/{c1_id}/sessions", headers=stud_headers)
    assert unauth_list.status_code == 403

    unauth_get = client.get(f"/api/v1/sessions/{session_id}", headers=stud_headers)
    assert unauth_get.status_code == 403

    # Enroll Student in Class 1
    enroll_res = client.post(
        f"/api/v1/classes/{c1_id}/students",
        json={"student_email_or_id": "stud_rbac_own@univ.edu"},
        headers=prof_headers
    )
    assert enroll_res.status_code in (200, 201)

    # Student now enrolled -> GET session returns 200
    auth_list = client.get(f"/api/v1/classes/{c1_id}/sessions", headers=stud_headers)
    assert auth_list.status_code == 200
    assert len(auth_list.json()) == 1

    auth_get = client.get(f"/api/v1/sessions/{session_id}", headers=stud_headers)
    assert auth_get.status_code == 200
    assert auth_get.json()["id"] == session_id

def test_session_lifecycle_start_end_cancel(client, db_session):
    prof_data, headers = create_user_and_headers(client, "prof_lifecycle@univ.edu", "professor")

    c_res = client.post("/api/v1/classes", json={"name": "Physics", "course_code": "PHY101"}, headers=headers)
    c_id = c_res.json()["id"]

    now = datetime.now(timezone.utc)
    s_res = client.post(
        f"/api/v1/classes/{c_id}/sessions",
        json={
            "title": "Quantum Lab",
            "start_at_utc": now.isoformat(),
            "end_at_utc": (now + timedelta(hours=2)).isoformat(),
            "timezone": "UTC"
        },
        headers=headers
    )
    s_id = s_res.json()["id"]
    initial_version = s_res.json()["policy_version"]

    # Start Session
    start_res = client.post(f"/api/v1/sessions/{s_id}/start", headers=headers)
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "active"
    assert start_res.json()["is_active"] is True
    assert start_res.json()["policy_version"] == initial_version + 1

    # End Session
    end_res = client.post(f"/api/v1/sessions/{s_id}/end", headers=headers)
    assert end_res.status_code == 200
    assert end_res.json()["status"] == "ended"
    assert end_res.json()["is_active"] is False
    assert end_res.json()["policy_version"] == initial_version + 2

    # Cancel Session
    cancel_res = client.post(f"/api/v1/sessions/{s_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
    assert cancel_res.json()["is_active"] is False
    assert cancel_res.json()["policy_version"] == initial_version + 3
