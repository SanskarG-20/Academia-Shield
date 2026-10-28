"""
Tests for Local SQLite Storage, FIFO Bounded Telemetry Queue, and Audit Logging.
"""

import pytest
import os
import tempfile
from agent.core.storage.database import LocalDatabase
from agent.core.telemetry.queue import TelemetryManager

@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_telemetry.db")
    return LocalDatabase(db_path)

def test_telemetry_enqueue_and_bounded_fifo(temp_db):
    # Test enqueue with small bound (e.g. max 5)
    for i in range(10):
        temp_db.enqueue_telemetry(
            event_id=f"evt_{i}",
            event_type="app_blocked",
            payload={"index": i},
            max_queue_size=5
        )

    pending = temp_db.get_pending_telemetry(limit=20)
    assert len(pending) <= 5
    # Ensure oldest were evicted and newest retained
    indexes = [e.get("index") for e in pending]
    assert 9 in indexes
    assert 0 not in indexes

def test_telemetry_manager_idempotency_and_batch_removal(temp_db):
    mgr = TelemetryManager(db=temp_db, device_id="dev_1", device_identifier="mac_hash_1")
    
    id1 = mgr.record_event(event_type="dns_query", payload={"query": "test.com"})
    id2 = mgr.record_event(event_type="heartbeat", payload={"status": "ok"})
    assert id1 != id2

    pending = temp_db.get_pending_telemetry()
    assert len(pending) == 2

    # Remove batch
    temp_db.remove_telemetry_batch([id1])
    remaining = temp_db.get_pending_telemetry()
    assert len(remaining) == 1
    assert remaining[0]["event_id"] == id2

def test_local_audit_log_recording(temp_db):
    temp_db.write_audit_log("AUTH", "LOGIN_SUCCESS", {"user": "student1@univ.edu"})
    temp_db.write_audit_log("POLICY", "ENFORCEMENT_STARTED", {"policy_id": "pol_abc"})

    logs = temp_db.get_recent_audit_logs(limit=10)
    assert len(logs) == 2
    assert logs[0]["action"] == "ENFORCEMENT_STARTED"
    assert logs[1]["action"] == "LOGIN_SUCCESS"
