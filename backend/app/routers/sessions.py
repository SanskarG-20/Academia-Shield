"""
Academic Sessions Router (/api/v1/batches/{batch_id}/sessions, /api/v1/sessions, & /api/v1/student/sessions).
"""

from typing import List, Optional, Dict, Union
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ..core.database import get_db
from ..core.dependencies import require_professor, require_student, require_any_user, get_current_user
from ..core.sockets import broadcast_socket_event
from ..models.user import User
from ..models.batch import Batch, BatchMember
from ..models.session import SessionModel, SessionParticipant, SessionPresence, UnlockRequest
from ..models.rule import RuleSet
from ..models.audit_log import AuditLog
from ..models.telemetry import TelemetryEvent, PolicyViolation
from ..models.device import AgentDevice, AgentPolicy, AgentPolicyAssignment
from ..services.policy_service import PolicyService
from ..schemas.session import (
    SessionCreate,
    SessionUpdate,
    SessionStatusUpdate,
    SessionResponse,
    SessionStudentResponse,
    LiveMonitorResponse,
    LiveMonitorStudentItem,
    UnlockRequestCreate,
    UnlockRequestResolve,
    UnlockRequestResponse,
)

router = APIRouter(tags=["Sessions"])

def create_audit_log(db: Session, user_id: str, action: str, resource_id: str, details: str):
    audit = AuditLog(
        actor_user_id=user_id,
        action=action,
        entity_type="SESSION",
        entity_id=resource_id,
        metadata_json={"details": details}
    )
    db.add(audit)
    db.commit()


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _sync_scheduled_session_state(session_obj: SessionModel, now: Optional[datetime] = None) -> bool:
    """Keep session status updated. Never auto-activates scheduled sessions."""
    if session_obj.status.lower() in {"ended", "completed", "cancelled"}:
        return False

    now = now or datetime.now(timezone.utc)
    end_at = session_obj.end_at_utc
    if end_at and end_at.tzinfo is None:
        end_at = end_at.replace(tzinfo=timezone.utc)

    if session_obj.status.lower() == "active" and end_at and now >= end_at:
        session_obj.status = "ended"
        session_obj.is_active = False
        session_obj.ended_at = session_obj.ended_at or now
        session_obj.policy_version += 1
        return True

    return False



# ==============================================================================
# PROFESSOR SESSION ENDPOINTS & CLASS COMPATIBILITY ROUTES
# ==============================================================================

from ..services.class_service import ClassService

@router.post("/classes/{class_id}/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_class_session_alias(
    class_id: str,
    req: SessionCreate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    return ClassService.create_session(class_id, req, current_user, db)

@router.get("/classes/{class_id}/sessions", response_model=List[SessionResponse])
def list_class_sessions_alias(
    class_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return ClassService.list_class_sessions(class_id, current_user, db)

@router.post("/batches/{batch_id}/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_batch_session(
    batch_id: str,
    req: SessionCreate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Create a new academic session for a batch (Professor owner only).
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")

    if current_user.role != "admin" and batch.professor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can create sessions only for batches you own."
        )

    if not req.start_at_utc or not req.end_at_utc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Session start and end times are required.",
        )

    # Ensure UTC datetimes
    start_utc = req.start_at_utc.replace(tzinfo=timezone.utc) if req.start_at_utc.tzinfo is None else req.start_at_utc
    end_utc = req.end_at_utc.replace(tzinfo=timezone.utc) if req.end_at_utc.tzinfo is None else req.end_at_utc

    if end_utc <= start_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session end time must be strictly after start time."
        )

    import random
    import string
    code = "CG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    resolved_rule_set_id = req.rule_set_id
    if not resolved_rule_set_id:
        batch_rs = db.query(RuleSet).filter(RuleSet.batch_id == batch.id, RuleSet.is_active == True).first()
        if batch_rs:
            resolved_rule_set_id = batch_rs.id
        else:
            prof_rs = db.query(RuleSet).filter(RuleSet.created_by == current_user.id, RuleSet.is_active == True).order_by(RuleSet.updated_at.desc()).first()
            if prof_rs:
                resolved_rule_set_id = prof_rs.id

    session_obj = SessionModel(
        batch_id=batch.id,
        created_by=current_user.id,
        title=req.title.strip(),
        description=req.description.strip() if req.description else None,
        start_at=start_utc,
        end_at=end_utc,
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        timezone=req.timezone or "UTC",
        rule_set_id=resolved_rule_set_id,
        status="scheduled",
        is_active=False,
        session_code=code,
        policy_version=1
    )
    _sync_scheduled_session_state(session_obj)
    db.add(session_obj)
    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="SESSION_CREATED",
        resource_id=session_obj.id,
        details=f"Created session '{session_obj.title}' (Code: {code}) for batch '{batch.name}'"
    )

    return session_obj


@router.get("/batches/{batch_id}/sessions", response_model=List[SessionResponse])
def list_batch_sessions_professor(
    batch_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    List all sessions for a batch owned by Professor.
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")

    if current_user.role != "admin" and batch.professor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    return db.query(SessionModel).filter(SessionModel.batch_id == batch_id).all()


def _verify_session_owner(session_obj: SessionModel, current_user: User, db: Session):
    if current_user.role == "admin" or session_obj.created_by == current_user.id:
        return
    if session_obj.batch_id:
        batch = db.query(Batch).filter(Batch.id == session_obj.batch_id).first()
        if batch and batch.professor_id == current_user.id:
            return
    if session_obj.class_id:
        from ..models.class_model import ClassModel
        c_obj = db.query(ClassModel).filter(ClassModel.id == session_obj.class_id).first()
        if c_obj and c_obj.professor_id == current_user.id:
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session_by_id(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get single session details by ID (Professor owner, Admin, or enrolled Student).
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    if current_user.role == "student":
        has_access = False
        if session_obj.batch_id:
            membership = db.query(BatchMember).filter(
                BatchMember.batch_id == session_obj.batch_id,
                BatchMember.student_id == current_user.id,
                BatchMember.status == "active"
            ).first()
            if membership:
                has_access = True
        if not has_access and session_obj.class_id:
            from ..models.class_model import ClassMember
            c_membership = db.query(ClassMember).filter(
                ClassMember.class_id == session_obj.class_id,
                ClassMember.student_id == current_user.id
            ).first()
            if c_membership:
                has_access = True

        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You have not joined the batch or class for this session."
            )

    return session_obj


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: str,
    req: SessionUpdate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Update session details (Owner or Admin only).
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)

    if req.title is not None:
        session_obj.title = req.title.strip()
    if req.timezone is not None:
        session_obj.timezone = req.timezone
    if req.rule_set_id is not None:
        session_obj.rule_set_id = req.rule_set_id
    if req.start_at_utc is not None:
        session_obj.start_at_utc = req.start_at_utc.replace(tzinfo=timezone.utc) if req.start_at_utc.tzinfo is None else req.start_at_utc
    if req.end_at_utc is not None:
        session_obj.end_at_utc = req.end_at_utc.replace(tzinfo=timezone.utc) if req.end_at_utc.tzinfo is None else req.end_at_utc
    if req.status is not None:
        session_obj.status = req.status

    session_obj.policy_version += 1
    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="SESSION_UPDATED",
        resource_id=session_obj.id,
        details=f"Updated session '{session_obj.title}'"
    )

    return session_obj


