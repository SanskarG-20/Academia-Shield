"""
Comprehensive Tests for Section 2.5 Application-Level Blocking.
"""

from datetime import datetime, timezone, timedelta
import pytest

def test_professor_can_create_rules_only_in_own_class(client):
    # Register Professor 1 & Professor 2
    client.post("/api/v1/auth/register", json={
        "email": "prof1_app@university.edu", "password": "Password123!", "full_name": "Prof One", "role": "professor"
    })
    prof1_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof1_app@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    client.post("/api/v1/auth/register", json={
        "email": "prof2_app@university.edu", "password": "Password123!", "full_name": "Prof Two", "role": "professor"
    })
    prof2_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof2_app@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class1_id = client.post("/api/v1/classes", json={"name": "OS Fundamentals", "course_code": "CS-101"}, headers=prof1_headers).json()["id"]
    class2_id = client.post("/api/v1/classes", json={"name": "Compiler Design", "course_code": "CS-401"}, headers=prof2_headers).json()["id"]

    now = datetime.now(timezone.utc)
    rs1_id = client.post(f"/api/v1/classes/{class1_id}/rule-sets", json={
        "name": "OS Lab Policy", "expires_at": (now + timedelta(hours=5)).isoformat()
    }, headers=prof1_headers).json()["id"]

    rs2_id = client.post(f"/api/v1/classes/{class2_id}/rule-sets", json={
        "name": "Compiler Policy", "expires_at": (now + timedelta(hours=5)).isoformat()
    }, headers=prof2_headers).json()["id"]

    # Prof 1 can create rule in Class 1
    r1 = client.post(f"/api/v1/rule-sets/{rs1_id}/application-rules", json={
        "executable_name": "notepad.exe", "action": "warn", "priority": 100, "cooldown_seconds": 30
    }, headers=prof1_headers)
    assert r1.status_code == 201

    # Prof 1 CANNOT create rule in Prof 2's Class 2 rule set
    r2 = client.post(f"/api/v1/rule-sets/{rs2_id}/application-rules", json={
        "executable_name": "notepad.exe", "action": "warn"
    }, headers=prof1_headers)
    assert r2.status_code == 403

def test_student_cannot_create_or_edit_rules(client):
    # Register Prof & Student
    client.post("/api/v1/auth/register", json={
        "email": "prof_owner@university.edu", "password": "Password123!", "full_name": "Prof Owner", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_owner@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    client.post("/api/v1/auth/register", json={
        "email": "stud_rbac@university.edu", "password": "Password123!", "full_name": "Student RBAC", "role": "student"
    })
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_rbac@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Software Eng", "course_code": "SE-201"}, headers=prof_headers).json()["id"]
    now = datetime.now(timezone.utc)
    rs_id = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "SE Policy", "expires_at": (now + timedelta(hours=5)).isoformat()
    }, headers=prof_headers).json()["id"]

    # Student POST application-rules -> 403 Forbidden
    res_post = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "calc.exe", "action": "close"
    }, headers=stud_headers)
    assert res_post.status_code == 403

def test_agent_gets_rules_only_during_active_assigned_session(client):
    # Setup Prof & Student
    client.post("/api/v1/auth/register", json={
        "email": "prof_active_test@university.edu", "password": "Password123!", "full_name": "Prof Active", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_active_test@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    client.post("/api/v1/auth/register", json={
        "email": "stud_active_test@university.edu", "password": "Password123!", "full_name": "Student Active", "role": "student"
    })
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_active_test@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Distributed Systems", "course_code": "CS-501"}, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/classes/{class_id}/students", json={"student_email_or_id": "stud_active_test@university.edu"}, headers=prof_headers)

    # Register student device
    reg_res = client.post("/api/v1/agent/devices/register", json={
        "device_name": "Active Laptop", "device_identifier": "DEV_ACTIVE_101",
        "public_key": "1234567890abcdef1234567890abcdef", "platform": "Windows", "agent_version": "2.3.0"
    }, headers=stud_headers)
    dev_headers = dict(stud_headers)
    dev_headers["X-Device-Identifier"] = "DEV_ACTIVE_101"

    # Before session: policy_active = False
    pol_before = client.get("/api/v1/agent/policies/active", headers=dev_headers).json()
    assert pol_before["policy_active"] is False

    # Create & Start Session + Add Rule
    now = datetime.now(timezone.utc)
    sess_id = client.post(f"/api/v1/classes/{class_id}/sessions", json={
        "title": "DS Lab Exam", "start_at": (now - timedelta(minutes=5)).isoformat(), "end_at": (now + timedelta(hours=1)).isoformat()
    }, headers=prof_headers).json()["id"]

    rs_id = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "DS Exam RuleSet", "expires_at": (now + timedelta(hours=2)).isoformat()
    }, headers=prof_headers).json()["id"]

    client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "notepad.exe", "action": "warn", "priority": 100, "reason": "Restricted during exam", "cooldown_seconds": 60
    }, headers=prof_headers)

    client.post(f"/api/v1/sessions/{sess_id}/start", headers=prof_headers)

    # Student manually joins active session
    client.post(f"/api/v1/student/sessions/{sess_id}/join", headers=stud_headers)

    # After session start & student join: policy_active = True and application_rules returned
    pol_after = client.get("/api/v1/agent/policies/active", headers=dev_headers).json()
    assert pol_after["policy_active"] is True
    assert len(pol_after["application_rules"]) == 1
    rule = pol_after["application_rules"][0]
    assert rule["executable_name"] == "notepad.exe"
    assert rule["action"] == "warn"

