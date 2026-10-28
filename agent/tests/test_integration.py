"""
Integration tests for Agent Authentication, Device Enrollment, Policy Sync, Heartbeat, and Telemetry against real FastAPI test environment.
"""

import sys
import os
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app
from app.core.database import engine, ensure_schema_up_to_date
from agent.auth.crypto import Ed25519KeyManager
from agent.auth.token_manager import TokenManager
from agent.auth.keyring_store import SecureStorageManager
from agent.api.client import APIClientAdapter

client = TestClient(app)

def test_integration_enrollment_and_policy(tmp_path):
    ensure_schema_up_to_date(engine)
    # 1. Register student account
    reg_payload = {
        "email": "student_test_agent@university.edu",
        "password": "Password123!",
        "full_name": "Test Agent Student",
        "role": "student"
    }
    reg_resp = client.post("/api/v1/auth/register", json=reg_payload)
    if reg_resp.status_code in (400, 409):
        login_resp = client.post("/api/v1/auth/login", json={"email": reg_payload["email"], "password": reg_payload["password"]})
        tokens = login_resp.json()
    else:
        assert reg_resp.status_code == 201
        login_resp = client.post("/api/v1/auth/login", json={"email": reg_payload["email"], "password": reg_payload["password"]})
        tokens = login_resp.json()

    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # 2. Device Keypair Generation & Registration
    key_mgr = Ed25519KeyManager()
    priv_pem, pub_hex = key_mgr.get_private_key_pem(), key_mgr.get_public_key_hex()

    enroll_payload = {
        "device_identifier": "test_device_node_01",
        "device_name": "student-laptop-win11",
        "public_key": pub_hex,
        "platform": "Windows 11",
        "agent_version": "2.3.0"
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    enroll_resp = client.post("/api/v1/agent/devices/register", json=enroll_payload, headers=headers)
    assert enroll_resp.status_code == 201
    assert "device_id" in enroll_resp.json()

    # 3. Heartbeat
    hb_resp = client.post("/api/v1/agent/heartbeat", json={
        "device_identifier": "test_device_node_01",
        "agent_version": "2.3.0",
        "health_state": "healthy"
    }, headers=headers)
    assert hb_resp.status_code == 200
    assert hb_resp.json()["status"] == "online"

    # 4. Active Policy Sync
    policy_resp = client.get("/api/v1/agent/policies/active", headers={"Authorization": f"Bearer {access_token}", "X-Device-Identifier": "test_device_node_01"})
    assert policy_resp.status_code == 200
    p_data = policy_resp.json()
    assert "policy_active" in p_data

    # 5. Telemetry Report
    import uuid
    from datetime import datetime, timezone
    telemetry_payload = [{
        "event_id": f"evt_integ_{uuid.uuid4().hex[:8]}",
        "device_id": enroll_resp.json()["device_id"],
        "event_type": "application_access",
        "resource_name": "notepad.exe",
        "action": "allowed",
        "occurred_at": datetime.now(timezone.utc).isoformat()
    }]
    telemetry_resp = client.post("/api/v1/agent/telemetry/events", json=telemetry_payload, headers=headers)
    assert telemetry_resp.status_code == 200
    assert telemetry_resp.json()["status"] == "ok"
