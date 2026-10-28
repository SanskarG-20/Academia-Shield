"""
Telemetry Queue and Flush Worker for Academia Shield Agent.
Maintains bounded offline SQLite FIFO queue with unique UUID event idempotency.
"""

import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from ..storage.database import LocalDatabase
from ..api.client import ApiClient

logger = logging.getLogger(__name__)

class TelemetryManager:
    """
    Manages telemetry events with offline buffering and reliable delivery.
    """

    def __init__(
        self,
        db: LocalDatabase,
        api_client: Optional[ApiClient] = None,
        device_id: Optional[str] = None,
        device_identifier: Optional[str] = None
    ):
        self.db = db
        self.api_client = api_client
        self.device_id = device_id
        self.device_identifier = device_identifier

    def record_event(
        self,
        event_type: str,
        session_id: Optional[str] = None,
        policy_version: Optional[int] = None,
        rule_id: Optional[str] = None,
        executable_name: Optional[str] = None,
        action_requested: Optional[str] = None,
        action_result: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create and enqueue an idempotent telemetry event.
        Returns the generated event_id (UUID4).
        """
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "device_id": self.device_id,
            "device_identifier": self.device_identifier,
            "session_id": session_id,
            "policy_version": policy_version,
            "rule_id": rule_id,
            "executable_name": executable_name,
            "action_requested": action_requested,
            "action_result": action_result,
            "payload": payload or {},
            "occurred_at": datetime.now(timezone.utc).isoformat()
        }

        self.db.enqueue_telemetry(event_id, event_type, event)
        logger.debug(f"Enqueued telemetry event [{event_type}] with id {event_id}")
        return event_id

    def flush_pending(self, batch_size: int = 50) -> Dict[str, Any]:
        """
        Flush pending offline telemetry events to backend.
        """
        if not self.api_client:
            return {"flushed": 0, "status": "no_api_client"}

        events = self.db.get_pending_telemetry(limit=batch_size)
        if not events:
            return {"flushed": 0, "status": "empty"}

        event_ids = [e["event_id"] for e in events if "event_id" in e]

        resp = self.api_client.post("/api/v1/agent/telemetry/events", json=events)
        if resp.get("status_code") in (200, 201) or resp.get("ok"):
            self.db.remove_telemetry_batch(event_ids)
            logger.info(f"Successfully flushed {len(event_ids)} telemetry events to backend")
            return {"flushed": len(event_ids), "status": "success"}
        else:
            self.db.increment_telemetry_attempts(event_ids)
            logger.warning(f"Telemetry flush failed (status: {resp.get('status_code')})")
            return {"flushed": 0, "status": "failed", "error": resp.get("error")}