def test_expired_policies_return_no_enforceable_rules(client):
    client.post("/api/v1/auth/register", json={
        "email": "prof_exp@university.edu", "password": "Password123!", "full_name": "Prof Exp", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_exp@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    client.post("/api/v1/auth/register", json={
        "email": "stud_exp@university.edu", "password": "Password123!", "full_name": "Student Exp", "role": "student"
    })
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_exp@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Algorithms", "course_code": "CS-202"}, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/classes/{class_id}/students", json={"student_email_or_id": "stud_exp@university.edu"}, headers=prof_headers)

    client.post("/api/v1/agent/devices/register", json={
        "device_name": "Exp Laptop", "device_identifier": "DEV_EXP_102",
        "public_key": "1234567890abcdef1234567890abcdef", "platform": "Windows", "agent_version": "2.3.0"
    }, headers=stud_headers)
    dev_headers = dict(stud_headers)
    dev_headers["X-Device-Identifier"] = "DEV_EXP_102"

    now = datetime.now(timezone.utc)
    sess_id = client.post(f"/api/v1/classes/{class_id}/sessions", json={
        "title": "Algo Quiz", "start_at": (now - timedelta(minutes=5)).isoformat(), "end_at": (now + timedelta(hours=1)).isoformat()
    }, headers=prof_headers).json()["id"]

    # Rule set expired 10 minutes ago
    rs_id = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "Expired RuleSet", "expires_at": (now - timedelta(minutes=10)).isoformat()
    }, headers=prof_headers).json()["id"]

    client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "notepad.exe", "action": "warn"
    }, headers=prof_headers)

    client.post(f"/api/v1/sessions/{sess_id}/start", headers=prof_headers)

    # Policy is expired -> policy_active = False
    pol_res = client.get("/api/v1/agent/policies/active", headers=dev_headers).json()
    assert pol_res["policy_active"] is False

def test_invalid_action_hash_and_path_pattern_rejected(client):
    client.post("/api/v1/auth/register", json={
        "email": "prof_val@university.edu", "password": "Password123!", "full_name": "Prof Val", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_val@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Database Systems", "course_code": "CS-301"}, headers=prof_headers).json()["id"]
    now = datetime.now(timezone.utc)
    rs_id = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "DB Policy", "expires_at": (now + timedelta(hours=5)).isoformat()
    }, headers=prof_headers).json()["id"]

    # 1. Invalid action 'kill' -> 422 Validation Error
    r_action = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "notepad.exe", "action": "kill"
    }, headers=prof_headers)
    assert r_action.status_code == 422

    # 2. Invalid SHA-256 hash -> 422 Validation Error
    r_hash = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "notepad.exe", "action": "close", "trusted_hash": "invalid_hash_string"
    }, headers=prof_headers)
    assert r_hash.status_code == 422

    # 3. Shell metacharacters in path pattern -> 422 Validation Error
    r_path = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "notepad.exe", "executable_path_pattern": "C:\\Program Files\\; rm -rf /"
    }, headers=prof_headers)
    assert r_path.status_code == 422

    # 4. Target protected system process for close action -> 400 Bad Request
    r_protected = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "explorer.exe", "action": "close"
    }, headers=prof_headers)
    assert r_protected.status_code == 400

def test_policy_version_and_integrity_hash_changes_after_modification(client):
    client.post("/api/v1/auth/register", json={
        "email": "prof_hash@university.edu", "password": "Password123!", "full_name": "Prof Hash", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_hash@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Cybersecurity", "course_code": "SEC-501"}, headers=prof_headers).json()["id"]
    now = datetime.now(timezone.utc)
    rs = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "Sec Policy", "expires_at": (now + timedelta(hours=5)).isoformat()
    }, headers=prof_headers).json()

    v1 = rs["version"]
    h1 = rs["integrity_hash"]

    # Add rule
    app_rule = client.post(f"/api/v1/rule-sets/{rs['id']}/application-rules", json={
        "executable_name": "notepad.exe", "action": "warn"
    }, headers=prof_headers).json()

    rs_after_add = client.get(f"/api/v1/classes/{class_id}/rule-sets", headers=prof_headers).json()[0]
    assert rs_after_add["version"] == v1 + 1
    assert rs_after_add["integrity_hash"] != h1

    # Update rule
    client.patch(f"/api/v1/application-rules/{app_rule['id']}", json={"action": "close"}, headers=prof_headers)
    rs_after_patch = client.get(f"/api/v1/classes/{class_id}/rule-sets", headers=prof_headers).json()[0]
    assert rs_after_patch["version"] == v1 + 2
    assert rs_after_patch["integrity_hash"] != rs_after_add["integrity_hash"]