@router.post("/sessions/{session_id}/start", response_model=SessionResponse)
def start_session(
    session_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Start an academic session, triggering active policy enforcement.
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)

    # Ensure policy rule set is published and assigned when session starts
    if session_obj.rule_set_id:
        assigned_rs = db.query(RuleSet).filter(RuleSet.id == session_obj.rule_set_id).first()
        if assigned_rs:
            if assigned_rs.status != "published":
                PolicyService.publish_rule_set(assigned_rs.id, current_user, db)
        else:
            session_obj.rule_set_id = None

    if not session_obj.rule_set_id:
        batch_rule_set = None
        if session_obj.batch_id:
            batch_rule_set = db.query(RuleSet).filter(
                RuleSet.batch_id == session_obj.batch_id,
                RuleSet.status == "published",
                RuleSet.is_active == True
            ).first() or db.query(RuleSet).filter(
                RuleSet.batch_id == session_obj.batch_id,
                RuleSet.is_active == True
            ).first()
        if not batch_rule_set and session_obj.class_id:
            batch_rule_set = db.query(RuleSet).filter(
                RuleSet.class_id == session_obj.class_id,
                RuleSet.status == "published",
                RuleSet.is_active == True
            ).first() or db.query(RuleSet).filter(
                RuleSet.class_id == session_obj.class_id,
                RuleSet.is_active == True
            ).first()
        if not batch_rule_set and session_obj.created_by:
            batch_rule_set = db.query(RuleSet).filter(
                RuleSet.created_by == session_obj.created_by,
                RuleSet.is_active == True
            ).order_by(RuleSet.updated_at.desc()).first()
        if not batch_rule_set:
            batch_rule_set = db.query(RuleSet).filter(
                RuleSet.is_active == True
            ).order_by(RuleSet.updated_at.desc()).first()

        if batch_rule_set:
            if batch_rule_set.status != "published":
                PolicyService.publish_rule_set(batch_rule_set.id, current_user, db)
            session_obj.rule_set_id = batch_rule_set.id
        else:
            # Create default published policy if none exists
            now_dt = datetime.now(timezone.utc)
            default_rs = RuleSet(
                batch_id=session_obj.batch_id,
                class_id=session_obj.class_id,
                session_id=session_obj.id,
                name=f"{session_obj.title} Policy",
                version=1,
                status="published",
                is_active=True,
                created_by=current_user.id,
                issued_at=now_dt,
                expires_at=now_dt + timedelta(hours=4),
                integrity_hash=""
            )
            db.add(default_rs)
            db.flush()
            dev_req = DevicePolicyRequirement(
                rule_set_id=default_rs.id,
                require_agent_enrolled=True,
                require_dns_or_content_filter=True,
                require_application_control=True
            )
            db.add(dev_req)
            db.commit()
            PolicyService.publish_rule_set(default_rs.id, current_user, db)
            session_obj.rule_set_id = default_rs.id

    now = datetime.now(timezone.utc)
    if session_obj.status.lower() == "active" and session_obj.is_active:
        return session_obj
    session_obj.status = "active"
    session_obj.is_active = True
    session_obj.started_at = now
    curr_start_utc = _ensure_utc(session_obj.start_at_utc)
    curr_end_utc = _ensure_utc(session_obj.end_at_utc)
    if not curr_start_utc or curr_start_utc > now:
        if curr_end_utc and curr_start_utc:
            duration = curr_end_utc - curr_start_utc
            session_obj.end_at_utc = now + max(duration, timedelta(minutes=15))
        else:
            session_obj.end_at_utc = now + timedelta(hours=1)
        session_obj.start_at_utc = now
    elif curr_end_utc and curr_end_utc <= now:
        session_obj.end_at_utc = now + timedelta(hours=1)
    session_obj.start_at = session_obj.start_at_utc
    session_obj.end_at = session_obj.end_at_utc
    session_obj.policy_version += 1
    session_obj.updated_at = now
    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="SESSION_STARTED",
        resource_id=session_obj.id,
        details=f"Started session '{session_obj.title}'"
    )

    from ..core.sockets import broadcast_socket_event
    broadcast_socket_event("session_started", {"session_id": session_id, "status": "active"}, session_id)
    broadcast_socket_event("session_updated", {"session_id": session_id, "status": "active"}, session_id)

    return session_obj


@router.post("/sessions/{session_id}/end", response_model=SessionResponse)
def end_session(
    session_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    End an active academic session and immediately revoke all agent policy assignments.
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)

    now = datetime.now(timezone.utc)
    session_obj.status = "ended"
    session_obj.is_active = False
    session_obj.ended_at = now
    session_obj.policy_version = (session_obj.policy_version or 1) + 1

    # Revoke all active policy assignments for this session
    db.query(AgentPolicyAssignment).filter(
        AgentPolicyAssignment.session_id == session_id,
        AgentPolicyAssignment.state.in_(["pending", "active"])
    ).update({
        "state": "revoked",
        "revoked_at": now,
        "restored_at": now,
        "failure_reason": "Session ended by professor"
    }, synchronize_session=False)

    # Revoke all agent policies
    db.query(AgentPolicy).filter(
        AgentPolicy.session_id == session_id,
        AgentPolicy.revoked_at.is_(None)
    ).update({"revoked_at": now}, synchronize_session=False)

    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="SESSION_ENDED",
        resource_id=session_obj.id,
        details=f"Ended session '{session_obj.title}'. All device restrictions revoked."
    )

    try:
        from ..ml.live_prediction_service import finalize_session_predictions
        finalize_session_predictions(db=db, session_id=session_id)
    except Exception as e:
        logger.warning(f"Failed to finalize session predictions for session {session_id}: {e}")

    broadcast_socket_event("session_ended", {"session_id": session_id, "status": "ended"}, session_id)
    broadcast_socket_event("policy_revoked", {"session_id": session_id, "reason": "session_ended"}, session_id)
    broadcast_socket_event("session_updated", {"session_id": session_id, "status": "ended"}, session_id)

    return session_obj


@router.post("/sessions/{session_id}/pause", response_model=SessionResponse)
def pause_session(
    session_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Pause an active academic session. Temporarily lifts policy restrictions.
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)

    session_obj.status = "paused"
    session_obj.is_active = False
    session_obj.policy_version += 1
    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="SESSION_PAUSED",
        resource_id=session_obj.id,
        details=f"Paused session '{session_obj.title}'"
    )

    from ..core.sockets import broadcast_socket_event
    broadcast_socket_event("session_paused", {"session_id": session_id, "status": "paused"}, session_id)
    broadcast_socket_event("session_updated", {"session_id": session_id, "status": "paused"}, session_id)

    return session_obj


@router.post("/sessions/{session_id}/resume", response_model=SessionResponse)
def resume_session(
    session_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Resume/Continue a paused academic session, re-enabling active policy enforcement.
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)

    now = datetime.now(timezone.utc)
    session_obj.status = "active"
    session_obj.is_active = True
    if not session_obj.started_at:
        session_obj.started_at = now
    session_obj.policy_version += 1
    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="SESSION_RESUMED",
        resource_id=session_obj.id,
        details=f"Resumed session '{session_obj.title}'"
    )

    from ..core.sockets import broadcast_socket_event
    broadcast_socket_event("session_resumed", {"session_id": session_id, "status": "active"}, session_id)
    broadcast_socket_event("session_updated", {"session_id": session_id, "status": "active"}, session_id)

    return session_obj


@router.patch("/sessions/{session_id}/status", response_model=SessionResponse)
def update_session_status(
    session_id: str,
    req: Union[SessionStatusUpdate, dict] = Body(...),
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Unified endpoint to update session status (active/resume, pause/paused, completed/ended, cancelled).
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)

    now = datetime.now(timezone.utc)
    raw_status = req.status if isinstance(req, SessionStatusUpdate) else (req.get("status") if isinstance(req, dict) else str(req))
    target_status = (raw_status or "").strip().lower()

    if target_status in ("pause", "paused"):
        session_obj.status = "paused"
        session_obj.is_active = False
    elif target_status in ("resume", "active", "start", "started", "continue"):
        session_obj.status = "active"
        session_obj.is_active = True
        session_obj.started_at = session_obj.started_at or now
        curr_start_utc = _ensure_utc(session_obj.start_at_utc)
        curr_end_utc = _ensure_utc(session_obj.end_at_utc)
        if not curr_start_utc or curr_start_utc > now:
            if curr_end_utc and curr_start_utc:
                duration = curr_end_utc - curr_start_utc
                session_obj.end_at_utc = now + max(duration, timedelta(minutes=15))
            else:
                session_obj.end_at_utc = now + timedelta(hours=1)
            session_obj.start_at_utc = now
        elif curr_end_utc and curr_end_utc <= now:
            session_obj.end_at_utc = now + timedelta(hours=1)
        session_obj.start_at = session_obj.start_at_utc
        session_obj.end_at = session_obj.end_at_utc
    elif target_status in ("completed", "ended", "end"):
        session_obj.status = "ended"
        session_obj.is_active = False
        session_obj.ended_at = now
        from ..models.device import AgentPolicy
        db.query(AgentPolicy).filter(
            AgentPolicy.session_id == session_id,
            AgentPolicy.revoked_at.is_(None)
        ).update({"revoked_at": now})
    elif target_status in ("cancelled", "cancel"):
        session_obj.status = "cancelled"
        session_obj.is_active = False
    else:
        session_obj.status = target_status

    session_obj.policy_version += 1
    session_obj.updated_at = now
    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="SESSION_STATUS_CHANGED",
        resource_id=session_obj.id,
        details=f"Changed status of session '{session_obj.title}' to '{session_obj.status}'"
    )

    from ..core.sockets import broadcast_socket_event
    if session_obj.status == "active":
        broadcast_socket_event("session_started", {"session_id": session_id, "status": "active"}, session_id)
    broadcast_socket_event("session_updated", {"session_id": session_id, "status": session_obj.status}, session_id)

    return session_obj



