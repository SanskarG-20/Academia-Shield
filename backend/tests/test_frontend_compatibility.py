"""Regression coverage for the React application's public API contract."""

from datetime import datetime, timedelta, timezone


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_profile_settings_and_student_session_flow(client):
    professor = client.post("/api/auth/register/professor", json={
        "full_name": "Professor One",
        "email": "prof.compat@example.edu",
        "employee_id": "EMP-100",
        "department": "CE",
        "password": "Password123!",
    })
    assert professor.status_code == 201
    professor_headers = _headers(professor.json()["access_token"])

    # This is the exact method and payload used by the Settings screen.
    profile = client.patch("/api/auth/me", json={
        "name": "Professor Updated",
        "department": "IT",
    }, headers=professor_headers)
    assert profile.status_code == 200
    assert profile.json()["full_name"] == "Professor Updated"
    assert profile.json()["department"] == "IT"

    batch = client.post("/api/v1/batches", json={"name": "Compatibility Batch"}, headers=professor_headers)
    assert batch.status_code == 201
    batch_id = batch.json()["id"]

    now = datetime.now(timezone.utc)
    session = client.post("/api/sessions", json={
        "title": "Compatibility Session",
        "course": "Networks",
        "batch_id": batch_id,
        "start_time": (now + timedelta(hours=1)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
    }, headers=professor_headers)
    assert session.status_code == 201

    student = client.post("/api/auth/register/student", json={
        "full_name": "Student One",
        "email": "student.compat@example.edu",
        "student_id": "STU-100",
        "department": "CE",
        "password": "Password123!",
    })
    assert student.status_code == 201
    student_headers = _headers(student.json()["access_token"])

    joined = client.post("/api/v1/student/batches/join", json={"batch_code": batch.json()["batch_code"]}, headers=student_headers)
    assert joined.status_code == 200

    student_sessions = client.get("/api/v1/student/sessions", headers=student_headers)
    assert student_sessions.status_code == 200
    data = student_sessions.json()
    assert len(data) == 1
    assert data[0]["start_at_utc"]
    assert data[0]["status"] == "scheduled"


def test_student_can_join_a_session_created_for_a_live_batch(client):
    professor = client.post("/api/auth/register/professor", json={
        "full_name": "Live Professor", "email": "live.prof@example.edu", "password": "Password123!",
    }).json()
    professor_headers = _headers(professor["access_token"])
    batch = client.post("/api/v1/batches", json={"name": "Live Batch"}, headers=professor_headers).json()

    now = datetime.now(timezone.utc)
    created = client.post(f"/api/v1/batches/{batch['id']}/sessions", json={
        "title": "Live Batch Session",
        "start_at_utc": (now - timedelta(minutes=5)).isoformat(),
        "end_at_utc": (now + timedelta(minutes=30)).isoformat(),
    }, headers=professor_headers)
    assert created.status_code == 201
    assert created.json()["status"] == "scheduled"
    sess_id = created.json()["id"]

    start_resp = client.post(f"/api/v1/sessions/{sess_id}/start", headers=professor_headers)
    assert start_resp.status_code == 200

    student = client.post("/api/auth/register/student", json={
        "full_name": "Live Student", "email": "live.student@example.edu", "password": "Password123!",
    }).json()
    student_headers = _headers(student["access_token"])
    assert client.post("/api/v1/student/batches/join", json={"batch_code": batch["batch_code"]}, headers=student_headers).status_code == 200

    sessions = client.get("/api/v1/student/sessions", headers=student_headers).json()
    assert sessions[0]["status"] == "active"
    joined = client.post(f"/api/sessions/{sessions[0]['id']}/join", headers=student_headers)
    assert joined.status_code == 200
