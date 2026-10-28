"""
Telemetry & Audit Trail Manager for Academia Shield Agent.

Generates monotonic sequence numbers, idempotency keys, enqueues events to SQLite,
and processes offline retry queue uploads safely.
"""

import uuid
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from ..storage import LocalStorageDB
from ..api import APIClientAdapter

LOGGER = logging.getLogger(__name__)

class TelemetryManager:
    """Manages privacy-minimized audit logging and reliable offline queue uploading."""

    def __init__(self, db: Optional[LocalStorageDB] = None, api_client: Optional[APIClientAdapter] = None, engagement_tracker: Optional[Any] = None):
        self.db = db or LocalStorageDB()
        self.api_client = api_client or APIClientAdapter()
        self.engagement_tracker = engagement_tracker
        self._violation_cooldowns: Dict[str, float] = {}

    def record_violation_event(
        self,
        event_type: str,
        resource_name: str,
        action: str,
        session_id: Optional[str] = None,
        rule_id: Optional[str] = None,
        is_violation: bool = True
    ) -> bool:
        """
        Record privacy-minimized telemetry event with sequence number and idempotency key.
        Never collects file contents, keystrokes, screenshots, or credentials.
        """
        # Guard: lifecycle events like policy restoration are informational, not violations
        if event_type.lower() in ("policy_restored", "restored", "heartbeat", "state_transition", "session_end_restoration"):
            is_violation = False

        is_web = event_type.lower() in ("web", "dns_block", "domain_block", "website")
        is_proc = event_type.lower() in ("process", "application", "application_violation", "process_violation")

        # Centralized debounce: Ensure 1 app / 1 website / 1 pendrive = 1 violation event within 20s
        if is_violation:
            now_ts = time.time()
            clean_res = str(resource_name or "").strip().lower()
            if is_web and "." in clean_res:
                parts = clean_res.split(".")
                if len(parts) >= 2:
                    clean_res = ".".join(parts[-2:])
            cooldown_key = f"{event_type}_{clean_res}"
            last_ts = self._violation_cooldowns.get(cooldown_key, 0.0)
            if (now_ts - last_ts) < 20.0:
                LOGGER.debug("Debouncing duplicate violation for '%s' (occurred %.1fs ago)", cooldown_key, now_ts - last_ts)
                return True
            self._violation_cooldowns[cooldown_key] = now_ts

        now_iso = datetime.now(timezone.utc).isoformat()
        idempotency_key = str(uuid.uuid4())
        dev_id = getattr(self.api_client.config, "device_id", "local_agent_device")

        payload = {
            "timestamp": now_iso,
            "event_id": idempotency_key,
            "event_type": event_type,
            "device_id": dev_id,
            "device_identifier": dev_id,
            "domain": resource_name if is_web else None,
            "application": resource_name if is_proc else None,
            "executable_name": resource_name if is_proc else None,
            "category": "Process" if is_proc else "Web",
            "action": action,
            "action_result": action,
            "action_requested": action,
            "session_id": session_id,
            "rule_id": rule_id,
            "student_id": dev_id,
            "is_violation": is_violation,
            "isViolation": is_violation,
            "resource": resource_name,
            "payload": {
                "domain": resource_name if is_web else None,
                "application": resource_name if is_proc else None,
                "executable_name": resource_name if is_proc else None,
                "action": action,
                "action_result": action,
                "is_violation": is_violation,
                "rule_id": rule_id
            }
        }

        # Automatically update engagement tracker if active and is a genuine violation
        if is_violation and self.engagement_tracker and getattr(self.engagement_tracker, "is_active", False):
            try:
                self.engagement_tracker.record_violation(event_type)
            except Exception as err:
                LOGGER.debug("Engagement tracker violation record error: %s", err)

        # Enqueue locally in SQLite queue first
        success = self.db.enqueue_telemetry(idempotency_key, event_type, payload)
        
        # Attempt immediate push
        self.flush_queue()
        return success

    def flush_queue(self, max_items: int = 50) -> int:
        """Upload pending telemetry batch to backend."""
        batch = self.db.peek_telemetry_batch(limit=max_items)
        if not batch:
            return 0

        # Filter internal sqlite queue metadata before sending to API
        payload_batch = []
        queue_ids = []
        for item in batch:
            q_id = item.get("_queue_id")
            if q_id:
                queue_ids.append(q_id)
            clean_item = dict(item)
            clean_item.pop("_queue_id", None)
            clean_item.pop("_retry_count", None)
            payload_batch.append(clean_item)

        try:
            res = self.api_client.send_telemetry_report(payload_batch)
            if res.get("status") == "ok":
                self.db.remove_telemetry_items(queue_ids)
                LOGGER.debug("Flushed %s telemetry items from queue", len(queue_ids))
                return len(queue_ids)
            else:
                self.db.increment_telemetry_retries(queue_ids)
        except Exception as err:
            LOGGER.debug("Offline or error during telemetry upload (%s); retained in SQLite queue", err)
            self.db.increment_telemetry_retries(queue_ids)
        
        return 0
