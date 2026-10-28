"""
Tests for Sessions & RuleSets: UTC Datetime Validation, SHA-256 Integrity, and Policy Versioning.
"""

from datetime import datetime, timezone, timedelta

def test_session_lifecycle_and_rule_sets(client):
    # Setup professor & class
    prof_token = client.post("/api/v1/auth/register", json={
        "email": "prof_jones@university.edu", "password": "Password123!", "full_name": "Dr. Jones", "role": "professor"
    }).json()
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_jones@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Cybersecurity", "course_code": "SEC-301"}, headers=prof_headers).json()["id"]

    # 1. Create Session
    now = datetime.now(timezone.utc)
    sess_payload = {
        "title": "Lab 1: Cryptography",
        "start_at": (now - timedelta(minutes=5)).isoformat(),
        "end_at": (now + timedelta(minutes=55)).isoformat(),
        "timezone": "UTC"
    }
    sess_res = client.post(f"/api/v1/classes/{class_id}/sessions", json=sess_payload, headers=prof_headers)
    assert sess_res.status_code == 201
    sess_id = sess_res.json()["id"]

    # 2. Reject Session where end_at <= start_at
    bad_sess = {
        "title": "Invalid Session",
        "start_at": (now + timedelta(minutes=30)).isoformat(),
        "end_at": (now + timedelta(minutes=10)).isoformat()
    }
    bad_res = client.post(f"/api/v1/classes/{class_id}/sessions", json=bad_sess, headers=prof_headers)
    assert bad_res.status_code == 422 or bad_res.status_code == 400

    # 3. Create Rule Set & Add Rules
    rule_set_res = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "Strict Exam Rule Set",
        "expires_at": (now + timedelta(hours=2)).isoformat()
    }, headers=prof_headers)
    assert rule_set_res.status_code == 201
    rule_set_id = rule_set_res.json()["id"]
    initial_hash = rule_set_res.json()["integrity_hash"]
    assert len(initial_hash) > 0

    # Add Domain Rule
    d_res = client.post(f"/api/v1/rule-sets/{rule_set_id}/domain-rules", json={
        "domain_pattern": "facebook.com", "action": "block", "priority": 10
    }, headers=prof_headers)
    assert d_res.status_code == 201

    # Verify SHA-256 integrity hash recalculation & version increment
    updated_rule_set = client.get(f"/api/v1/classes/{class_id}/rule-sets", headers=prof_headers).json()[0]
    assert updated_rule_set["version"] == 2
    assert updated_rule_set["integrity_hash"] != initial_hash

    # 4. Start & End Session
    start_res = client.post(f"/api/v1/sessions/{sess_id}/start", headers=prof_headers)
    assert start_res.status_code == 200
    assert start_res.json()["is_active"] is True

    end_res = client.post(f"/api/v1/sessions/{sess_id}/end", headers=prof_headers)
    assert end_res.status_code == 200
    assert end_res.json()["is_active"] is False


def test_student_unlock_request_notification_lifecycle(client):
    """Test full cycle: student creates unlock request, professor approves/rejects, student retrieves updated status."""
    # 1. Register professor and create active session
    prof_email = f"prof_{datetime.now().timestamp()}@uni.edu"
    client.post("/api/v1/auth/register", json={
        "email": prof_email, "password": "Password123!", "full_name": "Prof Smith", "role": "professor"
    })
    prof_token = client.post("/api/v1/auth/login", json={"email": prof_email, "password": "Password123!"}).json()["access_token"]
    prof_headers = {"Authorization": f"Bearer {prof_token}"}

    class_id = client.post("/api/v1/classes", json={"name": "AI Lab", "course_code": "CS-401"}, headers=prof_headers).json()["id"]

    now = datetime.now(timezone.utc)
    sess_res = client.post(f"/api/v1/classes/{class_id}/sessions", json={
        "title": "AI Midterm",
        "start_at": (now - timedelta(minutes=5)).isoformat(),
        "end_at": (now + timedelta(minutes=55)).isoformat(),
        "timezone": "UTC"
    }, headers=prof_headers)
    sess_id = sess_res.json()["id"]
    client.post(f"/api/v1/sessions/{sess_id}/start", headers=prof_headers)

    # 2. Register student and join class
    student_email = f"student_{datetime.now().timestamp()}@uni.edu"
    client.post("/api/v1/auth/register", json={
        "email": student_email, "password": "Password123!", "full_name": "Rocky Balboa", "role": "student"
    })
    student_token = client.post("/api/v1/auth/login", json={"email": student_email, "password": "Password123!"}).json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}

    client.post(f"/api/v1/classes/{class_id}/students", json={"student_email": student_email}, headers=prof_headers)

    # 3. Student submits assistance / unlock request
    req_res = client.post(f"/api/v1/sessions/{sess_id}/unlock-requests", json={
        "issue_type": "unlock_request",
        "description": "chatgpt"
    }, headers=student_headers)
    assert req_res.status_code == 201
    unlock_data = req_res.json()
    assert unlock_data["status"] == "pending"
    assert unlock_data["description"] == "chatgpt"
    request_id = unlock_data["id"]

    # 4. Professor sees pending request
    prof_list = client.get("/api/v1/professor/unlock-requests", headers=prof_headers).json()
    assert any(r["id"] == request_id and r["status"] == "pending" for r in prof_list)

    # 5. Student lists their unlock requests
    student_list = client.get("/api/v1/student/unlock-requests", headers=student_headers).json()
    assert any(r["id"] == request_id and r["status"] == "pending" for r in student_list)

    # 6. Professor Approves & Allows request
    resolve_res = client.post(
        f"/api/v1/sessions/{sess_id}/unlock-requests/{request_id}/resolve",
        json={"status": "approved", "resolution_notes": "Allowed for reference"},
        headers=prof_headers
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "approved"

    # 7. Student checks their requests and sees it's approved
    updated_student_list = client.get("/api/v1/student/unlock-requests", headers=student_headers).json()
    matched = next(r for r in updated_student_list if r["id"] == request_id)
    assert matched["status"] == "approved"
    assert matched["resolved_by"] is not None

    # 8. Test rejection flow on a second request
    req2_res = client.post(f"/api/v1/sessions/{sess_id}/unlock-requests", json={
        "issue_type": "technical_issue",
        "description": "social media site"
    }, headers=student_headers)
    req2_id = req2_res.json()["id"]

    client.post(
        f"/api/v1/sessions/{sess_id}/unlock-requests/{req2_id}/resolve",
        json={"status": "rejected", "resolution_notes": "Not permitted during exam"},
        headers=prof_headers
    )

    updated_list2 = client.get("/api/v1/student/unlock-requests", headers=student_headers).json()
    matched2 = next(r for r in updated_list2 if r["id"] == req2_id)
    assert matched2["status"] == "rejected"
    assert "Not permitted during exam" in matched2["resolution_notes"]