@router.get("/professor/sessions/{session_id}/live", response_model=LiveMonitorResponse)
def get_professor_session_live_monitor(
    session_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Get real-time live monitor data for professor's session.
    STRICT RBAC: Return only professor's own session data.
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)
    _sync_scheduled_session_state(session_obj)

    participants = db.query(SessionParticipant).filter(
        SessionParticipant.session_id == session_id
    ).all()

    student_ids = [p.student_id for p in participants]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(student_ids)).all()} if student_ids else {}
    presence_records = {p.student_id: p for p in db.query(SessionPresence).filter(SessionPresence.session_id == session_id).all()}

    from ..models.telemetry import PolicyViolation, TelemetryEvent
    from ..models.audit_log import AuditLog
    from ..models.engagement import EngagementFeatureWindow
    from sqlalchemy import func

    # Calculate authoritative violation count for this specific session
    pv_count = db.query(PolicyViolation).filter(PolicyViolation.session_id == session_id).count()
    violation_count = pv_count

    assignments = {
        a.student_id: a
        for a in db.query(AgentPolicyAssignment).filter(AgentPolicyAssignment.session_id == session_id).all()
    }
    enforcing_devices_count = db.query(AgentPolicyAssignment).filter(
        AgentPolicyAssignment.session_id == session_id,
        AgentPolicyAssignment.state == "active"
    ).count()

    student_items = []
    online_count = 0
    joined_count = 0

    from ..core.sockets import calculate_student_presence_dict

    devices_by_user = {}
    if student_ids:
        for d in db.query(AgentDevice).filter(AgentDevice.user_id.in_(student_ids)).all():
            devices_by_user.setdefault(d.user_id, []).append(d.id)

    for p in participants:
        u = users.get(p.student_id)
        u_name = u.full_name if u else "Student"
        pres = presence_records.get(p.student_id)

        item_dict = calculate_student_presence_dict(pres, p.status, u_name)
        item_dict["student_id"] = p.student_id

        # Calculate student specific violations strictly for this session
        dev_ids = devices_by_user.get(p.student_id, [])
        if dev_ids:
            s_pv = db.query(PolicyViolation).filter(
                PolicyViolation.session_id == session_id,
                PolicyViolation.device_id.in_(dev_ids)
            ).count()
        else:
            s_pv = db.query(PolicyViolation).filter(
                PolicyViolation.session_id == session_id
            ).count()

        item_dict["violation_count"] = s_pv

        # Calculate blocked website and app breakdown
        blocked_web_cnt = 0
        blocked_app_cnt = 0
        if dev_ids:
            blocked_web_cnt = db.query(PolicyViolation).filter(
                PolicyViolation.session_id == session_id,
                PolicyViolation.device_id.in_(dev_ids),
                PolicyViolation.violation_type.in_(["web", "dns", "url"])
            ).count()
            blocked_app_cnt = db.query(PolicyViolation).filter(
                PolicyViolation.session_id == session_id,
                PolicyViolation.device_id.in_(dev_ids),
                PolicyViolation.violation_type.in_(["process", "application"])
            ).count()
        item_dict["blocked_website_attempts"] = blocked_web_cnt
        item_dict["blocked_app_attempts"] = blocked_app_cnt

        # Determine USB restriction status honestly
        s_device = None
        if dev_ids:
            s_device = db.query(AgentDevice).filter(AgentDevice.id.in_(dev_ids)).first()
        dev_caps = s_device.capabilities_json or {} if s_device else {}
        usb_raw = dev_caps.get("usb_storage_restriction_status") or dev_caps.get("usb_storage_policy")
        if usb_raw == "active" or usb_raw == "restricted":
            usb_badge = "Active"
        elif usb_raw in ("unsupported", "unavailable"):
            usb_badge = "Unsupported"
        elif usb_raw in ("requires_managed_device", "requires_mdm"):
            usb_badge = "Requires Managed Device"
        else:
            usb_badge = "Not Compliant" if session_obj.is_active else "Requires Managed Device"
        item_dict["usb_storage_status"] = usb_badge
        item_dict["device_compliance_status"] = s_device.compliance_status if s_device else "compliant"
        item_dict["website_filtering_status"] = "active" if session_obj.is_active else "idle"
        item_dict["application_control_status"] = "active" if session_obj.is_active else "idle"

        # Determine enforcement / policy status badge
        assign = assignments.get(p.student_id)
        if assign:
            item_dict["enforcement_status"] = assign.state
            pol_st = assign.state.capitalize()
            if pol_st not in ("Pending", "Active", "Restored", "Failed"):
                pol_st = "Active"
            item_dict["policy_status"] = pol_st
        elif session_obj.is_active:
            item_dict["enforcement_status"] = "active"
            item_dict["policy_status"] = "Active"
        else:
            item_dict["enforcement_status"] = "restored"
            item_dict["policy_status"] = "Restored"

        # Academic activity summary & engagement state from engagement feature windows
        latest_efw = db.query(EngagementFeatureWindow).filter(
            EngagementFeatureWindow.session_id == session_id,
            EngagementFeatureWindow.student_id == p.student_id
        ).order_by(EngagementFeatureWindow.window_end_at.desc()).first()

        acad_summary = {}
        if latest_efw:
            acad_mins = int(round(latest_efw.academic_active_seconds / 60.0))
            acad_summary["Academic Activity"] = f"{max(1, acad_mins)} min"
            # Try to read granular breakdown if present
            if hasattr(latest_efw, "raw_telemetry_json") and isinstance(latest_efw.raw_telemetry_json, dict):
                bd = latest_efw.raw_telemetry_json.get("academic_breakdown", {})
                if bd:
                    acad_summary = {k: f"{int(round(v/60.0))} min" for k, v in bd.items()}
            item_dict["engagement_state"] = "Collecting Live Data" if session_obj.is_active else "Final"
        else:
            item_dict["engagement_state"] = "Collecting Live Data" if session_obj.is_active else "Data Insufficient"
        item_dict["academic_activity_summary"] = acad_summary

        if p.status == "joined":
            joined_count += 1
            if item_dict["presence_status"] == "online":
                online_count += 1
            
            # If student has violations, show latest blocked resource
            if s_pv > 0:
                latest_pv = db.query(PolicyViolation).filter(
                    PolicyViolation.session_id == session_id,
                    PolicyViolation.device_id.in_(dev_ids)
                ).order_by(PolicyViolation.occurred_at.desc()).first() if dev_ids else None
                if latest_pv:
                    target = str(latest_pv.target_value or "")
                    t_lower = target.lower()
                    is_proc = latest_pv.violation_type == "process" or t_lower.endswith(".exe")
                    is_usb = latest_pv.violation_type == "usb" or "usb" in t_lower or "drive" in t_lower
                    prefix = "Blocked App" if is_proc else ("Blocked USB Storage" if is_usb else "Restricted Site")
                    item_dict["latest_activity"] = f"{prefix}: {target}"
                else:
                    item_dict["latest_activity"] = f"Violations: {s_pv}"
            else:
                item_dict["latest_activity"] = "STUDENT_JOINED"
        else:
            item_dict["latest_activity"] = "STUDENT_LEFT"

        student_items.append(LiveMonitorStudentItem(**item_dict))

    # Sort: Online joined students first, then joined, then left
    student_items.sort(key=lambda s: (0 if (s.participant_status == "joined" and s.presence_status == "online") else (1 if s.participant_status == "joined" else 2), s.name))

    session_student_viols = sum(s.violation_count for s in student_items)
    violation_count = max(violation_count, session_student_viols)

    batch_name_val = session_obj.batch.name if session_obj.batch else None
    return LiveMonitorResponse(
        session_id=session_id,
        batch_name=batch_name_val,
        session_title=session_obj.title,
        policy_version=session_obj.policy_version or 1,
        status=session_obj.status,
        students=student_items,
        online_count=online_count,
        joined_count=joined_count,
        enforcing_count=enforcing_devices_count if enforcing_devices_count > 0 else (len(participants) if session_obj.is_active else 0),
        violation_count=violation_count
    )





@router.post("/sessions/{session_id}/cancel", response_model=SessionResponse)
def cancel_session(
    session_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Cancel an academic session and immediately revoke all agent policy assignments.
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)

    now = datetime.now(timezone.utc)
    session_obj.status = "cancelled"
    session_obj.is_active = False
    session_obj.ended_at = now
    session_obj.policy_version = (session_obj.policy_version or 1) + 1

    # Revoke all active policy assignments
    db.query(AgentPolicyAssignment).filter(
        AgentPolicyAssignment.session_id == session_id,
        AgentPolicyAssignment.state.in_(["pending", "active"])
    ).update({
        "state": "revoked",
        "revoked_at": now,
        "restored_at": now,
        "failure_reason": "Session cancelled by professor"
    }, synchronize_session=False)

    db.query(AgentPolicy).filter(
        AgentPolicy.session_id == session_id,
        AgentPolicy.revoked_at.is_(None)
    ).update({"revoked_at": now}, synchronize_session=False)

    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="SESSION_CANCELLED",
        resource_id=session_obj.id,
        details=f"Cancelled session '{session_obj.title}'"
    )

    broadcast_socket_event("session_cancelled", {"session_id": session_id, "status": "cancelled"}, session_id)
    broadcast_socket_event("policy_revoked", {"session_id": session_id, "reason": "session_cancelled"}, session_id)
    broadcast_socket_event("session_updated", {"session_id": session_id, "status": "cancelled"}, session_id)

    return session_obj


