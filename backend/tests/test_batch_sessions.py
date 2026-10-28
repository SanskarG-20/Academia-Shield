"""
Tests for Batch-Specific Academic Sessions, RBAC Isolation, and Audit Logging.
"""

from datetime import datetime, timedelta, timezone
import pytest

def test_batch_sessions_isolation_and_rbac(client):
    # 1. Register Professor Alpha, Student A (Batch 1), and Student B (Batch 2)
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/register', json={'email': 'prof_sess@university.edu', 'password': 'Password123!', 'full_name': 'Prof Sess', 'role': 'professor'}).json() and client.post('/api/v1/auth/login', json={'email': 'prof_sess@university.edu', 'password': 'Password123!'}).json()['access_token']}"}
    stud_a_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/register', json={'email': 'stud_a_sess@university.edu', 'password': 'Password123!', 'full_name': 'Student A', 'role': 'student'}).json() and client.post('/api/v1/auth/login', json={'email': 'stud_a_sess@university.edu', 'password': 'Password123!'}).json()['access_token']}"}
    stud_b_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/register', json={'email': 'stud_b_sess@university.edu', 'password': 'Password123!', 'full_name': 'Student B', 'role': 'student'}).json() and client.post('/api/v1/auth/login', json={'email': 'stud_b_sess@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    # 2. Professor creates Batch 1 and Batch 2
    b1 = client.post("/api/v1/batches", json={"name": "Database Systems B1"}, headers=prof_headers).json()
    b2 = client.post("/api/v1/batches", json={"name": "Algorithms B2"}, headers=prof_headers).json()
    b1_id, b1_code = b1["id"], b1["batch_code"]
    b2_id, b2_code = b2["id"], b2["batch_code"]

    # 3. Student A joins Batch 1; Student B joins Batch 2
    client.post("/api/v1/student/batches/join", json={"batch_code": b1_code}, headers=stud_a_headers)
    client.post("/api/v1/student/batches/join", json={"batch_code": b2_code}, headers=stud_b_headers)

    # 4. Professor creates Session 1 for Batch 1 (using UTC time and Asia/Kolkata timezone)
    now_utc = datetime.now(timezone.utc)
    start_time = (now_utc + timedelta(hours=1)).isoformat()
    end_time = (now_utc + timedelta(hours=3)).isoformat()

    s1_res = client.post(f"/api/v1/batches/{b1_id}/sessions", json={
        "title": "DBMS Lab Session 1",
        "start_at_utc": start_time,
        "end_at_utc": end_time,
        "timezone": "Asia/Kolkata"
    }, headers=prof_headers)
    assert s1_res.status_code == 201
    s1 = s1_res.json()
    assert s1["batch_id"] == b1_id
    assert s1["status"] == "scheduled"
    assert s1["policy_version"] == 1
    s1_id = s1["id"]

    # 5. Student A (joined in Batch 1) lists sessions -> sees Session 1
    stud_a_sessions = client.get("/api/v1/student/sessions", headers=stud_a_headers).json()
    assert len(stud_a_sessions) == 1
    assert stud_a_sessions[0]["id"] == s1_id
    assert stud_a_sessions[0]["batch_id"] == b1_id

    # 6. Student A lists sessions specifically for Batch 1 -> 200 OK
    b1_sessions = client.get(f"/api/v1/student/batches/{b1_id}/sessions", headers=stud_a_headers)
    assert b1_sessions.status_code == 200
    assert len(b1_sessions.json()) == 1

    # 7. Student B (joined ONLY in Batch 2) lists sessions -> returns 0 sessions
    stud_b_sessions = client.get("/api/v1/student/sessions", headers=stud_b_headers).json()
    assert len(stud_b_sessions) == 0

    # 8. Student B tries to access Batch 1's sessions -> 403 Forbidden!
    forbidden_list = client.get(f"/api/v1/student/batches/{b1_id}/sessions", headers=stud_b_headers)
    assert forbidden_list.status_code == 403
    msg = forbidden_list.json().get("detail") or forbidden_list.json().get("message", "")
    assert "Access denied" in msg

    # 9. Student B tries to access Session 1 by ID -> 403 Forbidden!
    forbidden_get = client.get(f"/api/v1/sessions/{s1_id}", headers=stud_b_headers)
    assert forbidden_get.status_code == 403

    # 10. Professor starts Session 1
    start_res = client.post(f"/api/v1/sessions/{s1_id}/start", headers=prof_headers)
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "active"
    assert start_res.json()["policy_version"] == 2

    # 11. Professor ends Session 1
    end_res = client.post(f"/api/v1/sessions/{s1_id}/end", headers=prof_headers)
    assert end_res.status_code == 200
    assert end_res.json()["status"] == "ended"
    assert end_res.json()["policy_version"] == 3

def test_unowned_batch_session_creation_rejected(client):
    prof1_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/register', json={'email': 'prof1_sess@university.edu', 'password': 'Password123!', 'full_name': 'Prof 1', 'role': 'professor'}).json() and client.post('/api/v1/auth/login', json={'email': 'prof1_sess@university.edu', 'password': 'Password123!'}).json()['access_token']}"}
    prof2_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/register', json={'email': 'prof2_sess@university.edu', 'password': 'Password123!', 'full_name': 'Prof 2', 'role': 'professor'}).json() and client.post('/api/v1/auth/login', json={'email': 'prof2_sess@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    # Prof 1 creates Batch 1
    b1 = client.post("/api/v1/batches", json={"name": "Prof 1 Batch"}, headers=prof1_headers).json()

    # Prof 2 tries to create session in Prof 1's batch -> 403 Forbidden!
    now_utc = datetime.now(timezone.utc)
    res = client.post(f"/api/v1/batches/{b1['id']}/sessions", json={
        "title": "Unauthorized Session",
        "start_at_utc": (now_utc + timedelta(hours=1)).isoformat(),
        "end_at_utc": (now_utc + timedelta(hours=2)).isoformat()
    }, headers=prof2_headers)

    assert res.status_code == 403
    assert "batches you own" in res.json()["message"].lower()
