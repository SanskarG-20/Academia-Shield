"""
Local SQLite Storage for Cache, Telemetry Queue, and Audit Logs.
"""

import os
import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DEFAULT_DB_DIR = os.path.expanduser("~/.academiashield")
DB_FILE = "agent_local_store.db"

class LocalDatabase:
    """
    Manages local SQLite database for offline telemetry FIFO queue,
    verified policy cache, and local audit logs.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = db_path
        else:
            os.makedirs(DEFAULT_DB_DIR, exist_ok=True)
            self.db_path = os.path.join(DEFAULT_DB_DIR, DB_FILE)
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Telemetry Queue
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS offline_telemetry (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    attempts INTEGER DEFAULT 0
                )
            """)
            # Policy Cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS policy_cache (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    policy_version INTEGER,
                    policy_data_json TEXT NOT NULL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            # Local Audit Logs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS local_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details_json TEXT
                )
            """)
            conn.commit()

    # Telemetry Queue Operations
    def enqueue_telemetry(self, event_id: str, event_type: str, payload: Dict[str, Any], max_queue_size: int = 1000):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Enforce bounded queue size (evict oldest if full)
            cursor.execute("SELECT COUNT(*) FROM offline_telemetry")
            count = cursor.fetchone()[0]
            if count >= max_queue_size:
                cursor.execute("""
                    DELETE FROM offline_telemetry WHERE event_id IN (
                        SELECT event_id FROM offline_telemetry ORDER BY created_at ASC LIMIT ?
                    )
                """, (count - max_queue_size + 1,))

            cursor.execute("""
                INSERT OR REPLACE INTO offline_telemetry (event_id, event_type, payload_json, attempts)
                VALUES (?, ?, ?, 0)
            """, (event_id, event_type, json.dumps(payload)))
            conn.commit()

    def get_pending_telemetry(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT event_id, event_type, payload_json, attempts FROM offline_telemetry ORDER BY created_at ASC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            events = []
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"])
                    payload["event_id"] = row["event_id"]
                    payload["event_type"] = row["event_type"]
                    events.append(payload)
                except Exception:
                    continue
            return events

    def remove_telemetry_batch(self, event_ids: List[str]):
        if not event_ids:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in event_ids)
            cursor.execute(f"DELETE FROM offline_telemetry WHERE event_id IN ({placeholders})", event_ids)
            conn.commit()

    def increment_telemetry_attempts(self, event_ids: List[str]):
        if not event_ids:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in event_ids)
            cursor.execute(f"UPDATE offline_telemetry SET attempts = attempts + 1 WHERE event_id IN ({placeholders})", event_ids)
            conn.commit()

    # Policy Cache Operations
    def save_cached_policy(self, session_id: str, policy_version: int, policy_data: Dict[str, Any], expires_at: Optional[str] = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO policy_cache (id, session_id, policy_version, policy_data_json, expires_at)
                VALUES ('active_policy', ?, ?, ?, ?)
            """, (session_id, policy_version, json.dumps(policy_data), expires_at))
            conn.commit()

    def get_cached_policy(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT session_id, policy_version, policy_data_json, expires_at FROM policy_cache WHERE id = 'active_policy'")
            row = cursor.fetchone()
            if row:
                try:
                    data = json.loads(row["policy_data_json"])
                    return data
                except Exception:
                    return None
        return None

    def clear_cached_policy(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM policy_cache WHERE id = 'active_policy'")
            conn.commit()

    # Audit Logging
    def write_audit_log(self, category: str, action: str, details: Optional[Dict[str, Any]] = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO local_audit_log (category, action, details_json)
                VALUES (?, ?, ?)
            """, (category, action, json.dumps(details or {})))
            conn.commit()

    def get_recent_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, timestamp, category, action, details_json FROM local_audit_log ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            logs = []
            for row in rows:
                try:
                    details = json.loads(row["details_json"])
                except Exception:
                    details = {}
                logs.append({
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "category": row["category"],
                    "action": row["action"],
                    "details": details
                })
            return logs