@router.post("/sessions/{session_id}/emergency-stop", response_model=SessionResponse)
def emergency_stop_session(
    session_id: str,
    req: Optional[dict] = None,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Emergency Stop: Immediately halt all endpoint restrictions, restore network adapters, and revoke policy assignments with mandatory audit logging.
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    _verify_session_owner(session_obj, current_user, db)

    now = datetime.now(timezone.utc)
    reason = (req or {}).get("reason", "Professor authorized emergency stop")

    session_obj.status = "ended"
    session_obj.is_active = False
    session_obj.ended_at = now
    session_obj.emergency_stopped_at = now
    session_obj.emergency_stopped_by = current_user.id
    session_obj.emergency_stop_reason = reason
    session_obj.policy_version = (session_obj.policy_version or 1) + 1

    # Revoke and mark restored on all assignments
    db.query(AgentPolicyAssignment).filter(
        AgentPolicyAssignment.session_id == session_id
    ).update({
        "state": "restored",
        "revoked_at": now,
        "restored_at": now,
        "failure_reason": f"Emergency Stop: {reason}"
    }, synchronize_session=False)

    db.query(AgentPolicy).filter(
        AgentPolicy.session_id == session_id,
        AgentPolicy.revoked_at.is_(None)
    ).update({"revoked_at": now}, synchronize_session=False)

    db.commit()
    db.refresh(session_obj)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="EMERGENCY_STOP",
        resource_id=session_obj.id,
        details=f"EMERGENCY STOP executed on session '{session_obj.title}'. Reason: {reason}. All student endpoint restrictions revoked."
    )

    broadcast_socket_event("emergency_stop", {"session_id": session_id, "reason": reason}, session_id)
    broadcast_socket_event("policy_revoked", {"session_id": session_id, "reason": f"emergency_stop: {reason}"}, session_id)
    broadcast_socket_event("session_ended", {"session_id": session_id, "status": "ended", "is_emergency": True}, session_id)
    broadcast_socket_event("session_updated", {"session_id": session_id, "status": "ended"}, session_id)

    return session_obj


# ==============================================================================
# STUDENT SESSION ENDPOINTS
# ==============================================================================

@router.get("/student/sessions", response_model=List[SessionStudentResponse])
def get_student_sessions(
    batch_id: Optional[str] = None,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    List sessions for batches actively joined by the student.
    Filterable by optional ?batch_id= parameter.
    """
    memberships = db.query(BatchMember).filter(
        BatchMember.student_id == current_user.id,
        BatchMember.status == "active"
    ).all()

    joined_batch_ids = [m.batch_id for m in memberships]

    if not joined_batch_ids:
        return []

    if batch_id:
        if batch_id not in joined_batch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You have not joined this batch."
            )
        target_batch_ids = [batch_id]
    else:
        target_batch_ids = joined_batch_ids

    sessions = db.query(SessionModel).filter(SessionModel.batch_id.in_(target_batch_ids)).all()
    state_changed = False
    for session in sessions:
        state_changed = _sync_scheduled_session_state(session) or state_changed
    if state_changed:
        db.commit()

    # Pre-fetch batch names and professor names for presentation
    batches = db.query(Batch).filter(Batch.id.in_(target_batch_ids)).all()
    batch_map = {b.id: b.name for b in batches}
    prof_ids = list(set([b.professor_id for b in batches]))
    prof_users = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(prof_ids)).all()} if prof_ids else {}

    # Get student's active joined participant sessions
    joined_participant_session_ids = set(
        p.session_id for p in db.query(SessionParticipant).filter(
            SessionParticipant.student_id == current_user.id,
            SessionParticipant.status == "joined"
        ).all()
    )

    result = []
    for s in sessions:
        b_name = batch_map.get(s.batch_id, "Unknown Batch")
        b_obj = next((b for b in batches if b.id == s.batch_id), None)
        p_name = prof_users.get(b_obj.professor_id, "Professor") if b_obj else "Professor"

        result.append(SessionStudentResponse(
            id=s.id,
            batch_id=s.batch_id,
            batch_name=b_name,
            professor_name=p_name,
            title=s.title,
            description=s.description or "",
            start_at_utc=s.start_at_utc,
            end_at_utc=s.end_at_utc,
            started_at=s.started_at,
            ended_at=s.ended_at,
            timezone=s.timezone,
            status=s.status,
            is_active=s.is_active,
            is_joined=s.id in joined_participant_session_ids,
            rule_set_id=s.rule_set_id,
            policy_version=s.policy_version,
            created_at=s.created_at,
            updated_at=s.updated_at
        ))

    return result


@router.get("/student/batches/{batch_id}/sessions", response_model=List[SessionStudentResponse])
def get_student_batch_sessions(
    batch_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    List sessions for a specific joined batch for student.
    STRICT SECURITY RULE: Returns 403 Forbidden if the student is not an active member.
    """
    membership = db.query(BatchMember).filter(
        BatchMember.batch_id == batch_id,
        BatchMember.student_id == current_user.id,
        BatchMember.status == "active"
    ).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You have not joined this batch."
        )

    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    batch_name = batch.name if batch else "Unknown Batch"
    prof_user = db.query(User).filter(User.id == batch.professor_id).first() if batch else None
    prof_name = prof_user.full_name if prof_user else "Professor"

    sessions = db.query(SessionModel).filter(SessionModel.batch_id == batch_id).all()
    state_changed = False
    for session in sessions:
        state_changed = _sync_scheduled_session_state(session) or state_changed
    if state_changed:
        db.commit()

    joined_participant_session_ids = set(
        p.session_id for p in db.query(SessionParticipant).filter(
            SessionParticipant.student_id == current_user.id,
            SessionParticipant.status == "joined"
        ).all()
    )

    result = []
    for s in sessions:
        result.append(SessionStudentResponse(
            id=s.id,
            batch_id=s.batch_id,
            batch_name=batch_name,
            professor_name=prof_name,
            title=s.title,
            description=s.description or "",
            start_at_utc=s.start_at_utc,
            end_at_utc=s.end_at_utc,
            started_at=s.started_at,
            ended_at=s.ended_at,
            timezone=s.timezone,
            status=s.status,
            is_active=s.is_active,
            is_joined=s.id in joined_participant_session_ids,
            rule_set_id=s.rule_set_id,
            policy_version=s.policy_version,
            created_at=s.created_at,
            updated_at=s.updated_at
        ))

    return result



@router.get("/student/sessions/{session_id}", response_model=SessionStudentResponse)
def get_student_session_details(
    session_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    Get safe session details for student.
    Returns 403 Forbidden if the student is not an active member of assigned batch.
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    has_membership = False
    if session_obj.batch_id:
        membership = db.query(BatchMember).filter(
            BatchMember.batch_id == session_obj.batch_id,
            BatchMember.student_id == current_user.id,
            BatchMember.status == "active"
        ).first()
        if membership:
            has_membership = True

    if not has_membership and session_obj.class_id:
        from ..models.class_model import ClassMember
        c_membership = db.query(ClassMember).filter(
            ClassMember.class_id == session_obj.class_id,
            ClassMember.student_id == current_user.id
        ).first()
        if c_membership:
            has_membership = True

    if not has_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You have not joined the batch or class assigned to this session."
        )

    _sync_scheduled_session_state(session_obj)

    b_obj = db.query(Batch).filter(Batch.id == session_obj.batch_id).first() if session_obj.batch_id else None
    b_name = b_obj.name if b_obj else "Class Session"
    prof_user = db.query(User).filter(User.id == (b_obj.professor_id if b_obj else session_obj.created_by)).first()
    p_name = prof_user.full_name if prof_user else "Professor"

    participant = db.query(SessionParticipant).filter(
        SessionParticipant.session_id == session_id,
        SessionParticipant.student_id == current_user.id,
        SessionParticipant.status == "joined"
    ).first()

    return SessionStudentResponse(
        id=session_obj.id,
        batch_id=session_obj.batch_id,
        batch_name=b_name,
        professor_name=p_name,
        title=session_obj.title,
        description=session_obj.description or "",
        start_at_utc=session_obj.start_at_utc,
        end_at_utc=session_obj.end_at_utc,
        started_at=session_obj.started_at,
        ended_at=session_obj.ended_at,
        timezone=session_obj.timezone,
        status=session_obj.status,
        is_active=session_obj.is_active,
        is_joined=participant is not None,
        rule_set_id=session_obj.rule_set_id,
        policy_version=session_obj.policy_version,
        created_at=session_obj.created_at,
        updated_at=session_obj.updated_at
    )