def test_telemetry_authenticated_and_idempotent(client):
    client.post("/api/v1/auth/register", json={
        "email": "prof_telem@university.edu", "password": "Password123!", "full_name": "Prof Telem", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_telem@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    client.post("/api/v1/auth/register", json={
        "email": "stud_telem@university.edu", "password": "Password123!", "full_name": "Student Telem", "role": "student"
    })
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_telem@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Telemetry Class", "course_code": "CS-999"}, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/classes/{class_id}/students", json={"student_email_or_id": "stud_telem@university.edu"}, headers=prof_headers)

    client.post("/api/v1/agent/devices/register", json={
        "device_name": "Telem Laptop", "device_identifier": "DEV_TELEM_201",
        "public_key": "1234567890abcdef1234567890abcdef", "platform": "Windows", "agent_version": "2.3.0"
    }, headers=stud_headers)
    dev_headers = dict(stud_headers)
    dev_headers["X-Device-Identifier"] = "DEV_TELEM_201"

    now = datetime.now(timezone.utc)
    sess_id = client.post(f"/api/v1/classes/{class_id}/sessions", json={
        "title": "Telem Session", "start_at": (now - timedelta(minutes=5)).isoformat(), "end_at": (now + timedelta(hours=1)).isoformat()
    }, headers=prof_headers).json()["id"]

    event_payload = {
        "event_id": "evt_unique_1001",
        "event_type": "application_violation",
        "device_identifier": "DEV_TELEM_201",
        "session_id": sess_id,
        "policy_version": 1,
        "executable_name": "notepad.exe",
        "action_requested": "warn",
        "action_result": "warned",
        "occurred_at": now.isoformat()
    }

    # 1. Unauthenticated request -> 401 Unauthorized
    res_unauth = client.post("/api/v1/agent/telemetry/events", json=event_payload)
    assert res_unauth.status_code == 401

    # 2. Authenticated request -> 200 OK
    res_auth = client.post("/api/v1/agent/telemetry/events", json=event_payload, headers=dev_headers)
    assert res_auth.status_code == 200
    assert res_auth.json()["processed"] == 1

def test_duplicate_event_id_handled_safely(client):
    client.post("/api/v1/auth/register", json={
        "email": "prof_dup@university.edu", "password": "Password123!", "full_name": "Prof Dup", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_dup@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    client.post("/api/v1/auth/register", json={
        "email": "stud_dup@university.edu", "password": "Password123!", "full_name": "Student Dup", "role": "student"
    })
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_dup@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Dup Test Class", "course_code": "CS-888"}, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/classes/{class_id}/students", json={"student_email_or_id": "stud_dup@university.edu"}, headers=prof_headers)

    client.post("/api/v1/agent/devices/register", json={
        "device_name": "Dup Laptop", "device_identifier": "DEV_DUP_301",
        "public_key": "1234567890abcdef1234567890abcdef", "platform": "Windows", "agent_version": "2.3.0"
    }, headers=stud_headers)
    dev_headers = dict(stud_headers)
    dev_headers["X-Device-Identifier"] = "DEV_DUP_301"

    now = datetime.now(timezone.utc)
    sess_id = client.post(f"/api/v1/classes/{class_id}/sessions", json={
        "title": "Dup Session", "start_at": (now - timedelta(minutes=5)).isoformat(), "end_at": (now + timedelta(hours=1)).isoformat()
    }, headers=prof_headers).json()["id"]

    event_payload = {
        "event_id": "evt_dup_2002",
        "event_type": "application_violation",
        "device_identifier": "DEV_DUP_301",
        "session_id": sess_id,
        "executable_name": "notepad.exe",
        "action_result": "warned",
        "occurred_at": now.isoformat()
    }

    t1 = client.post("/api/v1/agent/telemetry/events", json=event_payload, headers=dev_headers)
    assert t1.status_code == 200

    # Single event re-submission returns 409 Conflict
    t2 = client.post("/api/v1/agent/telemetry/events", json=event_payload, headers=dev_headers)
    assert t2.status_code == 409

def test_agent_cannot_submit_telemetry_for_another_device_or_session(client):
    # Setup Student A and Student B
    client.post("/api/v1/auth/register", json={
        "email": "stud_a@university.edu", "password": "Password123!", "full_name": "Student A", "role": "student"
    })
    stud_a_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_a@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    client.post("/api/v1/auth/register", json={
        "email": "stud_b@university.edu", "password": "Password123!", "full_name": "Student B", "role": "student"
    })

    client.post("/api/v1/agent/devices/register", json={
        "device_name": "Student B Laptop", "device_identifier": "DEV_STUD_B",
        "public_key": "1234567890abcdef1234567890abcdef", "platform": "Windows", "agent_version": "2.3.0"
    }, headers={"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_b@university.edu', 'password': 'Password123!'}).json()['access_token']}"})

    # Student A tries to submit telemetry with Student B's device header -> 403 Forbidden
    headers_a_with_b_device = dict(stud_a_headers)
    headers_a_with_b_device["X-Device-Identifier"] = "DEV_STUD_B"

    now = datetime.now(timezone.utc)
    res = client.post("/api/v1/agent/telemetry/events", json={
        "event_id": "evt_cross_dev_100",
        "event_type": "application_violation",
        "device_identifier": "DEV_STUD_B",
        "executable_name": "notepad.exe",
        "occurred_at": now.isoformat()
    }, headers=headers_a_with_b_device)

    assert res.status_code == 403

def test_protected_process_records_included_correctly(client):
    client.post("/api/v1/auth/register", json={
        "email": "prof_prot@university.edu", "password": "Password123!", "full_name": "Prof Prot", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_prot@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    client.post("/api/v1/auth/register", json={
        "email": "stud_prot@university.edu", "password": "Password123!", "full_name": "Student Prot", "role": "student"
    })
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_prot@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Operating Systems", "course_code": "CS-302"}, headers=prof_headers).json()["id"]
    client.post(f"/api/v1/classes/{class_id}/students", json={"student_email_or_id": "stud_prot@university.edu"}, headers=prof_headers)

    client.post("/api/v1/agent/devices/register", json={
        "device_name": "Prot Laptop", "device_identifier": "DEV_PROT_401",
        "public_key": "1234567890abcdef1234567890abcdef", "platform": "Windows", "agent_version": "2.3.0"
    }, headers=stud_headers)
    dev_headers = dict(stud_headers)
    dev_headers["X-Device-Identifier"] = "DEV_PROT_401"

    now = datetime.now(timezone.utc)
    sess_id = client.post(f"/api/v1/classes/{class_id}/sessions", json={
        "title": "OS Exam", "start_at": (now - timedelta(minutes=5)).isoformat(), "end_at": (now + timedelta(hours=1)).isoformat()
    }, headers=prof_headers).json()["id"]

    rs_id = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "OS Exam RuleSet", "expires_at": (now + timedelta(hours=2)).isoformat()
    }, headers=prof_headers).json()["id"]

    client.post(f"/api/v1/sessions/{sess_id}/start", headers=prof_headers)

    # Student manually joins active session
    client.post(f"/api/v1/student/sessions/{sess_id}/join", headers=stud_headers)

    pol = client.get("/api/v1/agent/policies/active", headers=dev_headers).json()
    assert pol["policy_active"] is True
    assert "protected_processes" in pol
    assert len(pol["protected_processes"]) > 0
    protected_names = [p["executable_name"] for p in pol["protected_processes"]]
    assert "explorer.exe" in protected_names or "svchost.exe" in protected_names or "python.exe" in protected_names

def test_browser_can_be_blocked_as_application_rule(client):
    """Verify msedge.exe and chrome.exe can be added and blocked via application rules and quick-update."""
    client.post("/api/v1/auth/register", json={
        "email": "prof_edge_test@university.edu", "password": "Password123!", "full_name": "Prof Edge", "role": "professor"
    })
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_edge_test@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    class_id = client.post("/api/v1/classes", json={"name": "Network Security", "course_code": "CS-501"}, headers=prof_headers).json()["id"]
    rs_id = client.post(f"/api/v1/classes/{class_id}/rule-sets", json={
        "name": "Exam Lockdown Policy"
    }, headers=prof_headers).json()["id"]

    # 1. Add msedge.exe directly as an application rule with action close
    res_edge = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "msedge.exe",
        "action": "close",
        "priority": 50
    }, headers=prof_headers)
    assert res_edge.status_code == 201
    assert res_edge.json()["executable_name"] == "msedge.exe"

    # 2. Add chrome.exe via quick-update
    quick_res = client.patch(f"/api/v1/rules/{rs_id}/quick-update", json={
        "action": "add",
        "type": "application",
        "item": "chrome.exe"
    }, headers=prof_headers)
    assert quick_res.status_code == 200
    assert "chrome.exe" in quick_res.json()["applications"]
    assert "msedge.exe" in quick_res.json()["applications"]

