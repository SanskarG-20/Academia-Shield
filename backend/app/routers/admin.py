"""
Academia Shield IT Administrator Management Router.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..core.database import get_db
from ..core.dependencies import get_current_user
from ..models.user import User
from ..models.institution import InstitutionSetting
from ..models.device import AgentDevice
from ..models.audit_log import AuditLog
from ..models.session import SessionModel
from ..models.telemetry import PolicyViolation

router = APIRouter(prefix="/api/v1/admin", tags=["IT Administrator"])

def require_admin_or_professor(current_user: User = Depends(get_current_user)):
    if current_user.role not in ("admin", "professor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IT Administrator privileges required"
        )
    return current_user

def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IT Administrator privileges required"
        )
    return current_user

@router.get("/institution")
def get_institution_settings(
    current_user: User = Depends(require_admin_or_professor),
    db: Session = Depends(get_db)
):
    """Retrieve global institution compliance configuration."""
    setting = db.query(InstitutionSetting).first()
    if not setting:
        setting = InstitutionSetting(
            institution_name="Academia Shield Academic Institute",
            allow_usb_blocking=True,
            fail_safe_grace_seconds=120,
            max_session_duration_minutes=240,
            require_student_consent=True
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)

    return {
        "id": setting.id,
        "institution_name": setting.institution_name,
        "allow_usb_blocking": setting.allow_usb_blocking,
        "fail_safe_grace_seconds": setting.fail_safe_grace_seconds,
        "max_session_duration_minutes": setting.max_session_duration_minutes,
        "require_student_consent": setting.require_student_consent,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None
    }

@router.put("/institution")
def update_institution_settings(
    payload: Dict[str, Any],
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update global institution compliance configuration (Admin only)."""
    setting = db.query(InstitutionSetting).first()
    if not setting:
        setting = InstitutionSetting()
        db.add(setting)

    if "institution_name" in payload:
        setting.institution_name = str(payload["institution_name"]).strip()
    if "allow_usb_blocking" in payload:
        setting.allow_usb_blocking = bool(payload["allow_usb_blocking"])
    if "fail_safe_grace_seconds" in payload:
        setting.fail_safe_grace_seconds = max(30, int(payload["fail_safe_grace_seconds"]))
    if "max_session_duration_minutes" in payload:
        setting.max_session_duration_minutes = max(15, int(payload["max_session_duration_minutes"]))
    if "require_student_consent" in payload:
        setting.require_student_consent = bool(payload["require_student_consent"])

    db.commit()
    db.refresh(setting)

    # Log audit trail
    audit = AuditLog(
        actor_user_id=current_user.id,
        action="INSTITUTION_SETTINGS_UPDATED",
        entity_type="INSTITUTION",
        entity_id=setting.id,
        metadata_json=payload
    )
    db.add(audit)
    db.commit()

    return {
        "status": "success",
        "message": "Institution settings updated successfully",
        "settings": {
            "institution_name": setting.institution_name,
            "allow_usb_blocking": setting.allow_usb_blocking,
            "fail_safe_grace_seconds": setting.fail_safe_grace_seconds,
            "max_session_duration_minutes": setting.max_session_duration_minutes,
            "require_student_consent": setting.require_student_consent
        }
    }

@router.get("/audit-logs")
def list_system_audit_logs(
    action: Optional[str] = Query(default=None),
    entity_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    current_user: User = Depends(require_admin_or_professor),
    db: Session = Depends(get_db)
):
    """Retrieve immutable system audit logs."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type.upper())

    logs = query.order_by(desc(AuditLog.created_at)).limit(limit).all()

    # Join actor names
    user_ids = {log.actor_user_id for log in logs if log.actor_user_id}
    users_map = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return [
        {
            "id": log.id,
            "actor_user_id": log.actor_user_id,
            "actor_name": users_map.get(log.actor_user_id, "System / Automated"),
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "metadata": log.metadata_json or {},
            "created_at": log.created_at.isoformat() if log.created_at else None
        }
        for log in logs
    ]

@router.get("/devices")
def list_enrolled_devices(
    limit: int = Query(default=100, le=500),
    current_user: User = Depends(require_admin_or_professor),
    db: Session = Depends(get_db)
):
    """List all registered and enrolled student devices across the institution."""
    devices = db.query(AgentDevice).order_by(desc(AgentDevice.last_seen_at)).limit(limit).all()
    user_ids = {d.user_id for d in devices if d.user_id}
    users_map = {u.id: {"name": u.full_name, "email": u.email, "roll": u.roll_number} for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return [
        {
            "id": d.id,
            "device_name": d.device_name,
            "device_identifier": d.device_identifier,
            "platform": d.platform,
            "agent_version": d.agent_version,
            "enrollment_status": d.enrollment_status,
            "compliance_status": d.compliance_status,
            "policy_delivery_state": d.policy_delivery_state,
            "is_active": d.is_active,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "enrolled_at": d.enrolled_at.isoformat() if d.enrolled_at else None,
            "student": users_map.get(d.user_id, {"name": "Unassigned", "email": "", "roll": ""})
        }
        for d in devices
    ]

@router.get("/stats")
def get_institution_stats(
    current_user: User = Depends(require_admin_or_professor),
    db: Session = Depends(get_db)
):
    """Retrieve institution-wide health, compliance, and activity metrics."""
    total_professors = db.query(User).filter(User.role == "professor").count()
    total_students = db.query(User).filter(User.role == "student").count()
    total_devices = db.query(AgentDevice).count()
    active_devices = db.query(AgentDevice).filter(AgentDevice.is_active == True).count()
    from ..models.telemetry import TelemetryEvent
    from ..models.audit_log import AuditLog
    total_pv = db.query(PolicyViolation).count()
    total_telem = db.query(TelemetryEvent).filter(
        TelemetryEvent.event_type.in_(["application_violation", "process_violation", "dns_block", "tamper_alert", "usb_storage_violation"])
    ).count()
    total_audit = db.query(AuditLog).filter(AuditLog.action.in_(["VIOLATION", "POLICY_VIOLATION"])).count()
    total_violations = max(total_pv, total_telem) + total_audit

    return {
        "total_professors": total_professors,
        "total_students": total_students,
        "total_devices": total_devices,
        "active_devices": active_devices,
        "active_sessions": active_sessions,
        "total_violations": total_violations
    }
