"""
Tests for Role-Based Access Control (RBAC) across Admin, Professor, Student, and Agent roles.
"""

def test_rbac_permissions(client):
    # Register Admin, Professor, and Student
    admin_token = client.post("/api/v1/auth/register", json={
        "email": "admin_sys@university.edu", "password": "Password123!", "full_name": "Admin User", "role": "admin"
    }).json()
    admin_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'admin_sys@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    prof_token = client.post("/api/v1/auth/register", json={
        "email": "prof_alpha@university.edu", "password": "Password123!", "full_name": "Prof Alpha", "role": "professor"
    }).json()
    prof_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'prof_alpha@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    stud_token = client.post("/api/v1/auth/register", json={
        "email": "stud_beta@university.edu", "password": "Password123!", "full_name": "Student Beta", "role": "student"
    }).json()
    stud_headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'stud_beta@university.edu', 'password': 'Password123!'}).json()['access_token']}"}

    # 1. Student cannot access Dashboard APIs (403 Forbidden)
    dash_res = client.get("/api/v1/dashboard/live", headers=stud_headers)
    assert dash_res.status_code == 403

    # 2. Professor CAN access Dashboard APIs (200 OK)
    prof_dash_res = client.get("/api/v1/dashboard/live", headers=prof_headers)
    assert prof_dash_res.status_code == 200

    # 3. Admin CAN access Dashboard APIs (200 OK)
    admin_dash_res = client.get("/api/v1/dashboard/live", headers=admin_headers)
    assert admin_dash_res.status_code == 200