@router.post("/sessions/{session_id}/join", status_code=status.HTTP_200_OK)
@router.post("/student/sessions/{session_id}/join", status_code=status.HTTP_200_OK)
def student_join_session_endpoint(
    session_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    Manually join an active session (Student only).
    """
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    has_membership = False
    if session_obj.batch_id:
        membership = db.query(BatchMember).filter(
            BatchMember.batch_id == session_obj.batch_id,
            BatchMember.student_id == current_user.id,
            BatchMember.status == "active"
        ).first()
        if membership:
            has_membership = True

    if not has_membership and session_obj.class_id:
        from ..models.class_model import ClassMember
        c_membership = db.query(ClassMember).filter(
            ClassMember.class_id == session_obj.class_id,
            ClassMember.student_id == current_user.id
        ).first()
        if c_membership:
            has_membership = True

    if not has_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You have not joined the batch or class assigned to this session."
        )

    _sync_scheduled_session_state(session_obj)

    if session_obj.status.lower() != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot join session. Current status is '{session_obj.status}'. The professor must start the session first."
        )

    existing = db.query(SessionParticipant).filter(
        SessionParticipant.session_id == session_id,
        SessionParticipant.student_id == current_user.id
    ).first()

    now = datetime.now(timezone.utc)
    if existing:
        if existing.status == "joined":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already joined this session."
            )
        existing.status = "joined"
        existing.joined_at = now
        existing.left_at = None
        existing.enforcement_activated_at = now
        participant = existing
    else:
        participant = SessionParticipant(
            session_id=session_id,
            student_id=current_user.id,
            status="joined",
            joined_at=now,
            enforcement_activated_at=now
        )
        db.add(participant)

    # Create/activate AgentPolicyAssignment for all student's enrolled devices
    devices = db.query(AgentDevice).filter(AgentDevice.user_id == current_user.id, AgentDevice.is_active == True).all()
    if devices:
        for dev in devices:
            assignment = db.query(AgentPolicyAssignment).filter(
                AgentPolicyAssignment.session_id == session_id,
                AgentPolicyAssignment.student_id == current_user.id,
                AgentPolicyAssignment.device_id == dev.id
            ).first()
            if not assignment:
                assignment = AgentPolicyAssignment(
                    session_id=session_id,
                    student_id=current_user.id,
                    device_id=dev.id,
                    state="active",
                    assigned_at=now,
                    activated_at=now,
                    last_heartbeat_at=now
                )
                db.add(assignment)
            else:
                assignment.state = "active"
                assignment.activated_at = now
                assignment.last_heartbeat_at = now
    else:
        # Fallback assignment without device link until device enrolls
        assignment = db.query(AgentPolicyAssignment).filter(
            AgentPolicyAssignment.session_id == session_id,
            AgentPolicyAssignment.student_id == current_user.id,
            AgentPolicyAssignment.device_id.is_(None)
        ).first()
        if not assignment:
            assignment = AgentPolicyAssignment(
                session_id=session_id,
                student_id=current_user.id,
                device_id=None,
                state="active",
                assigned_at=now,
                activated_at=now,
                last_heartbeat_at=now
            )
            db.add(assignment)

    presence = db.query(SessionPresence).filter(
        SessionPresence.session_id == session_id,
        SessionPresence.student_id == current_user.id
    ).first()

    if not presence:
        presence = SessionPresence(
            session_id=session_id,
            student_id=current_user.id,
            browser_last_seen_at=now,
            connected_socket_count=1,
            joined_at=now,
            updated_at=now
        )
        db.add(presence)
    else:
        presence.browser_last_seen_at = now
        presence.connected_socket_count = max(1, getattr(presence, 'connected_socket_count', 0) or 1)
        presence.updated_at = now

    db.commit()

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="STUDENT_JOINED",
        resource_id=session_obj.id,
        details=f"Student '{current_user.full_name}' joined session '{session_obj.title}'. Device policy enforcement activated."
    )

    from ..core.sockets import broadcast_socket_event, calculate_student_presence_dict
    presence_info = calculate_student_presence_dict(presence, "joined", current_user.full_name)
    presence_info["latest_activity"] = "STUDENT_JOINED"
    presence_info["enforcement_status"] = "active"
    broadcast_socket_event("student_joined", presence_info, session_id)
    broadcast_socket_event("policy_available", {"session_id": session_id, "student_id": current_user.id}, session_id)

    return {
        "status": "ok",
        "sessionId": session_obj.id,
        "joined": True,
        "joined_at": now.isoformat(),
        "message": "Protection will remain active until the professor ends this session.",
        "protection_notice": "Protection will remain active until the professor ends this session.",
        "socket_config": {
            "room": f"session_{session_obj.id}",
            "session_id": session_obj.id
        }
    }


@router.post("/sessions/{session_id}/leave", status_code=status.HTTP_200_OK)
@router.post("/student/sessions/{session_id}/leave", status_code=status.HTTP_200_OK)
def student_leave_session_endpoint(
    session_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    Leave session web portal (Student only).
    NOTE: Device policy enforcement remains active until professor ends session.
    """
    participant = db.query(SessionParticipant).filter(
        SessionParticipant.session_id == session_id,
        SessionParticipant.student_id == current_user.id
    ).first()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are not enrolled in this session."
        )

    now = datetime.now(timezone.utc)
    participant.status = "left"
    participant.left_at = now

    presence = db.query(SessionPresence).filter(
        SessionPresence.session_id == session_id,
        SessionPresence.student_id == current_user.id
    ).first()
    if presence:
        presence.connected_socket_count = 0
        presence.updated_at = now

    db.commit()

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="STUDENT_LEFT",
        resource_id=session_id,
        details=f"Student '{current_user.full_name}' left website portal. Device protection remains active."
    )

    from ..core.sockets import broadcast_socket_event, calculate_student_presence_dict
    presence_info = calculate_student_presence_dict(presence, "left", current_user.full_name)
    presence_info["latest_activity"] = "STUDENT_LEFT"
    presence_info["enforcement_status"] = "active"
    broadcast_socket_event("student_left", presence_info, session_id)
    broadcast_socket_event("presence_updated", presence_info, session_id)

    return {
        "status": "ok",
        "message": "You left the website session. Device protection remains active until the professor ends the session.",
        "protection_notice": "You left the website session. Device protection remains active until the professor ends the session."
    }



# ==============================================================================
# GENERIC /SESSIONS ENDPOINTS (FRONTEND COMPATIBILITY)
# ==============================================================================

from datetime import timedelta

