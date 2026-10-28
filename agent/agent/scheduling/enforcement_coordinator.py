"""
Idempotent Enforcement Coordinator for Academia Shield Local Agent.

Connects custom schedule evaluator state transitions to DNS enforcement,
process monitoring, and reliable telemetry dispatch.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from .server_clock import ServerClock
from .session_evaluator import AgentSessionEvaluator
from ..policy.policy_manager import VerifiedPolicy
from ..monitoring.process_monitor import ProcessMonitor
from ..telemetry.telemetry_manager import TelemetryManager

LOGGER = logging.getLogger(__name__)

class EnforcementCoordinator:
    """Orchestrates DNS and process monitoring enforcement based on scheduler state."""

    def __init__(
        self,
        server_clock: Optional[ServerClock] = None,
        session_evaluator: Optional[AgentSessionEvaluator] = None,
        process_monitor: Optional[ProcessMonitor] = None,
        telemetry_manager: Optional[TelemetryManager] = None,
        dns_controller: Optional[Any] = None
    ):
        self.server_clock = server_clock or ServerClock()
        self.session_evaluator = session_evaluator or AgentSessionEvaluator(server_clock=self.server_clock)
        self.process_monitor = process_monitor or ProcessMonitor()
        self.telemetry_manager = telemetry_manager or TelemetryManager()
        self.dns_controller = dns_controller

        self.current_state: str = "inactive"
        self.current_session_id: Optional[str] = None
        self.enforcement_enabled: bool = False

    def evaluate_and_coordinate(
        self,
        policy: Optional[VerifiedPolicy],
        local_now_utc: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluate policy state and apply idempotent state transitions to enforcement engines.
        Returns evaluation result dictionary.
        """
        eval_res = self.session_evaluator.evaluate_policy_session(policy, local_now_utc=local_now_utc)
        new_state = eval_res["state"]
        session_id = eval_res.get("session_id")
        old_state = self.current_state

        # Check if state transition occurred
        if new_state == old_state and session_id == self.current_session_id:
            # Maintain active scanning loop if active
            if new_state == "active" and policy:
                self.process_monitor.scan_and_enforce(policy)
            return eval_res

        LOGGER.info("Scheduler state transition: '%s' -> '%s' (session: %s)", old_state, new_state, session_id)

        # Transition: -> ACTIVE
        if new_state == "active" and policy:
            self.enforcement_enabled = True
            self.current_state = "active"
            self.current_session_id = session_id

            # Enable DNS enforcement if controller available
            if self.dns_controller and hasattr(self.dns_controller, "enable_enforcement"):
                try:
                    self.dns_controller.enable_enforcement(policy)
                except Exception as err:
                    LOGGER.error("DNS controller activation error: %s", err)

            # Execute process monitor scan
            self.process_monitor.scan_and_enforce(policy)

            # Dispatch session_activated telemetry event
            self._dispatch_scheduler_event(
                event_type="session_activated",
                session_id=session_id,
                policy_version=policy.policy_version,
                old_state=old_state,
                new_state="active",
                reason=eval_res.get("reason", "Session started")
            )

        # Transition: -> ENDED / CANCELLED / EXPIRED / INVALID_TIME / INACTIVE
        else:
            self.enforcement_enabled = False
            self.current_state = new_state
            self.current_session_id = session_id

            # Disable DNS enforcement and restore host configuration
            if self.dns_controller and hasattr(self.dns_controller, "disable_enforcement"):
                try:
                    self.dns_controller.disable_enforcement()
                except Exception as err:
                    LOGGER.error("DNS controller deactivation error: %s", err)

            event_type_map = {
                "invalid_time": "session_time_invalid",
                "cancelled": "session_cancelled",
                "expired": "policy_expired",
                "ended": "session_deactivated"
            }
            event_type = event_type_map.get(new_state, "session_deactivated")

            self._dispatch_scheduler_event(
                event_type=event_type,
                session_id=session_id,
                policy_version=policy.policy_version if policy else None,
                old_state=old_state,
                new_state=new_state,
                reason=eval_res.get("reason", "Session concluded or enforcement disabled")
            )

        return eval_res

    def _dispatch_scheduler_event(
        self,
        event_type: str,
        session_id: Optional[str],
        policy_version: Optional[int],
        old_state: str,
        new_state: str,
        reason: Optional[str] = None
    ) -> None:
        """Enqueue idempotent scheduler telemetry event to SQLite queue."""
        now_iso = datetime.now(timezone.utc).isoformat()
        event_id = str(uuid.uuid4())
        device_id = getattr(self.telemetry_manager.api_client.config, "device_id", "agent_device")

        payload = {
            "event_id": event_id,
            "event_type": event_type,
            "device_id": device_id,
            "session_id": session_id,
            "policy_version": policy_version,
            "old_state": old_state,
            "new_state": new_state,
            "occurred_at_utc": now_iso,
            "server_time_offset_seconds": round(self.server_clock.get_server_offset_seconds(), 2),
            "reason": reason
        }

        try:
            self.telemetry_manager.db.enqueue_telemetry(
                idempotency_key=event_id,
                event_type=event_type,
                payload=payload
            )
            self.telemetry_manager.flush_queue()
        except Exception as err:
            LOGGER.debug("Scheduler telemetry enqueue error: %s", err)
