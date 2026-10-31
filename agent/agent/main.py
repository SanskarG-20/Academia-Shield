"""
Academia Shield Local Agent Daemon.
Coordinates heartbeat, policy retrieval, telemetry flush worker,
process monitoring, and graceful policy restoration on shutdown.
"""

import sys
import os
import time
import signal
import logging
from datetime import datetime, timezone
from typing import Optional

from .platforms import get_platform_bundle
from .core.storage.database import LocalDatabase
from .core.auth.tokens import TokenManager
from .core.enrollment.enrollment_manager import EnrollmentManager, AGENT_VERSION
from .core.api.client import ApiClient, DEFAULT_API_URL
from .core.telemetry.queue import TelemetryManager
from .core.policy.engine import PolicyEngine
from .core.state_machine.machine import AgentStateMachine, AgentState
from .telemetry.engagement_tracker import EngagementTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent.main")

class AgentCoordinator:
    def __init__(self, base_url: str = DEFAULT_API_URL):
        self.platform = get_platform_bundle()
        self.db = LocalDatabase()
        self.tokens = TokenManager(self.platform.storage)
        self.enrollment = EnrollmentManager(self.platform.storage)
        
        dev_info = self.enrollment.get_enrollment_info()
        self.api = ApiClient(
            base_url=os.getenv("BACKEND_API_URL", base_url),
            token_manager=self.tokens,
            device_identifier=dev_info.get("device_identifier")
        )
        self.enrollment.api_client = self.api
        self.telemetry = TelemetryManager(
            db=self.db,
            api_client=self.api,
            device_id=dev_info.get("device_id"),
            device_identifier=dev_info.get("device_identifier")
        )
        self.policy_engine = PolicyEngine(self.db)
        self.engagement_tracker = EngagementTracker(api_client=self.api)

        # State machine with restore callback
        init_state = AgentState.ENROLLED_IDLE if self.enrollment.is_enrolled() else AgentState.NOT_ENROLLED
        self.sm = AgentStateMachine(
            initial_state=init_state,
            on_restore=self._restore_system_settings,
            on_state_change=self._handle_state_transition
        )

        self._running = False

    def _restore_system_settings(self):
        logger.info("Restoring system settings and stopping enforcement...")
        self.platform.dns.restore_original_dns()
        self.telemetry.record_event(
            event_type="policy_restored",
            session_id=self.sm.context.get("session_id"),
            policy_version=self.sm.context.get("policy_version")
        )
        self.db.write_audit_log("RESTORATION", "POLICY_RESTORED", {"state": self.sm.current_state.value})

    def _handle_state_transition(self, old_state: AgentState, new_state: AgentState, ctx: dict):
        self.telemetry.record_event(
            event_type="state_transition",
            session_id=ctx.get("session_id"),
            payload={"from_state": old_state.value, "to_state": new_state.value}
        )
        self.db.write_audit_log("STATE", f"{old_state.value}_TO_{new_state.value}", ctx)

    def send_heartbeat(self):
        if not self.enrollment.is_enrolled():
            return
        dev_info = self.enrollment.get_enrollment_info()
        cached_pol = self.db.get_cached_policy()

        dns_status_res = self.platform.dns.get_status()
        proc_status_res = self.platform.process_monitor.get_status()
        usb_res = self.platform.usb_compliance.check_compliance()

        payload = {
            "device_id": dev_info.get("device_id"),
            "device_identifier": dev_info.get("device_identifier"),
            "agent_version": AGENT_VERSION,
            "agent_installed": True,
            "agent_service_running": True,
            "current_session_id": self.sm.context.get("session_id"),
            "policy_version": cached_pol.get("policy_version") if cached_pol else None,
            "dns_enforcement_status": dns_status_res.status.value,
            "application_control_status": proc_status_res.status.value,
            "usb_storage_restricted": usb_res.details.get("usb_storage_blocked", False),
            "health_state": "healthy" if self.sm.current_state != AgentState.ERROR else "degraded"
        }

        self.api.post("/api/v1/agent/heartbeat", json=payload)

    def sync_active_policy(self):
        """Fetch and enforce active policy when student is joined and professor started session."""
        if not self.enrollment.is_enrolled():
            return

        res = self.api.get("/api/v1/agent/policies/active")
        status_code = res.get("status_code", 0)

        if status_code == 200 and res.get("data") and res["data"].get("policy_active") is True:
            pol_data = res["data"]
            policy_id = pol_data.get("policy_id") or pol_data.get("id") or pol_data.get("session_id")
            session_id = pol_data.get("session_id")
            version = pol_data.get("policy_version", 1)

            # 1. Validate signature & temporal validity
            sig_valid = self.policy_engine.verify_policy_signature(pol_data)
            is_valid, reason = self.policy_engine.is_policy_temporally_valid(pol_data)

            if not sig_valid or not is_valid:
                logger.warning(f"Invalid or expired policy received: {reason}")
                if self.sm.current_state == AgentState.ENFORCING:
                    self.sm.transition_to(AgentState.RESTORING, {"session_id": session_id})
                    self.sm.transition_to(AgentState.ERROR, {"error": reason})
                return

            # 2. Apply DNS & App enforcement if not already enforcing this version
            current_enforcing_session = self.sm.context.get("session_id")
            current_enforcing_version = self.sm.context.get("policy_version")

            if self.sm.current_state == AgentState.OFFLINE_ENFORCING:
                self.sm.return_to_online_enforcing()

            if self.sm.current_state != AgentState.ENFORCING or current_enforcing_session != session_id or current_enforcing_version != version:
                logger.info(f"Activating session policy for session {session_id} v{version}")
                domain_rules = pol_data.get("domain_rules", [])
                if domain_rules:
                    self.platform.dns.apply_dns_redirect()

                self.policy_engine.active_policy = pol_data
                self.db.cache_policy(pol_data)

                self.sm.transition_to(AgentState.ENFORCING, {
                    "session_id": session_id,
                    "policy_id": policy_id,
                    "policy_version": version
                })

                # Acknowledge policy receipt
                self.api.post(
                    f"/api/v1/agent/policies/{policy_id}/acknowledge",
                    json={"status": "acknowledged", "policy_version": version, "session_id": session_id}
                )
                self.telemetry.record_event(
                    event_type="policy_acknowledged",
                    session_id=session_id,
                    policy_version=version,
                    payload={"status": "enforcing"}
                )

            # Start engagement tracking window if not already active for this session
            if not self.engagement_tracker.is_active or self.engagement_tracker.session_id != session_id:
                dev_info = self.enrollment.get_enrollment_info()
                student_id = pol_data.get("student_id")
                device_id = pol_data.get("device_id") or dev_info.get("device_id")
                batch_id = pol_data.get("batch_id")
                if student_id and device_id and batch_id:
                    self.engagement_tracker.start_session(
                        session_id=session_id,
                        batch_id=batch_id,
                        student_id=student_id,
                        device_id=device_id,
                        policy_version=version
                    )

        else:
            # If request failed due to network error (status_code == 0 or connection refused), do NOT transition to RESTORING!
            # Instead, transition to OFFLINE_ENFORCING and keep blocking!
            if status_code == 0 or status_code >= 500:
                if self.sm.current_state == AgentState.ENFORCING:
                    logger.warning("Network connection lost during active session. Entering OFFLINE_ENFORCING mode...")
                    self.sm.enter_offline_enforcing()
            elif self.sm.current_state in (AgentState.ENFORCING, AgentState.OFFLINE_ENFORCING):
                logger.info("Session ended or policy revoked. Restoring baseline settings...")
                if self.engagement_tracker.is_active:
                    self.engagement_tracker.end_session()
                self.policy_engine.active_policy = None
                self.sm.transition_to(AgentState.RESTORING)
                self.sm.transition_to(AgentState.ENROLLED_IDLE)


    def evaluate_processes(self):
        """Inspect running processes against active policy."""
        if self.sm.current_state not in (AgentState.ENFORCING, AgentState.OFFLINE_ENFORCING) or not self.policy_engine.active_policy:
            return

        processes = self.platform.process_monitor.get_running_processes()
        for p in processes:
            name = p.get("name", "")
            pid = p.get("pid")
            should_restrict, action, rule_id = self.policy_engine.should_restrict_process(name)
            if should_restrict and pid:
                action_res = self.platform.process_monitor.handle_process_action(pid, name, action)
                self.engagement_tracker.record_violation("application")
                self.telemetry.record_event(
                    event_type="application_violation",
                    session_id=self.sm.context.get("session_id"),
                    policy_version=self.sm.context.get("policy_version"),
                    rule_id=rule_id,
                    executable_name=name,
                    action_requested=action,
                    action_result=action_res.status.value,
                    payload=action_res.details
                )
                try:
                    self.telemetry.flush_pending()
                except Exception as flush_err:
                    logger.debug("Failed immediate telemetry flush: %s", flush_err)

    def run_loop(self):
        self._running = True
        logger.info(f"Academia Shield Local Agent Daemon started. State: {self.sm.current_state.value}")

        # Repair DNS adapter state left behind by an earlier crashed run before
        # this daemon begins enforcing anything.
        try:
            from .platform.windows_dns import WindowsDNSAdapterManager
            recovery = WindowsDNSAdapterManager().recover_orphaned_state()
            logger.info("Startup network recovery: %s", recovery.get("status"))
        except Exception as err:
            logger.warning("Startup network recovery skipped: %s", err)

        last_heartbeat = 0
        last_flush = 0
        last_policy_sync = 0

        while self._running:
            try:
                now = time.time()

                # 1. Heartbeat every 15s
                if now - last_heartbeat > 15:
                    self.send_heartbeat()
                    last_heartbeat = now

                # 2. Telemetry flush every 10s
                if now - last_flush > 10:
                    self.telemetry.flush_pending()
                    last_flush = now

                # 3. Policy sync every 5s
                if now - last_policy_sync > 5:
                    self.sync_active_policy()
                    last_policy_sync = now

                # 4. Process evaluation loop (if enforcing)
                if self.sm.current_state == AgentState.ENFORCING:
                    self.evaluate_processes()

                # 5. Engagement tracking tick
                if self.engagement_tracker.is_active:
                    self.engagement_tracker.tick()

                time.sleep(2)
            except Exception as e:
                logger.error(f"Error in agent main loop: {e}")
                time.sleep(5)

    def stop(self):
        self._running = False
        if self.engagement_tracker.is_active:
            self.engagement_tracker.end_session()
        self.sm.transition_to(AgentState.RESTORING)
        self.telemetry.flush_pending()
        logger.info("Academia Shield Local Agent Daemon stopped cleanly.")


def main():
    coordinator = AgentCoordinator()

    def handle_sig(sig, frame):
        logger.info(f"Received signal {sig}. Initiating graceful shutdown...")
        coordinator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    coordinator.run_loop()

if __name__ == "__main__":
    main()
