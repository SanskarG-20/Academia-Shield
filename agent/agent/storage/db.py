"""
SQLite Local Storage Manager for Academia Shield Agent.

Provides offline resilience, local policy persistence, sequence numbering, and offline telemetry queueing.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

LOGGER = logging.getLogger(__name__)

class LocalStorageDB:
    """Manages SQLite database for verified policy cache, telemetry queue, and audit logs."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            storage_dir = os.path.expanduser("~/.academia_shield")
            os.makedirs(storage_dir, exist_ok=True)
            db_path = os.path.join(storage_dir, "agent_storage.db")
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Policy Cache Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS policy_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_version INTEGER NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Telemetry Queue Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seq_num INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Key-Value Metadata Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # -------------------------------------------------------------------------
    # Policy Storage
    # -------------------------------------------------------------------------
    def save_policy(self, policy_data: Dict[str, Any]) -> bool:
        """Save verified policy object locally."""
        try:
            raw_ver = policy_data.get("policy_version")
            if raw_ver is None:
                raw_ver = policy_data.get("version", 0)
            version = int(raw_ver or 0)
            issued_at = str(policy_data.get("issued_at") or "")
            expires_at = str(policy_data.get("expires_at") or "")
            sha256 = str(policy_data.get("sha256") or policy_data.get("integrity_hash") or "")
            payload_str = json.dumps(policy_data)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM policy_cache")
                cursor.execute("""
                    INSERT INTO policy_cache (policy_version, issued_at, expires_at, sha256, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (version, issued_at, expires_at, sha256, payload_str))
                conn.commit()
            return True
        except Exception as err:
            LOGGER.error("Failed to save policy to SQLite: %s", err)
            return False

    def get_latest_policy(self) -> Optional[Dict[str, Any]]:
        """Retrieve latest cached policy from SQLite."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT payload_json FROM policy_cache ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return json.loads(row["payload_json"])
        except Exception as err:
            LOGGER.error("Failed retrieving policy from SQLite: %s", err)
        return None

    # -------------------------------------------------------------------------
    # Telemetry Queue & Sequence Numbering
    # -------------------------------------------------------------------------
    def get_next_sequence_number(self) -> int:
        """Atomically generate monotonic sequence number for telemetry events."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'last_seq_num'")
            row = cursor.fetchone()
            current_seq = int(row["value"]) if row else 0
            next_seq = current_seq + 1
            cursor.execute("""
                INSERT OR REPLACE INTO metadata (key, value, updated_at)
                VALUES ('last_seq_num', ?, CURRENT_TIMESTAMP)
            """, (str(next_seq),))
            conn.commit()
            return next_seq

    def enqueue_telemetry(self, idempotency_key: str, event_type: str, payload: Dict[str, Any]) -> bool:
        """Enqueue telemetry event for offline delivery."""
        try:
            seq_num = self.get_next_sequence_number()
            payload["seq_num"] = seq_num
            payload["idempotency_key"] = idempotency_key
            payload_str = json.dumps(payload)

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO telemetry_queue (seq_num, idempotency_key, event_type, payload_json)
                    VALUES (?, ?, ?, ?)
                """, (seq_num, idempotency_key, event_type, payload_str))
                conn.commit()
            return True
        except Exception as err:
            LOGGER.error("Failed to enqueue telemetry event: %s", err)
            return False

    def peek_telemetry_batch(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch pending telemetry events from queue."""
        events = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, seq_num, idempotency_key, event_type, payload_json, retry_count
                    FROM telemetry_queue ORDER BY id ASC LIMIT ?
                """, (limit,))
                for row in cursor.fetchall():
                    item = json.loads(row["payload_json"]) if row["payload_json"] else {}
                    item["_queue_id"] = row["id"]
                    item["_retry_count"] = row["retry_count"]
                    if "event_id" not in item:
                        item["event_id"] = row["idempotency_key"]
                    if "event_type" not in item:
                        item["event_type"] = row["event_type"]
                    if "occurred_at" not in item:
                        item["occurred_at"] = item.get("timestamp") or datetime.now(timezone.utc).isoformat()
                    events.append(item)
        except Exception as err:
            LOGGER.error("Error reading telemetry queue: %s", err)
        return events

    def remove_telemetry_items(self, queue_ids: List[int]) -> bool:
        """Remove successfully uploaded events from offline queue."""
        if not queue_ids:
            return True
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join(["?"] * len(queue_ids))
                cursor.execute(f"DELETE FROM telemetry_queue WHERE id IN ({placeholders})", queue_ids)
                conn.commit()
            return True
        except Exception as err:
            LOGGER.error("Failed removing telemetry items: %s", err)
            return False

    def increment_telemetry_retries(self, queue_ids: List[int]) -> None:
        """Increment retry count for failed batch items."""
        if not queue_ids:
            return
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ",".join(["?"] * len(queue_ids))
                cursor.execute(f"UPDATE telemetry_queue SET retry_count = retry_count + 1 WHERE id IN ({placeholders})", queue_ids)
                conn.commit()
        except Exception as err:
            LOGGER.error("Failed updating retry counts: %s", err)

    def set_metadata(self, key: str, value: str) -> None:
        """Set metadata value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, value))
            conn.commit()

    def get_metadata(self, key: str) -> Optional[str]:
        """Get metadata value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None
