"""
Tests for Versioned Policy Management, SHA-256 Integrity Hashing, Security Guardrails, and RBAC.
"""

import pytest

def get_auth_headers(client, email, name, role="professor"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "Password123!", "full_name": name, "role": role
    })
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    token = res.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}

def test_versioned_policy_lifecycle_and_integrity_hashing(client):
    prof_headers = get_auth_headers(client, "prof_policy@university.edu", "Prof Policy")

    # 2. Create Batch
    b_res = client.post("/api/v1/batches", json={"name": "Cybersecurity Policy Lab"}, headers=prof_headers)
    assert b_res.status_code == 201
    batch_id = b_res.json()["id"]

    # 3. Create Batch Policy Rule Set (v1)
    rs_res = client.post(f"/api/v1/batches/{batch_id}/rule-sets", json={"name": "Exam Lockdown Policy v1"}, headers=prof_headers)
    assert rs_res.status_code == 201
    rs = rs_res.json()
    assert rs["version"] == 1
    assert rs["is_active"] is True
    initial_hash = rs["integrity_hash"]
    assert len(initial_hash) == 64  # SHA-256 hex string
    rs_id = rs["id"]

    # 4. Publish v1
    pub1 = client.post(f"/api/v1/rule-sets/{rs_id}/publish", headers=prof_headers)
    assert pub1.status_code == 200

    # 5. Mutating published policy branches new draft version 2
    d_res = client.post(f"/api/v1/rule-sets/{rs_id}/domain-rules", json={
        "domain_pattern": "cheat-engine.org",
        "rule_type": "domain",
        "action": "block",
        "priority": 10
    }, headers=prof_headers)
    assert d_res.status_code == 201

    all_rs = client.get(f"/api/v1/batches/{batch_id}/rule-sets", headers=prof_headers).json()
    rs_v2 = next(r for r in all_rs if r["version"] == 2)
    assert rs_v2["version"] == 2
    assert rs_v2["integrity_hash"] != initial_hash
    hash_v2 = rs_v2["integrity_hash"]
    rs2_id = rs_v2["id"]

    # Publish v2
    pub2 = client.post(f"/api/v1/rule-sets/{rs2_id}/publish", headers=prof_headers)
    assert pub2.status_code == 200

    # 6. Mutating published v2 branches new draft version 3
    a_res = client.post(f"/api/v1/rule-sets/{rs2_id}/application-rules", json={
        "executable_name": "discord.exe",
        "action": "close",
        "priority": 10,
        "cooldown_seconds": 5
    }, headers=prof_headers)
    assert a_res.status_code == 201

    all_rs2 = client.get(f"/api/v1/batches/{batch_id}/rule-sets", headers=prof_headers).json()
    rs_v3 = next(r for r in all_rs2 if r["version"] == 3)
    assert rs_v3["version"] == 3
    assert rs_v3["integrity_hash"] != hash_v2

def test_security_guardrails_rejections(client):
    prof_headers = get_auth_headers(client, "prof_guardrail@university.edu", "Prof Guard")

    b_res = client.post("/api/v1/batches", json={"name": "Guardrail Test Batch"}, headers=prof_headers).json()
    batch_id = b_res["id"]

    rs = client.post(f"/api/v1/batches/{batch_id}/rule-sets", json={"name": "Strict Guardrails Policy"}, headers=prof_headers).json()
    rs_id = rs["id"]

    # 1. Reject Shell Interpreters (cmd.exe, powershell.exe) -> 400 Bad Request
    cmd_res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "cmd.exe", "action": "close"
    }, headers=prof_headers)
    assert cmd_res.status_code == 400
    assert "Shell commands" in cmd_res.json()["message"]

    ps_res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "powershell.exe", "action": "close"
    }, headers=prof_headers)
    assert ps_res.status_code == 400

    # 2. Reject Script Files (.bat, .ps1) -> 400 Bad Request
    script_res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "hack_script.bat", "action": "close"
    }, headers=prof_headers)
    assert script_res.status_code == 400

    # 3. Reject Protected System Process (explorer.exe, svchost.exe, acad_agent.exe) -> 400 Bad Request
    sys_proc_res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "explorer.exe", "action": "close"
    }, headers=prof_headers)
    assert sys_proc_res.status_code == 400
    assert "protected system process" in sys_proc_res.json()["message"]

    agent_proc_res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "acad_agent.exe", "action": "close"
    }, headers=prof_headers)
    assert agent_proc_res.status_code == 400

    # 4. Reject Invalid / Network Restrict Action -> 400/422 Bad Request
    net_res = client.post(f"/api/v1/rule-sets/{rs_id}/application-rules", json={
        "executable_name": "chrome.exe", "action": "network_restrict"
    }, headers=prof_headers)
    assert net_res.status_code in (400, 422)

def test_unowned_batch_policy_rbac(client):
    p1_headers = get_auth_headers(client, "p1_pol@univ.edu", "P1")
    p2_headers = get_auth_headers(client, "p2_pol@univ.edu", "P2")

    # P1 creates Batch 1
    b1 = client.post("/api/v1/batches", json={"name": "P1 Batch"}, headers=p1_headers).json()

    # P2 tries to create policy for P1's batch -> 403 Forbidden!
    forbidden_res = client.post(f"/api/v1/batches/{b1['id']}/rule-sets", json={"name": "Rogue Policy"}, headers=p2_headers)
    assert forbidden_res.status_code == 403
    assert "Only batch owner" in forbidden_res.json()["message"]
