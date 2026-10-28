"""
Telemetry & Audit Log Processing Service.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models.telemetry import TelemetryEvent, PolicyViolation
from ..models.device import AgentDevice, AgentPolicyAssignment
from ..models.session import SessionModel, SessionParticipant
from ..models.audit_log import AuditLog
from ..models.class_model import ClassMember
from ..models.user import User
from ..schemas.agent import TelemetryEventItem
from ..core.sockets import broadcast_telemetry_event


SAFE_EVENT_TYPES = {
    "application_access",
    "application_violation",
    "application_monitor_health",
    "application_enforcement_error",
    "dns_block",
    "dns_blocked",
    "dns_violation",
    "resolver_started",
    "resolver_stopped",
    "upstream_health",
    "resolver_health",
    "dns_configuration_drift",
    "drift",
    "process",
    "web",
    "usb",
    "usb_storage_violation",
    "process_violation",
    "heartbeat",
    "tamper_alert",
    "session_upcoming",
    "session_activated",
    "session_deactivated",
    "session_cancelled",
    "session_time_invalid",
    "scheduler_health",
    "clock_skew_detected",
    "policy_restored",
    "policy_acknowledged",
    "policy_delivered",
    "policy_rejected",
    "state_transition"
}


FORBIDDEN_PAYLOAD_KEYS = {
    "cmdline", "command_line", "args", "arguments",
    "window_title", "window_text", "file_name", "full_path",
    "password", "passwords", "secret", "screenshot", "memory", "dump"
}

class TelemetryService:
    """Manages telemetry ingestion, event deduplication via event_id, and violation recording."""

    @staticmethod
    def sanitize_payload(raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Strip sensitive or forbidden fields from telemetry payload."""
        sanitized = {}
        for k, v in raw_payload.items():
            if k.lower() in FORBIDDEN_PAYLOAD_KEYS:
                continue
            if isinstance(v, (str, int, float, bool, type(None))):
                sanitized[k] = v
            elif isinstance(v, dict):
                sanitized[k] = TelemetryService.sanitize_payload(v)
        return sanitized

    @staticmethod
    def process_telemetry_batch(device: AgentDevice, events: List[TelemetryEventItem], db: Session) -> Dict[str, Any]:
        processed_count = 0
        duplicate_count = 0

        for item in events:
            if item.event_type not in SAFE_EVENT_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported telemetry event type: '{item.event_type}'"
                )

            # Session verification if session_id is provided, or resolve from active assignment
            explicit_session = bool(item.session_id)
            if not item.session_id:
                assignment = db.query(AgentPolicyAssignment).filter(
                    (AgentPolicyAssignment.device_id == device.id) | (AgentPolicyAssignment.student_id == device.user_id),
                    AgentPolicyAssignment.state.in_(["active", "pending"])
                ).order_by(AgentPolicyAssignment.assigned_at.desc()).first()
                if assignment and assignment.session_id:
                    item.session_id = assignment.session_id
                else:
                    active_sess = db.query(SessionModel).filter(
                        SessionModel.status.in_(["active", "in_progress"])
                    ).order_by(SessionModel.created_at.desc()).first()
                    if active_sess:
                        is_part = bool(db.query(SessionParticipant).filter(
                            SessionParticipant.session_id == active_sess.id,
                            SessionParticipant.student_id == device.user_id
                        ).first())
                        if not is_part and active_sess.batch_id:
                            from ..models.batch import BatchMember
                            is_part = bool(db.query(BatchMember).filter(
                                BatchMember.batch_id == active_sess.batch_id,
                                BatchMember.student_id == device.user_id
                            ).first())
                        if is_part:
                            item.session_id = active_sess.id

            if item.session_id:
                session_obj = db.query(SessionModel).filter(SessionModel.id == item.session_id).first()
                if not session_obj:
                    if explicit_session and len(events) == 1:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Session '{item.session_id}' not found"
                        )
                    # For batches with stale offline events, continue processing
                    item.session_id = None
                else:
                    # Allow if created by professor/admin or student assigned/joined
                    user = db.query(User).filter(User.id == device.user_id).first()
                    is_owner = (session_obj.created_by == device.user_id) or (user and user.role in ("professor", "admin"))
                    is_enrolled = False
                    if session_obj.class_id:
                        is_enrolled = bool(db.query(ClassMember).filter(
                            ClassMember.class_id == session_obj.class_id,
                            ClassMember.student_id == device.user_id
                        ).first())
                    if not is_enrolled and session_obj.batch_id:
                        from ..models.batch import BatchMember
                        is_enrolled = bool(db.query(BatchMember).filter(
                            BatchMember.batch_id == session_obj.batch_id,
                            BatchMember.student_id == device.user_id
                        ).first())
                    is_participant = bool(db.query(SessionParticipant).filter(
                        SessionParticipant.session_id == session_obj.id,
                        SessionParticipant.student_id == device.user_id
                    ).first())
                    has_assignment = bool(db.query(AgentPolicyAssignment).filter(
                        AgentPolicyAssignment.session_id == session_obj.id,
                        (AgentPolicyAssignment.student_id == device.user_id) | (AgentPolicyAssignment.device_id == device.id)
                    ).first())

                    if not (is_owner or is_enrolled or is_participant or has_assignment):
                        if explicit_session and len(events) == 1:
                            raise HTTPException(
                                status_code=status.HTTP_403_FORBIDDEN,
                                detail="Device user is not assigned to the batch or class for this session"
                            )
                        item.session_id = None

            evt_id = item.event_id or str(uuid.uuid4())
            # Check idempotency: event_id must be unique
            existing = db.query(TelemetryEvent).filter(TelemetryEvent.event_id == evt_id).first()
            if existing:
                if len(events) == 1:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Duplicate telemetry event_id '{evt_id}'"
                    )
                duplicate_count += 1
                continue

            if item.occurred_at is not None:
                occurred_at = item.occurred_at.replace(tzinfo=timezone.utc) if item.occurred_at.tzinfo is None else item.occurred_at
            else:
                occurred_at = datetime.now(timezone.utc)

            # Merge flat fields into payload_json if provided
            payload_dict = dict(item.payload or {})
            if item.executable_name:
                payload_dict["executable_name"] = item.executable_name
            if item.action_requested:
                payload_dict["action_requested"] = item.action_requested
            if item.action_result:
                payload_dict["action_result"] = item.action_result
            if item.rule_id:
                payload_dict["rule_id"] = item.rule_id
            if item.policy_version:
                payload_dict["policy_version"] = item.policy_version

            clean_payload = TelemetryService.sanitize_payload(payload_dict)

            # Robust active session resolution
            resolved_session_id = item.session_id or clean_payload.get("session_id") or clean_payload.get("sessionId")
            if not resolved_session_id:
                # 1. Check active policy assignment on this device
                assign = db.query(AgentPolicyAssignment).filter(
                    AgentPolicyAssignment.device_id == device.id,
                    AgentPolicyAssignment.state.in_(["active", "pending"])
                ).order_by(AgentPolicyAssignment.assigned_at.desc()).first()
                if assign and assign.session_id:
                    resolved_session_id = assign.session_id

            if not resolved_session_id and device.user_id:
                # 2. Check active session where student is a participant
                joined_part = (
                    db.query(SessionParticipant)
                    .join(SessionModel, SessionModel.id == SessionParticipant.session_id)
                    .filter(
                        SessionParticipant.student_id == device.user_id,
                        SessionModel.status.in_(["active", "in_progress", "Active"])
                    )
                    .first()
                )
                if joined_part and joined_part.session_id:
                    resolved_session_id = joined_part.session_id

            if not resolved_session_id:
                # 3. Fallback to any currently active session
                active_sess = db.query(SessionModel).filter(
                    SessionModel.status.in_(["active", "in_progress", "Active"])
                ).order_by(SessionModel.start_at_utc.desc()).first()
                if active_sess:
                    resolved_session_id = active_sess.id

            telemetry = TelemetryEvent(
                event_id=evt_id,
                device_id=device.id,
                session_id=resolved_session_id,
                event_type=item.event_type or "heartbeat",
                payload_json=clean_payload,
                occurred_at=occurred_at
            )
            db.add(telemetry)
            processed_count += 1

            # Record in PolicyViolation and AuditLog tables if applicable
            action = clean_payload.get("action_result") or clean_payload.get("action_requested") or clean_payload.get("action", "")
            res_name = (
                clean_payload.get("executable_name")
                or clean_payload.get("application")
                or clean_payload.get("domain")
                or clean_payload.get("resource_name")
                or item.executable_name
                or item.event_type
            )
            res_clean = str(res_name or "").strip().lower()

            # Internal lifecycle events, heartbeats, and restoration must NEVER be violations
            is_internal_lifecycle = (
                item.event_type in ("policy_restored", "heartbeat", "state_transition", "policy_delivered", "policy_acknowledged")
                or res_clean in ("policy_restored", "system", "heartbeat", "state_transition", "all", "none")
            )

            is_viol = False
            if not is_internal_lifecycle:
                is_viol = (
                    item.event_type in ("application_violation", "process_violation", "dns_block", "dns_blocked", "dns_violation", "usb_storage_violation")
                    or bool(clean_payload.get("is_violation"))
                    or bool(clean_payload.get("isViolation"))
                    or str(action).lower() in ("blocked", "closed", "violation")
                )

            user_obj = db.query(User).filter(User.id == device.user_id).first()
            user_name = user_obj.full_name if user_obj else "Student"
            sap_id = getattr(user_obj, "roll_number", None) or getattr(user_obj, "institutional_id", "") or ""

            if is_viol:
                # 1 App / 1 Website / 1 Pendrive = 1 Violation:
                # Deduplicate repeated violation events for the same target and device within 20 seconds
                recent_cutoff = occurred_at - timedelta(seconds=20)
                recent_viol = db.query(PolicyViolation).filter(
                    PolicyViolation.device_id == device.id,
                    PolicyViolation.session_id == resolved_session_id,
                    PolicyViolation.target_value.ilike(res_clean),
                    PolicyViolation.occurred_at >= recent_cutoff
                ).first()

                if recent_viol:
                    # Duplicate violation within cooldown window: suppress duplicate count & live broadcast
                    is_viol = False
                else:
                    rule_id = item.rule_id or clean_payload.get("rule_id")
                    viol_type = "process" if item.event_type in ("application_violation", "process_violation") or res_clean.endswith(".exe") else ("usb" if "usb" in item.event_type else "web")
                    violation = PolicyViolation(
                        device_id=device.id,
                        session_id=resolved_session_id,
                        rule_id=rule_id,
                        violation_type=viol_type,
                        target_value=str(res_name),
                        action_taken=str(action or "blocked"),
                        occurred_at=occurred_at
                    )
                    db.add(violation)

                    # Add AuditLog for immutable tracking and logs & analytics querying
                    audit = AuditLog(
                        actor_user_id=device.user_id or "system",
                        action="POLICY_VIOLATION",
                        entity_type="SESSION",
                        entity_id=resolved_session_id or "global",
                        metadata_json={
                            "domain": str(res_name),
                            "action": str(action or "blocked"),
                            "is_violation": True,
                            "student_name": user_name,
                            "sap_id": sap_id,
                            "engagement_score": clean_payload.get("engagement_score", 20)
                        }
                    )
                    db.add(audit)

            # Broadcast live telemetry event via Socket.IO with accurate activity labels
            is_proc = item.event_type in ("application_violation", "process_violation", "process", "application") or res_clean.endswith(".exe")
            is_usb = "usb" in item.event_type.lower() or "drive" in res_clean
            is_web = not is_proc and not is_usb and ("." in res_clean or "http" in res_clean or item.event_type in ("dns_block", "web"))

            if is_viol:
                if is_proc:
                    act_label = f"Blocked App: {res_name}"
                elif is_usb:
                    act_label = f"Blocked USB Storage: {res_name}"
                elif is_web:
                    act_label = f"Restricted Site: {res_name}"
                else:
                    act_label = f"Violation: {res_name}"
            else:
                act_label = f"Activity: {action or res_name}"

            socket_payload = {
                "_id": telemetry.id,
                "event_id": item.event_id,
                "type": "VIOLATION" if is_viol else "EVENT",
                "studentId": device.user_id,
                "student_id": device.user_id,
                "studentName": user_name,
                "student_name": user_name,
                "sapId": sap_id,
                "sessionId": resolved_session_id or "",
                "session_id": resolved_session_id or "",
                "resource": res_name,
                "activeApp": res_name,
                "category": "Process" if is_proc else ("USB" if is_usb else "Web"),
                "violation_type": viol_type if is_viol else None,
                "action": str(action or ("blocked" if is_viol else "active")),
                "details": act_label,
                "engagementScore": clean_payload.get("engagement_score", 85 if not is_viol else 20),
                "isViolation": is_viol,
                "is_violation": is_viol,
                "status": "online",
                "lastSeen": occurred_at.isoformat(),
                "timestamp": occurred_at.isoformat()
            }
            broadcast_telemetry_event(socket_payload)

        db.commit()
        return {
            "status": "ok",
            "processed": processed_count,
            "duplicates_ignored": duplicate_count
        }


