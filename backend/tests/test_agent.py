"""
Tests for Agent API: Device Registration, Active Policy Resolution, Heartbeats, and Idempotent Telemetry.
"""

import pytest
from datetime import datetime, timezone, timedelta

def test_agent_device_registration_policy_and_telemetry(client):
    # Setup professor, class, student, session, and rule set
    prof_token = client.post("/api/v1/auth/register", json={
        "email": "prof_agent_test@university.edu", "password": "Password123!", "full_name": "Prof Agent", "role": "professor"
    }).json()
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_agent_test@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Network Security", "course_code": "SEC-402"}, headers=prof_headers).json()["id"]

    # Student registration & login
    stud_token = client.post("/api/v1/auth/register", json={
        "email": "agent_student@university.edu", "password": "Password123!", "full_name": "Agent Student", "role": "student"
    }).json()
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'agent_student@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    # Enroll student in class
    client.post(f"/api/v1/classes/{class_id}/students", json={"student_email_or_id": "agent_student@university.edu"}, headers=prof_headers)

    # 1. Register Device
    reg_dev_res = client.post("/api/v1/agent/devices/register", json={
        "device_name": "Student Laptop",
        "device_identifier": "DEV_IDENT_999",
        "public_key": "1234567890abcdef1234567890abcdef",
        "platform": "Windows",
        "agent_version": "2.3.0"
    }, headers=stud_headers)
    assert reg_dev_res.status_code == 201

    # 2. Heartbeat
    hb_res = client.post("/api/v1/agent/heartbeat", json={
        "device_identifier": "DEV_IDENT_999",
        "agent_version": "2.3.0",
        "health_status": "healthy",
        "dns_status": "normal"
    }, headers=stud_headers)
    assert hb_res.status_code == 200

    # 3. Policy Active Check BEFORE session start (Must return policy_active = False)
    headers_before = dict(stud_headers)
    headers_before["X-Device-Identifier"] = "DEV_IDENT_999"
    pol_before = client.get("/api/v1/agent/policies/active", headers=headers_before).json()
    assert pol_before["policy_active"] is False

    # Create & Start Session + Add Domain Rule
    now = datetime.now(timezone.utc)
    sess_id = client.post(f"/api/v1/classes/{class_id}/sessions", json={
        "title": "Security Exam",
        "start_at": (now - timedelta(minutes=5)).isoformat(),
        "end_at": (now + timedelta(minutes=55)).isoformat()
    }, headers=prof_headers).json()["id"]

    rule_set_id = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "Exam Blocklist", "expires_at": (now + timedelta(hours=2)).isoformat()
    }, headers=prof_headers).json()["id"]

    client.post(f"/api/v1/rule-sets/{rule_set_id}/domain-rules", json={
        "domain_pattern": "reddit.com", "action": "block"
    }, headers=prof_headers)

    client.post(f"/api/v1/sessions/{sess_id}/start", headers=prof_headers)

    # Student manually joins active session
    join_res = client.post(f"/api/v1/student/sessions/{sess_id}/join", headers=stud_headers)
    assert join_res.status_code == 200

    # 4. Policy Active Check AFTER session start & student join (Must return policy_active = True and domain rule)
    headers_with_device = dict(stud_headers)
    headers_with_device["X-Device-Identifier"] = "DEV_IDENT_999"
    pol_after = client.get("/api/v1/agent/policies/active", headers=headers_with_device).json()
    assert pol_after["policy_active"] is True
    assert len(pol_after["domain_rules"]) == 1
    assert pol_after["domain_rules"][0]["domain_pattern"] == "reddit.com"

    # 5. Telemetry Ingestion with Idempotency Key
    telemetry_payload = [{
        "event_id": "unique_evt_uuid_001",
        "device_identifier": "DEV_IDENT_999",
        "session_id": sess_id,
        "event_type": "dns_block",
        "payload": {"domain": "reddit.com", "action": "blocked"},
        "occurred_at": now.isoformat()
    }]

    t_res1 = client.post("/api/v1/agent/telemetry/events", json=telemetry_payload, headers=headers_with_device)
    assert t_res1.status_code == 200
    assert t_res1.json()["processed"] == 1

    # Re-submitting same event_id must safely handle duplicate
    t_res2 = client.post("/api/v1/agent/telemetry/events", json=telemetry_payload, headers=headers_with_device)
    assert t_res2.status_code in (200, 409)
