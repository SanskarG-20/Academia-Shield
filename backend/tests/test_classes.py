"""
Tests for Classes API: Professor Ownership, Student Enrollment, and Isolation.
"""

def test_class_creation_and_student_enrollment(client):
    # Register Professor
    prof_res = client.post("/api/v1/auth/register", json={
        "email": "prof_smith@university.edu",
        "password": "Password123!",
        "full_name": "Dr. Smith",
        "role": "professor"
    })
    assert prof_res.status_code == 201
    prof_token = client.post("/api/v1/auth/login", json={"email": "prof_smith@university.edu", "password": "Password123!"}).json()["access_token"]

    # Register Student
    stud_res = client.post("/api/v1/auth/register", json={
        "email": "bob_student@university.edu",
        "password": "Password123!",
        "full_name": "Bob Student",
        "role": "student"
    })
    assert stud_res.status_code == 201
    stud_token = client.post("/api/v1/auth/login", json={"email": "bob_student@university.edu", "password": "Password123!"}).json()["access_token"]

    # 1. Professor creates class
    headers_prof = {"Authorization": f"Bearer {prof_token}"}
    class_res = client.post("/api/v1/classes", json={
        "name": "Distributed Systems",
        "course_code": "CS-401",
        "description": "Advanced Networking & Systems"
    }, headers=headers_prof)
    assert class_res.status_code == 201
    class_id = class_res.json()["id"]

    # 2. Student cannot create class (RBAC check)
    headers_stud = {"Authorization": f"Bearer {stud_token}"}
    fail_res = client.post("/api/v1/classes", json={"name": "Fake Class", "course_code": "FC-101"}, headers=headers_stud)
    assert fail_res.status_code == 403

    # 3. Professor enrolls student
    add_res = client.post(f"/api/v1/classes/{class_id}/students", json={"student_email_or_id": "bob_student@university.edu"}, headers=headers_prof)
    assert add_res.status_code == 200
    assert add_res.json()["status"] == "enrolled"

    # 4. Student can now view enrolled class
    stud_classes = client.get("/api/v1/classes", headers=headers_stud).json()
    assert len(stud_classes) == 1
    assert stud_classes[0]["id"] == class_id
