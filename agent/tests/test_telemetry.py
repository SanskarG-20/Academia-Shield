"""
Unit tests for Telemetry Manager, sequence numbers, idempotency keys, and offline SQLite queueing.
"""

from agent.storage.db import LocalStorageDB
from agent.telemetry.telemetry_manager import TelemetryManager
from agent.api.client import APIClientAdapter

class MockAPIClient(APIClientAdapter):
    def __init__(self):
        super().__init__()
        self.sent_batches = []
        self.should_fail = False

    def send_telemetry_report(self, events):
        if self.should_fail:
            raise RuntimeError("Network offline simulated")
        self.sent_batches.append(events)
        return {"status": "ok", "data": {"logged": len(events)}}

def test_telemetry_idempotency_and_sequence(tmp_path):
    db = LocalStorageDB(db_path=str(tmp_path / "telemetry_test.db"))
    api = MockAPIClient()
    tm = TelemetryManager(db=db, api_client=api)

    # 1. Enqueue events while mock API is set to fail (offline period)
    api.should_fail = True
    tm.record_violation_event("web", "facebook.com", "blocked", session_id="sess_10")
    tm.record_violation_event("process", "steam.exe", "closed", session_id="sess_10")

    # Queue should contain 2 pending items
    batch = db.peek_telemetry_batch()
    assert len(batch) == 2
    assert batch[0]["seq_num"] == 1
    assert batch[1]["seq_num"] == 2
    assert batch[0]["idempotency_key"] != batch[1]["idempotency_key"]

    # 2. Connectivity restored (offline flush)
    api.should_fail = False
    flushed = tm.flush_queue()
    assert flushed == 2
    assert len(api.sent_batches) == 1

    # Queue should now be empty
    assert len(db.peek_telemetry_batch()) == 0
