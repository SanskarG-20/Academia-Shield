"""
Tests for Auth API: Password Hashing, Login, JWT Expiry, Refresh Token Rotation, and Logout.
"""

import pytest
from app.core.security import hash_password, verify_password

def test_password_hashing():
    pwd = "MySecretPassword123!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False

def test_auth_registration_and_login(client):
    # 1. Register student
    reg_payload = {
        "email": "student_b21@university.edu",
        "password": "Password123!",
        "full_name": "Alice Student",
        "role": "student"
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    user_data = reg_res.json()
    assert user_data["email"] == reg_payload["email"]
    assert "password_hash" not in user_data

    # 2. Login
    login_payload = {
        "email": reg_payload["email"],
        "password": reg_payload["password"]
    }
    login_res = client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["role"] == "student"

    # 3. Fetch profile
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == reg_payload["email"]

    # 4. Refresh token rotation
    ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert ref_res.status_code == 200
    new_tokens = ref_res.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # Old refresh token MUST now be revoked and rejected
    old_ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert old_ref_res.status_code == 401

    # 5. Logout
    logout_res = client.post("/api/v1/auth/logout", json={"refresh_token": new_tokens["refresh_token"]}, headers={"Authorization": f"Bearer {new_tokens['access_token']}"})
    assert logout_res.status_code == 200

    # Revoked token cannot be used again
    logout_ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert logout_ref_res.status_code == 401

def test_invalid_login(client):
    res = client.post("/api/v1/auth/login", json={"email": "nonexistent@university.edu", "password": "BadPassword"})
    assert res.status_code == 401

def test_invalid_password(client):
    # Register user
    reg = client.post("/api/v1/auth/register", json={
        "email": "user_invalid_pwd@university.edu", "password": "CorrectPassword123!", "full_name": "Test User", "role": "student"
    })
    assert reg.status_code == 201

    # Login with wrong password
    res = client.post("/api/v1/auth/login", json={"email": "user_invalid_pwd@university.edu", "password": "WrongPassword123!"})
    assert res.status_code == 401
    assert "Invalid institutional credentials" in res.json()["message"]

def test_token_expiry(client):
    from datetime import timedelta
    from app.core.security import create_access_token

    # Create expired access token (-1 minute)
    expired_token = create_access_token(
        data={"sub": "some_user_id", "role": "student"},
        expires_delta=timedelta(minutes=-1)
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 401
    assert "expired" in res.json()["message"].lower() or "invalid" in res.json()["message"].lower()

def test_login_rate_limiting(client):
    email = "rate_limit_test@university.edu"
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "RealPassword123!", "full_name": "Rate Limit User", "role": "student"
    })

    # Fail 5 times sequentially
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword!"})

    # 6th attempt must trigger 429 Too Many Requests
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword!"})
    assert res.status_code == 429
    assert "too many failed login attempts" in res.json()["message"].lower()