@router.get("/sessions", response_model=List[dict])
def get_sessions_generic(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all sessions formatted for frontend Sessions page."""
    if current_user.role == "student":
        memberships = db.query(BatchMember).filter(
            BatchMember.student_id == current_user.id,
            BatchMember.status == "active"
        ).all()
        joined_batch_ids = [m.batch_id for m in memberships]
        if not joined_batch_ids:
            return []
        sessions = db.query(SessionModel).filter(SessionModel.batch_id.in_(joined_batch_ids)).all()
    elif current_user.role == "professor":
        prof_batches = db.query(Batch).filter(Batch.professor_id == current_user.id).all()
        p_batch_ids = [b.id for b in prof_batches]
        sessions = db.query(SessionModel).filter(
            (SessionModel.created_by == current_user.id) | (SessionModel.batch_id.in_(p_batch_ids))
        ).order_by(SessionModel.start_at_utc.desc()).all()
    else:
        sessions = db.query(SessionModel).order_by(SessionModel.start_at_utc.desc()).all()

    batch_map = {b.id: b for b in db.query(Batch).all()}

    session_ids = [s.id for s in sessions]
    from ..models.telemetry import PolicyViolation, TelemetryEvent
    from ..models.audit_log import AuditLog
    from sqlalchemy import func

    # Batch compute real-time violations per session
    pv_counts = dict(
        db.query(PolicyViolation.session_id, func.count(PolicyViolation.id))
        .filter(PolicyViolation.session_id.in_(session_ids))
        .group_by(PolicyViolation.session_id)
        .all()
    ) if session_ids else {}

    audit_viol_counts = dict(
        db.query(AuditLog.entity_id, func.count(AuditLog.id))
        .filter(
            AuditLog.entity_id.in_(session_ids),
            AuditLog.action.in_(["VIOLATION", "POLICY_VIOLATION"])
        )
        .group_by(AuditLog.entity_id)
        .all()
    ) if session_ids else {}

    telem_viol_counts = dict(
        db.query(TelemetryEvent.session_id, func.count(TelemetryEvent.id))
        .filter(
            TelemetryEvent.session_id.in_(session_ids),
            TelemetryEvent.event_type.in_(["application_violation", "process_violation", "dns_block", "tamper_alert", "usb_storage_violation"])
        )
        .group_by(TelemetryEvent.session_id)
        .all()
    ) if session_ids else {}

    result = []
    now_dt = datetime.now(timezone.utc)
    for s in sessions:
        b_obj = batch_map.get(s.batch_id) if s.batch_id else None
        course_name = b_obj.name if b_obj else "General Class"
        batch_ids = [s.batch_id] if s.batch_id else []

        if not s.rule_set_id:
            if s.batch_id:
                b_rs = db.query(RuleSet).filter(RuleSet.batch_id == s.batch_id, RuleSet.is_active == True).first()
                if b_rs:
                    s.rule_set_id = b_rs.id
            if not s.rule_set_id and s.created_by:
                p_rs = db.query(RuleSet).filter(RuleSet.created_by == s.created_by, RuleSet.is_active == True).order_by(RuleSet.updated_at.desc()).first()
                if p_rs:
                    s.rule_set_id = p_rs.id
            if s.rule_set_id:
                try:
                    db.commit()
                except Exception:
                    db.rollback()

        start_dt = s.started_at or s.start_at_utc or s.start_at or s.created_at or now_dt
        end_dt = s.end_at_utc or s.end_at or s.created_at or (now_dt + timedelta(hours=2))
        created_dt = s.created_at or now_dt
        updated_dt = s.updated_at or now_dt

        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        raw_status = (s.status or "scheduled").strip().lower()
        if raw_status in ("active", "resume", "continue"):
            if end_dt and now_dt >= end_dt:
                s.status = "ended"
                s.is_active = False
                calc_status = "Completed"
            else:
                calc_status = "Active"
        elif raw_status in ("paused", "pause"):
            calc_status = "Paused"
        elif raw_status in ("ended", "completed"):
            calc_status = "Completed"
        elif raw_status in ("cancelled", "cancel"):
            calc_status = "Cancelled"
        else:
            # Scheduled / Upcoming sessions stay Upcoming until the professor explicitly starts them
            calc_status = "Upcoming"

        sess_viols = max(pv_counts.get(s.id, 0), audit_viol_counts.get(s.id, 0), telem_viol_counts.get(s.id, 0))

        result.append({
            "_id": s.id,
            "id": s.id,
            "title": s.title or "Academic Session",
            "course": course_name,
            "type": "Lecture",
            "startTime": start_dt.isoformat(),
            "endTime": end_dt.isoformat(),
            "status": calc_status,
            "ruleSetId": s.rule_set_id,
            "batchIds": batch_ids,
            "professorId": s.created_by,
            "violationCount": sess_viols,
            "violation_count": sess_viols,
            "createdAt": created_dt.isoformat(),
            "updatedAt": updated_dt.isoformat()
        })

    return result

@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session_generic(
    req: dict,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Create a new session from frontend React form."""
    try:
        raw_title = req.get("title")
        if not raw_title or not str(raw_title).strip():
            title = "New Academic Session"
        else:
            title = str(raw_title).strip()

        course = req.get("course", "")

        batch_ids = req.get("batch_ids") or req.get("batchIds") or []
        raw_batch_id = req.get("batch_id") or req.get("batchId") or (batch_ids[0] if isinstance(batch_ids, list) and batch_ids else None)
        batch_id = None
        if raw_batch_id and str(raw_batch_id).strip():
            clean_batch_id = str(raw_batch_id).strip()
            batch = db.query(Batch).filter(Batch.id == clean_batch_id).first()
            if not batch:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected batch was not found.")
            if current_user.role != "admin" and batch.professor_id != current_user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can create sessions only for batches you own.")
            batch_id = clean_batch_id

        raw_rule_id = req.get("rule_id") or req.get("ruleSetId")
        rule_id = None
        if raw_rule_id and str(raw_rule_id).strip():
            clean_rule_id = str(raw_rule_id).strip()
            rule_exists = db.query(RuleSet).filter(RuleSet.id == clean_rule_id).first()
            if rule_exists:
                rule_id = clean_rule_id

        if not rule_id and batch_id:
            batch_rs = db.query(RuleSet).filter(RuleSet.batch_id == batch_id, RuleSet.is_active == True).first()
            if batch_rs:
                rule_id = batch_rs.id
        if not rule_id:
            prof_rs = db.query(RuleSet).filter(RuleSet.created_by == current_user.id, RuleSet.is_active == True).order_by(RuleSet.updated_at.desc()).first()
            if prof_rs:
                rule_id = prof_rs.id
        if not rule_id:
            any_rs = db.query(RuleSet).filter(RuleSet.is_active == True).order_by(RuleSet.updated_at.desc()).first()
            if any_rs:
                rule_id = any_rs.id

        start_iso = req.get("start_time") or req.get("startTime")
        end_iso = req.get("end_time") or req.get("endTime")

        now = datetime.now(timezone.utc)
        try:
            start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00")) if start_iso else now
        except Exception:
            start_dt = now

        try:
            end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else now + timedelta(hours=2)
        except Exception:
            end_dt = now + timedelta(hours=2)

        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=1)

        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        is_active = (start_dt <= now <= end_dt)
        session_status = "active" if is_active else "scheduled"

        raw_class_id = req.get("class_id") or req.get("classId")
        class_id = str(raw_class_id).strip() if raw_class_id and str(raw_class_id).strip() else None

        session_obj = SessionModel(
            batch_id=batch_id,
            class_id=class_id,
            created_by=current_user.id,
            title=title,
            start_at=start_dt,
            end_at=end_dt,
            start_at_utc=start_dt,
            end_at_utc=end_dt,
            timezone="UTC",
            rule_set_id=rule_id,
            status=session_status,
            is_active=is_active,
            policy_version=1
        )
        _sync_scheduled_session_state(session_obj, now)
        db.add(session_obj)
        db.commit()
        db.refresh(session_obj)

        b_obj = db.query(Batch).filter(Batch.id == session_obj.batch_id).first() if session_obj.batch_id else None
        course_name = course or (b_obj.name if b_obj else "General Class")

        return {
            "_id": session_obj.id,
            "id": session_obj.id,
            "title": session_obj.title,
            "course": course_name,
            "type": req.get("type", "Lecture"),
            "startTime": session_obj.start_at_utc.isoformat(),
            "endTime": session_obj.end_at_utc.isoformat(),
            "status": session_obj.status.capitalize(),
            "ruleSetId": session_obj.rule_set_id,
            "batchIds": [session_obj.batch_id] if session_obj.batch_id else [],
            "professorId": session_obj.created_by,
            "createdAt": session_obj.created_at.isoformat() if session_obj.created_at else now.isoformat(),
            "updatedAt": session_obj.updated_at.isoformat() if session_obj.updated_at else now.isoformat()
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create session: {str(e)}"
        )



