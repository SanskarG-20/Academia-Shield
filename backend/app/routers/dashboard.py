"""
Dashboard Router (/api/v1/dashboard).
"""

from typing import List
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import require_professor
from ..models.user import User
from ..models.session import SessionModel
from ..models.device import AgentDevice
from ..models.telemetry import PolicyViolation
from ..schemas.dashboard import LiveDashboardResponse, ViolationResponse, AgentStatusResponse

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/live", response_model=LiveDashboardResponse)
def get_live_dashboard(
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Fetch real-time classroom telemetry overview (Professor/Admin only)."""
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    active_sessions = db.query(SessionModel).filter(
        SessionModel.status.in_(["active", "Active"]),
        SessionModel.is_active == True
    ).all()

    enrolled_devices_count = db.query(AgentDevice).filter(AgentDevice.is_active == True).count()
    online_threshold = now - timedelta(minutes=5)
    online_agents_count = db.query(AgentDevice).filter(AgentDevice.last_seen_at >= online_threshold).count()

    pv_today = db.query(PolicyViolation).filter(PolicyViolation.occurred_at >= today_start).count()
    from ..models.telemetry import TelemetryEvent
    from ..models.audit_log import AuditLog
    telem_today = db.query(TelemetryEvent).filter(
        TelemetryEvent.occurred_at >= today_start,
        TelemetryEvent.event_type.in_(["application_violation", "process_violation", "dns_block", "tamper_alert", "usb_storage_violation"])
    ).count()
    audit_today = db.query(AuditLog).filter(
        AuditLog.created_at >= today_start,
        AuditLog.action.in_(["VIOLATION", "POLICY_VIOLATION"])
    ).count()
    violations_today = max(pv_today, telem_today) + audit_today

    session_list = []
    for s in active_sessions:
        session_list.append({
            "id": s.id,
            "title": s.title,
            "class_id": s.class_id,
            "start_at": s.start_at_utc or s.start_at or s.created_at or now,
            "end_at": s.end_at_utc or s.end_at or s.created_at or (now + timedelta(hours=2)),
            "status": s.status
        })

    return LiveDashboardResponse(
        active_sessions_count=len(active_sessions),
        enrolled_devices_count=enrolled_devices_count,
        online_agents_count=online_agents_count,
        total_violations_today=violations_today,
        active_sessions=session_list
    )

@router.get("/violations", response_model=List[ViolationResponse])
def get_violations_audit(
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Fetch policy violation audit trail (Professor/Admin only)."""
    violations = db.query(PolicyViolation).order_by(PolicyViolation.occurred_at.desc()).limit(100).all()
    results = []
    for v in violations:
        student_name = "Anonymous"
        device = db.query(AgentDevice).filter(AgentDevice.id == v.device_id).first()
        if device and device.user:
            student_name = device.user.full_name

        sess_title = None
        if v.session_id:
            s = db.query(SessionModel).filter(SessionModel.id == v.session_id).first()
            if s:
                sess_title = s.title

        results.append(ViolationResponse(
            id=v.id,
            device_id=v.device_id,
            student_name=student_name,
            session_id=v.session_id,
            session_title=sess_title,
            violation_type=v.violation_type,
            target_value=v.target_value,
            action_taken=v.action_taken,
            occurred_at=v.occurred_at
        ))

    return results

@router.get("/agent-status", response_model=List[AgentStatusResponse])
def get_agent_status(
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Fetch health status of all enrolled student agent devices (Professor/Admin only)."""
    now = datetime.now(timezone.utc)
    devices = db.query(AgentDevice).order_by(AgentDevice.last_seen_at.desc()).all()
    results = []
    for d in devices:
        user_name = d.user.full_name if d.user else "Unknown"
        user_email = d.user.email if d.user else "Unknown"

        # Calculate real online status (heartbeat within last 45 seconds)
        is_online = False
        if d.last_seen_at:
            last_seen_aware = d.last_seen_at if d.last_seen_at.tzinfo else d.last_seen_at.replace(tzinfo=timezone.utc)
            is_online = (now - last_seen_aware).total_seconds() <= 45

        # Find active batch / session if student joined
        from ..models.session import SessionParticipant, SessionModel
        from ..models.batch import BatchMember, Batch
        active_part = db.query(SessionParticipant).filter(
            SessionParticipant.student_id == d.user_id,
            SessionParticipant.status == "joined"
        ).first()

        batch_name = None
        batch_mem = db.query(BatchMember).filter(BatchMember.student_id == d.user_id, BatchMember.status == "active").first()
        if batch_mem:
            batch_obj = db.query(Batch).filter(Batch.id == batch_mem.batch_id).first()
            if batch_obj:
                batch_name = batch_obj.name

        results.append(AgentStatusResponse(
            device_id=d.id,
            user_name=user_name,
            user_email=user_email,
            device_name=d.device_name,
            platform=d.platform,
            agent_version=d.agent_version,
            is_active=d.is_active,
            last_seen_at=d.last_seen_at,
            enrollment_status=getattr(d, "enrollment_status", "enrolled"),
            compliance_status=getattr(d, "compliance_status", "compliant"),
            policy_delivery_state=getattr(d, "policy_delivery_state", "idle"),
            capabilities=d.capabilities_json,
            is_online=is_online,
            session_id=active_part.session_id if active_part else None,
            batch_name=batch_name
        ))

    return results

