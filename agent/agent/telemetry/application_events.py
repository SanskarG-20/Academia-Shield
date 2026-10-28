"""
Application Telemetry Event Builders matching Backend API Specs.

Formats privacy-minimized application violation events and health telemetry
payloads for submission via TelemetryManager to /api/v1/agent/telemetry/events.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from ..monitoring.enforcement import EnforcementResult

class ApplicationTelemetryBuilder:
    """Helper to build telemetry event dictionaries."""

    @staticmethod
    def build_violation_event(
        result: EnforcementResult,
        device_id: str,
        session_id: Optional[str] = None,
        policy_version: Optional[int] = None
    ) -> Dict[str, Any]:
        """Format an application violation event for API ingestion."""
        now_iso = datetime.now(timezone.utc).isoformat()
        event_id = str(uuid.uuid4())

        return {
            "event_id": event_id,
            "event_type": "application_violation",
            "device_id": device_id,
            "device_identifier": device_id,
            "session_id": session_id,
            "policy_version": policy_version,
            "rule_id": result.rule_id,
            "process_name": result.executable_name,
            "executable_name": result.executable_name,
            "resource": result.executable_name,
            "category": "Process",
            "action": result.action_result or "blocked",
            "action_requested": result.action_requested,
            "action_result": result.action_result,
            "is_violation": True,
            "isViolation": True,
            "occurred_at": now_iso,
            "payload": {
                "process_name": result.executable_name,
                "executable_name": result.executable_name,
                "resource": result.executable_name,
                "action": result.action_result or "blocked",
                "action_requested": result.action_requested,
                "action_result": result.action_result,
                "rule_id": result.rule_id,
                "reason": result.reason,
                "notification_shown": result.notification_shown,
                "is_violation": True,
                "isViolation": True
            }
        }

    @staticmethod
    def build_health_event(
        device_id: str,
        processes_scanned: int,
        scan_duration_ms: float,
        enforcement_active: bool,
        policy_version: Optional[int] = None,
        error_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Format an application monitor health event."""
        now_iso = datetime.now(timezone.utc).isoformat()
        event_id = str(uuid.uuid4())

        return {
            "event_id": event_id,
            "event_type": "application_monitor_health",
            "device_id": device_id,
            "device_identifier": device_id,
            "policy_version": policy_version,
            "occurred_at": now_iso,
            "payload": {
                "status": "healthy" if not error_code else "impaired",
                "processes_scanned": processes_scanned,
                "scan_duration_ms": round(scan_duration_ms, 2),
                "enforcement_active": enforcement_active,
                "policy_version": policy_version,
                "error_code": error_code
            }
        }
