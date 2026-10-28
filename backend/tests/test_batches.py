"""
Tests for Secure Batch Management API & RBAC Rules.
"""

import pytest

def test_batch_lifecycle_and_rbac(client):
    # 1. Register Professor Alpha, Student A, and Student B
    prof_token = client.post("/api/v1/auth/register", json={
        "email": "prof_batch@university.edu", "password": "Password123!", "full_name": "Prof Batch", "role": "professor"
    }).json()
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_batch@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    student_a_token = client.post("/api/v1/auth/register", json={
        "email": "student_a@university.edu", "password": "Password123!", "full_name": "Student A", "role": "student"
    }).json()
    student_a_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'student_a@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    student_b_token = client.post("/api/v1/auth/register", json={
        "email": "student_b@university.edu", "password": "Password123!", "full_name": "Student B", "role": "student"
    }).json()
    student_b_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'student_b@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    # 2. Professor creates Batch 1 and Batch 2
    b1_res = client.post("/api/v1/batches", json={"name": "Computer Networks B1", "description": "Morning Section"}, headers=prof_headers)
    assert b1_res.status_code == 201
    b1_data = b1_res.json()
    assert "batch_code" in b1_data
    assert len(b1_data["batch_code"]) == 6
    b1_id = b1_data["id"]
    b1_code = b1_data["batch_code"]

    b2_res = client.post("/api/v1/batches", json={"name": "Cyber Security B2", "description": "Afternoon Section"}, headers=prof_headers)
    assert b2_res.status_code == 201
    b2_data = b2_res.json()
    b2_id = b2_data["id"]
    b2_code = b2_data["batch_code"]

    # 3. Student A joins Batch 1 using code
    join_a_res = client.post("/api/v1/student/batches/join", json={"batch_code": b1_code}, headers=student_a_headers)
    assert join_a_res.status_code == 200
    joined_a_data = join_a_res.json()
    assert joined_a_data["id"] == b1_id
    # SECURITY RULE: Student response MUST NOT contain batch_code
    assert "batch_code" not in joined_a_data

    # 4. Student B joins Batch 2 using code
    join_b_res = client.post("/api/v1/student/batches/join", json={"batch_code": b2_code}, headers=student_b_headers)
    assert join_b_res.status_code == 200
    joined_b_data = join_b_res.json()
    assert joined_b_data["id"] == b2_id

    # 5. Verify Student A's batch list contains ONLY Batch 1
    stud_a_batches = client.get("/api/v1/student/batches", headers=student_a_headers).json()
    assert len(stud_a_batches) == 1
    assert stud_a_batches[0]["id"] == b1_id
    # Check that batch_code is NOT present in list
    assert "batch_code" not in stud_a_batches[0]

    # 6. Verify Student B's batch list contains ONLY Batch 2
    stud_b_batches = client.get("/api/v1/student/batches", headers=student_b_headers).json()
    assert len(stud_b_batches) == 1
    assert stud_b_batches[0]["id"] == b2_id

    # 7. Student A tries to access Student B's batch (Batch 2) directly -> 403 Forbidden!
    unjoined_access_res = client.get(f"/api/v1/student/batches/{b2_id}", headers=student_a_headers)
    assert unjoined_access_res.status_code == 403
    assert "Access denied" in unjoined_access_res.json()["message"]

    # 8. Student A accesses their own joined batch (Batch 1) -> 200 OK
    joined_access_res = client.get(f"/api/v1/student/batches/{b1_id}", headers=student_a_headers)
    assert joined_access_res.status_code == 200
    assert joined_access_res.json()["id"] == b1_id

    # 9. Professor views members for Batch 1 -> returns Student A
    members_res = client.get(f"/api/v1/batches/{b1_id}/members", headers=prof_headers)
    assert members_res.status_code == 200
    members = members_res.json()
    assert len(members) == 1
    assert members[0]["student_email"] == "student_a@university.edu"

    # 10. Student CANNOT view members endpoint -> 403 Forbidden
    student_members_res = client.get(f"/api/v1/batches/{b1_id}/members", headers=student_a_headers)
    assert student_members_res.status_code == 403

def test_batch_code_regeneration(client):
    prof_token = client.post("/api/v1/auth/register", json={
        "email": "prof_regen@university.edu", "password": "Password123!", "full_name": "Prof Regen", "role": "professor"
    }).json()
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_regen@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    # Create batch
    b_res = client.post("/api/v1/batches", json={"name": "Regen Test Batch"}, headers=prof_headers)
    b_data = b_res.json()
    old_code = b_data["batch_code"]

    # Regenerate code
    regen_res = client.post(f"/api/v1/batches/{b_data['id']}/regenerate-code", headers=prof_headers)
    assert regen_res.status_code == 200
    new_code = regen_res.json()["batch_code"]
    assert new_code != old_code

    # Old code fails to join
    stud_token = client.post("/api/v1/auth/register", json={
        "email": "student_regen@university.edu", "password": "Password123!", "full_name": "Student Regen", "role": "student"
    }).json()
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'student_regen@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    old_join = client.post("/api/v1/student/batches/join", json={"batch_code": old_code}, headers=stud_headers)
    assert old_join.status_code == 404

    # New code succeeds
    new_join = client.post("/api/v1/student/batches/join", json={"batch_code": new_code}, headers=stud_headers)
    assert new_join.status_code == 200