@router.delete("/sessions/{session_id}")
def delete_session_generic(
    session_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    _verify_session_owner(session_obj, current_user, db)
    db.delete(session_obj)
    db.commit()
    return {"status": "success", "message": "Session deleted"}


@router.get("/logs", response_model=List[dict])
def get_logs_generic(
    sessionId: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch real-time activity, policy violations, and telemetry logs for a session or globally."""
    session_dev_ids = []
    part_student_ids = []
    if sessionId:
        part_student_ids = [p.student_id for p in db.query(SessionParticipant).filter(SessionParticipant.session_id == sessionId).all()]
        if part_student_ids:
            session_dev_ids = [d.id for d in db.query(AgentDevice).filter(AgentDevice.user_id.in_(part_student_ids)).all()]

    # 1. Fetch real PolicyViolations
    violations_query = db.query(PolicyViolation)
    if sessionId:
        violations_query = violations_query.filter(PolicyViolation.session_id == sessionId)
    violations = violations_query.order_by(desc(PolicyViolation.occurred_at)).limit(100).all()

    # 2. Fetch real TelemetryEvents
    telemetry_query = db.query(TelemetryEvent)
    if sessionId:
        telemetry_query = telemetry_query.filter(TelemetryEvent.session_id == sessionId)
    telemetry_events = telemetry_query.order_by(desc(TelemetryEvent.occurred_at)).limit(100).all()

    # 3. Fetch AuditLogs
    audit_query = db.query(AuditLog)
    if sessionId:
        audit_query = audit_query.filter(AuditLog.entity_id == sessionId)
    audit_logs = audit_query.order_by(desc(AuditLog.created_at)).limit(100).all()

    # Prefetch devices
    device_ids = set(
        [t.device_id for t in telemetry_events if t.device_id] +
        [v.device_id for v in violations if v.device_id]
    )
    devices = {d.id: d for d in db.query(AgentDevice).filter(AgentDevice.id.in_(device_ids)).all()} if device_ids else {}

    # Prefetch users
    user_ids = set(
        [d.user_id for d in devices.values() if d.user_id] +
        [v.device_id for v in violations if v.device_id and v.device_id not in devices] +
        [log.actor_user_id for log in audit_logs if log.actor_user_id]
    )
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    # Prefetch sessions for titles
    sess_ids = set(
        [t.session_id for t in telemetry_events if t.session_id] +
        [v.session_id for v in violations if v.session_id] +
        [log.entity_id for log in audit_logs if log.entity_id]
    )
    sessions_map = {s.id: s.title for s in db.query(SessionModel).filter(SessionModel.id.in_(sess_ids)).all()} if sess_ids else {}

    result = []
    seen_ids = set()
    seen_viol_signatures = set()

    for v in violations:
        dev = devices.get(v.device_id)
        user = users.get(dev.user_id) if dev else users.get(v.device_id)
        u_name = (user.full_name or user.email) if user else "Student"
        sap_id = getattr(user, 'roll_number', None) or getattr(user, 'institutional_id', '') or ""

        target_str = str(v.target_value or "").strip().lower()
        sig = (v.session_id, v.device_id, target_str)
        seen_viol_signatures.add(sig)

        viol_key = f"viol-{v.id}"
        if viol_key not in seen_ids:
            seen_ids.add(viol_key)
            result.append({
                "_id": viol_key,
                "id": v.id,
                "type": "VIOLATION",
                "studentId": user.id if user else (dev.user_id if dev else ""),
                "studentName": u_name,
                "sapId": sap_id,
                "sessionId": v.session_id or "",
                "sessionTitle": sessions_map.get(v.session_id, ""),
                "resource": v.target_value,
                "details": f"Policy Enforcement: Blocked ({v.target_value})",
                "duration": 60,
                "engagementScore": 30,
                "isViolation": True,
                "timestamp": v.occurred_at.isoformat() if hasattr(v.occurred_at, 'isoformat') else str(v.occurred_at)
            })

    for t in telemetry_events:
        meta = t.payload_json or {}
        res = meta.get("executable_name") or meta.get("application") or meta.get("domain") or meta.get("resource_name") or meta.get("active_app") or t.event_type
        res_str = str(res or "").strip()

        # Skip internal system heartbeats and agent state transitions
        if str(t.event_type).lower() in ("heartbeat", "state_transition", "policy_delivered", "policy_acknowledged", "policy_restored") or res_str.lower() in ("policy_restored", "system"):
            continue

        dev = devices.get(t.device_id)
        user = users.get(dev.user_id) if dev else users.get(t.device_id)
        u_name = (user.full_name or user.email) if user else "Student"
        sap_id = getattr(user, 'roll_number', None) or getattr(user, 'institutional_id', '') or ""

        is_viol = t.event_type in ("application_violation", "process_violation", "dns_block", "dns_blocked", "tamper_alert", "usb_storage_violation") or bool(meta.get("is_violation"))
        sig = (t.session_id, t.device_id, res_str.lower())
        # Deduplicate: if violation already recorded in PolicyViolation table, do not add duplicate row
        if is_viol and sig in seen_viol_signatures:
            continue

        action = meta.get("action_result") or meta.get("action_requested") or meta.get("action")
        details = meta.get("details") or (f"Blocked {res_str}" if is_viol else f"Activity on {res_str}")
        score = meta.get("engagement_score", 30 if is_viol else 85)

        t_key = f"tel-{t.id}"
        if t_key not in seen_ids:
            seen_ids.add(t_key)
            ts = t.occurred_at or t.received_at
            result.append({
                "_id": t_key,
                "id": t.id,
                "type": "VIOLATION" if is_viol else "EVENT",
                "studentId": user.id if user else (dev.user_id if dev else ""),
                "studentName": u_name,
                "sapId": sap_id,
                "sessionId": t.session_id or "",
                "sessionTitle": sessions_map.get(t.session_id, ""),
                "resource": res_str,
                "details": str(details),
                "duration": meta.get("duration", 60),
                "engagementScore": score,
                "isViolation": is_viol,
                "timestamp": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
            })

    for log in audit_logs:
        # Avoid duplicate violation entries from AuditLog since PolicyViolation is the authority
        if log.action in ("VIOLATION", "POLICY_VIOLATION"):
            continue

        user = users.get(log.actor_user_id)
        u_name = (user.full_name or user.email) if user else "Student"
        sap_id = getattr(user, 'institutional_id', None) or getattr(user, 'roll_number', '') or ""
        meta = log.metadata_json or {}

        # Filter out seed dummy rows or internal restored logs
        if meta.get("domain") == "vscode.dev" and u_name == "Test Agent Student":
            continue
        if log.action in ("POLICY_RESTORED", "AGENT_RESTORED") or meta.get("domain") in ("policy_restored", "system"):
            continue

        raw_res = meta.get("domain") or meta.get("resource") or meta.get("executable_name") or meta.get("application") or meta.get("active_app") or meta.get("usb_drive")

        if log.action == "STUDENT_JOINED":
            resource = "Joined Session Room"
            details = f"Student joined session: {sessions_map.get(log.entity_id, 'Active Session')}"
        elif log.action == "STUDENT_LEFT":
            resource = "Left Session Room"
            details = f"Student left session: {sessions_map.get(log.entity_id, 'Active Session')}"
        elif log.action == "SESSION_STATUS_CHANGED":
            status_val = meta.get("status") or meta.get("new_status") or "Updated"
            resource = f"Session Status: {status_val.title()}"
            details = f"Session status changed to {status_val}"
        elif raw_res and raw_res != "Class Workspace":
            resource = raw_res
            details = meta.get("details") or f"Activity: {raw_res}"
        elif log.action == "AGENT_REPORT":
            resource = raw_res or "Active Workspace"
            details = meta.get("details") or f"Student Activity: {resource}"
        else:
            resource = log.action.replace("_", " ").title()
            details = meta.get("details") or f"Session Event: {resource}"

        score = meta.get("engagement_score", 85)

        audit_key = f"audit-{log.id}"
        if audit_key not in seen_ids:
            seen_ids.add(audit_key)
            result.append({
                "_id": audit_key,
                "id": log.id,
                "type": "EVENT",
                "studentId": log.actor_user_id,
                "studentName": meta.get("student_name") or u_name,
                "sapId": meta.get("sap_id") or sap_id,
                "sessionId": log.entity_id,
                "sessionTitle": sessions_map.get(log.entity_id, ""),
                "resource": str(resource),
                "details": str(details),
                "duration": meta.get("duration", 60),
                "engagementScore": score,
                "isViolation": False,
                "timestamp": log.created_at.isoformat() if hasattr(log.created_at, 'isoformat') else str(log.created_at)
            })

    result.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return result[:150]





@router.post("/sessions/join-by-code", response_model=SessionStudentResponse)
def join_session_by_code(
    payload: Dict[str, str],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Join an active or scheduled session using its 6-character session code."""
    raw_code = payload.get("session_code", "").strip().upper()
    if not raw_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session code is required.")

    session_obj = db.query(SessionModel).filter(
        (SessionModel.session_code == raw_code) | (SessionModel.session_code == f"CG-{raw_code}")
    ).first()

    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No session found with this code.")

    # Ensure student is enrolled in the session's batch
    if session_obj.batch_id:
        bm = db.query(BatchMember).filter(
            BatchMember.batch_id == session_obj.batch_id,
            BatchMember.student_id == current_user.id
        ).first()
        if not bm:
            bm = BatchMember(
                batch_id=session_obj.batch_id,
                student_id=current_user.id,
                status="active"
            )
            db.add(bm)
            db.commit()

    # Record participant
    participant = db.query(SessionParticipant).filter(
        SessionParticipant.session_id == session_obj.id,
        SessionParticipant.student_id == current_user.id
    ).first()
    now = datetime.now(timezone.utc)
    if not participant:
        participant = SessionParticipant(
            session_id=session_obj.id,
            student_id=current_user.id,
            status="joined",
            joined_at=now,
            enforcement_activated_at=now
        )
        db.add(participant)
    else:
        participant.status = "joined"
        participant.left_at = None
        participant.joined_at = now
        participant.enforcement_activated_at = now

    # Ensure policy assignment is active for student devices
    devices = db.query(AgentDevice).filter(AgentDevice.user_id == current_user.id, AgentDevice.is_active == True).all()
    if devices:
        for dev in devices:
            assignment = db.query(AgentPolicyAssignment).filter(
                AgentPolicyAssignment.session_id == session_obj.id,
                AgentPolicyAssignment.student_id == current_user.id,
                AgentPolicyAssignment.device_id == dev.id
            ).first()
            if not assignment:
                assignment = AgentPolicyAssignment(
                    session_id=session_obj.id,
                    student_id=current_user.id,
                    device_id=dev.id,
                    state="active",
                    assigned_at=now,
                    activated_at=now,
                    last_heartbeat_at=now
                )
                db.add(assignment)
            else:
                assignment.state = "active"
                assignment.activated_at = now
                assignment.last_heartbeat_at = now
    else:
        assignment = db.query(AgentPolicyAssignment).filter(
            AgentPolicyAssignment.session_id == session_obj.id,
            AgentPolicyAssignment.student_id == current_user.id,
            AgentPolicyAssignment.device_id.is_(None)
        ).first()
        if not assignment:
            assignment = AgentPolicyAssignment(
                session_id=session_obj.id,
                student_id=current_user.id,
                device_id=None,
                state="active",
                assigned_at=now,
                activated_at=now,
                last_heartbeat_at=now
            )
            db.add(assignment)

    presence = db.query(SessionPresence).filter(
        SessionPresence.session_id == session_obj.id,
        SessionPresence.student_id == current_user.id
    ).first()
    if not presence:
        presence = SessionPresence(
            session_id=session_obj.id,
            student_id=current_user.id,
            browser_last_seen_at=now,
            connected_socket_count=1,
            joined_at=now,
            updated_at=now
        )
        db.add(presence)
    else:
        presence.browser_last_seen_at = now
        presence.connected_socket_count = max(1, getattr(presence, 'connected_socket_count', 0) or 1)
        presence.updated_at = now

    db.commit()

    try:
        from ..core.sockets import broadcast_socket_event, calculate_student_presence_dict
        presence_info = calculate_student_presence_dict(presence, "joined", current_user.full_name)
        presence_info["latest_activity"] = "STUDENT_JOINED"
        presence_info["enforcement_status"] = "active"
        broadcast_socket_event("student_joined", presence_info, session_obj.id)
        broadcast_socket_event("policy_available", {"session_id": session_obj.id, "student_id": current_user.id}, session_obj.id)
    except Exception as e:
        pass

    return SessionStudentResponse(
        id=session_obj.id,
        batch_id=session_obj.batch_id,
        batch_name=session_obj.batch.name if session_obj.batch else "Class",
        professor_name=session_obj.creator.full_name if session_obj.creator else "Professor",
        title=session_obj.title,
        description=session_obj.description,
        start_at_utc=session_obj.start_at_utc,
        end_at_utc=session_obj.end_at_utc,
        started_at=session_obj.started_at,
        ended_at=session_obj.ended_at,
        timezone=session_obj.timezone,
        status=session_obj.status,
        is_active=session_obj.is_active,
        is_joined=True,
        session_code=session_obj.session_code,
        rule_set_id=session_obj.rule_set_id,
        policy_version=session_obj.policy_version,
        created_at=session_obj.created_at,
        updated_at=session_obj.updated_at
    )


@router.post("/sessions/{session_id}/unlock-requests", response_model=UnlockRequestResponse, status_code=status.HTTP_201_CREATED)
def create_unlock_request(
    session_id: str,
    req: UnlockRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Student submits a temporary unlock or technical issue assistance request."""
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    unlock_req = UnlockRequest(
        session_id=session_obj.id,
        student_id=current_user.id,
        issue_type=req.issue_type,
        description=req.description.strip(),
        status="pending"
    )
    db.add(unlock_req)
    db.commit()
    db.refresh(unlock_req)

    broadcast_socket_event("unlock_request_created", {
        "id": unlock_req.id,
        "session_id": session_obj.id,
        "student_id": current_user.id,
        "student_name": current_user.full_name,
        "issue_type": unlock_req.issue_type,
        "description": unlock_req.description,
        "created_at": unlock_req.created_at.isoformat()
    })

    return UnlockRequestResponse(
        id=unlock_req.id,
        session_id=unlock_req.session_id,
        student_id=unlock_req.student_id,
        student_name=current_user.full_name,
        issue_type=unlock_req.issue_type,
        description=unlock_req.description,
        status=unlock_req.status,
        created_at=unlock_req.created_at,
        updated_at=unlock_req.updated_at
    )


@router.get("/sessions/{session_id}/unlock-requests", response_model=List[UnlockRequestResponse])
def list_unlock_requests(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all student assistance/unlock requests for a session."""
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    query = db.query(UnlockRequest).filter(UnlockRequest.session_id == session_id)
    if current_user.role == "student":
        query = query.filter(UnlockRequest.student_id == current_user.id)

    requests = query.order_by(desc(UnlockRequest.created_at)).all()
    user_ids = {r.student_id for r in requests}
    users_map = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return [
        UnlockRequestResponse(
            id=r.id,
            session_id=r.session_id,
            student_id=r.student_id,
            student_name=users_map.get(r.student_id, "Student"),
            issue_type=r.issue_type,
            description=r.description,
            status=r.status,
            resolution_notes=r.resolution_notes,
            resolved_by=r.resolved_by,
            created_at=r.created_at,
            updated_at=r.updated_at
        )
        for r in requests
    ]


@router.get("/professor/unlock-requests", response_model=List[UnlockRequestResponse])
def list_professor_unlock_requests(
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """List all student assistance/unlock requests across all sessions for the professor."""
    if current_user.role == "admin":
        session_ids = [s.id for s in db.query(SessionModel).all()]
    else:
        session_ids = [s.id for s in db.query(SessionModel).filter(SessionModel.created_by == current_user.id).all()]

    if not session_ids:
        session_ids = [s.id for s in db.query(SessionModel).filter(SessionModel.is_active == True).all()]

    query = db.query(UnlockRequest)
    if session_ids:
        query = query.filter(UnlockRequest.session_id.in_(session_ids))

    requests = query.order_by(desc(UnlockRequest.created_at)).limit(50).all()

    user_ids = {r.student_id for r in requests}
    users_map = {u.id: (u.full_name or u.email) for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return [
        UnlockRequestResponse(
            id=r.id,
            session_id=r.session_id,
            student_id=r.student_id,
            student_name=users_map.get(r.student_id, "Student"),
            issue_type=r.issue_type,
            description=r.description,
            status=r.status,
            resolution_notes=r.resolution_notes,
            resolved_by=r.resolved_by,
            created_at=r.created_at,
            updated_at=r.updated_at
        )
        for r in requests
    ]


@router.get("/student/unlock-requests", response_model=List[UnlockRequestResponse])
def list_student_unlock_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all unlock/assistance requests submitted by the student."""
    requests = db.query(UnlockRequest).filter(
        UnlockRequest.student_id == current_user.id
    ).order_by(desc(UnlockRequest.created_at)).limit(50).all()

    resolver_ids = {r.resolved_by for r in requests if r.resolved_by}
    resolvers_map = {u.id: (u.full_name or u.email) for u in db.query(User).filter(User.id.in_(resolver_ids)).all()} if resolver_ids else {}

    return [
        UnlockRequestResponse(
            id=r.id,
            session_id=r.session_id,
            student_id=r.student_id,
            student_name=current_user.full_name or "Student",
            issue_type=r.issue_type,
            description=r.description,
            status=r.status,
            resolution_notes=r.resolution_notes or (f"Approved by {resolvers_map.get(r.resolved_by, 'Professor')}" if r.status == "approved" else f"Denied by {resolvers_map.get(r.resolved_by, 'Professor')}" if r.status == "rejected" else None),
            resolved_by=r.resolved_by,
            created_at=r.created_at,
            updated_at=r.updated_at
        )
        for r in requests
    ]


@router.post("/sessions/{session_id}/unlock-requests/{request_id}/resolve", response_model=UnlockRequestResponse)
def resolve_unlock_request(
    session_id: str,
    request_id: str,
    req: UnlockRequestResolve,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Professor or Admin approves/resolves a student unlock or assistance request."""
    unlock_req = db.query(UnlockRequest).filter(
        UnlockRequest.id == request_id,
        UnlockRequest.session_id == session_id
    ).first()

    if not unlock_req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unlock request not found.")

    unlock_req.status = req.status
    unlock_req.resolution_notes = req.resolution_notes
    unlock_req.resolved_by = current_user.id
    unlock_req.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(unlock_req)

    broadcast_socket_event("unlock_request_resolved", {
        "id": unlock_req.id,
        "session_id": session_id,
        "student_id": unlock_req.student_id,
        "status": unlock_req.status,
        "resolution_notes": unlock_req.resolution_notes,
        "resolved_by_name": current_user.full_name or "Professor",
        "description": unlock_req.description,
        "issue_type": unlock_req.issue_type,
        "created_at": unlock_req.created_at.isoformat() if unlock_req.created_at else None,
        "updated_at": unlock_req.updated_at.isoformat() if unlock_req.updated_at else None
    })

    return UnlockRequestResponse(
        id=unlock_req.id,
        session_id=unlock_req.session_id,
        student_id=unlock_req.student_id,
        student_name="Student",
        issue_type=unlock_req.issue_type,
        description=unlock_req.description,
        status=unlock_req.status,
        resolution_notes=unlock_req.resolution_notes,
        resolved_by=unlock_req.resolved_by,
        created_at=unlock_req.created_at,
        updated_at=unlock_req.updated_at
    )

