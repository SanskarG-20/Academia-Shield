"""
Service for Live Student Engagement Telemetry Processing, Feature Aggregation, and Labelling.
Strictly privacy-minimized: aggregates 8 safe telemetry signals into live rolling windows.
Never calculates mock engagement scores or predictions.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models.engagement import (
    EngagementFeatureWindow,
    SessionEngagementLabel,
    EngagementPrediction,
    MLModelVersion,
    EngagementSessionSummary,
    EngagementModelVersion,
)
from ..models.session import SessionModel, SessionParticipant, SessionPresence
from ..models.batch import Batch, BatchMember
from ..models.class_model import ClassModel, ClassMember
from ..models.device import AgentDevice, AgentPolicyAssignment
from ..models.telemetry import PolicyViolation, TelemetryEvent
from ..models.user import User
from ..models.audit_log import AuditLog
from ..ml.features import compute_feature_vector
from ..ml.live_prediction_service import process_live_prediction_for_window
from ..ml.model_registry import get_active_model
from ..ml.predictor import predict_engagement_from_features
from ..schemas.engagement import (
    EngagementFeatureWindowCreate,
    EngagementFeatureWindowResponse,
    LiveEngagementStudentItem,
    LiveEngagementResponse,
    SessionEngagementLabelCreate,
    SessionEngagementLabelResponse,
    EngagementBatchItem,
    EngagementSessionItem,
    StudentEngagementRowItem,
    SessionEngagementDetailResponse,
    PredictionReviewRequest,
    PredictionReviewResponse,
)
from ..core.sockets import broadcast_engagement_features, broadcast_engagement_prediction

logger = logging.getLogger(__name__)


def _audit_rejection(db: Session, actor_id: Optional[str], session_id: str, reason: str, metadata: dict):
    """Log an audit entry for rejected telemetry windows."""
    try:
        audit = AuditLog(
            actor_user_id=actor_id or "system",
            action="REJECT_ENGAGEMENT_WINDOW",
            entity_type="engagement_feature_window",
            entity_id=session_id or "unknown",
            metadata_json={"reason": reason, **metadata}
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to create audit log for rejection: {e}")


def compute_student_engagement(
    db: Session,
    session_id: str,
    student_id: str,
    student_name: str,
    student_email: str,
    batch_id: str
) -> LiveEngagementStudentItem:
    """Compute rolling totals and safe privacy-minimized ratios for a student in a session."""
    # Check if student has joined
    participant = db.query(SessionParticipant).filter(
        SessionParticipant.session_id == session_id,
        SessionParticipant.student_id == student_id,
        SessionParticipant.status == "joined"
    ).first()
    has_joined = participant is not None

    # Query all valid windows for this student in this session
    windows = db.query(EngagementFeatureWindow).filter(
        EngagementFeatureWindow.session_id == session_id,
        EngagementFeatureWindow.student_id == student_id,
        EngagementFeatureWindow.validation_status == "valid"
    ).order_by(EngagementFeatureWindow.window_start_at.asc()).all()

    total_app = sum(getattr(w, "allowed_academic_application_active_seconds", 0.0) or 0.0 for w in windows)
    total_web = sum(getattr(w, "allowed_academic_website_active_seconds", 0.0) or 0.0 for w in windows)
    total_academic = total_app + total_web
    if total_academic == 0.0 and windows:
        total_academic = sum(w.academic_active_seconds for w in windows)

    total_non_academic = sum(w.non_academic_active_seconds for w in windows)
    total_idle = sum(w.idle_seconds for w in windows)
    total_unknown = sum(getattr(w, "unknown_or_unavailable_seconds", 0.0) or 0.0 for w in windows)
    total_switches = sum(w.application_switch_count for w in windows)
    total_unauthorized = sum(w.unauthorized_application_attempt_count for w in windows)
    total_blocked = sum(w.blocked_website_attempt_count for w in windows)
    total_violations = sum(w.policy_violation_count for w in windows)
    window_count = len(windows)
    last_window_at = windows[-1].window_end_at if windows else None

    # Merge breakdown summaries
    apps_summary: dict = {}
    websites_summary: dict = {}
    for w in windows:
        bd = getattr(w, "approved_resources_breakdown", None) or {}
        if isinstance(bd, dict):
            for a_name, a_sec in bd.get("applications", {}).items():
                apps_summary[a_name] = round(apps_summary.get(a_name, 0.0) + float(a_sec), 2)
            for w_name, w_sec in bd.get("websites", {}).items():
                websites_summary[w_name] = round(websites_summary.get(w_name, 0.0) + float(w_sec), 2)

    # Safe derived ratios
    total_active_seconds = total_academic + total_non_academic + total_unknown
    if total_active_seconds > 0:
        academic_ratio = round(total_academic / max(total_active_seconds, 1.0), 3)
        app_ratio = round(total_app / max(total_active_seconds, 1.0), 3)
        web_ratio = round(total_web / max(total_active_seconds, 1.0), 3)
    else:
        academic_ratio = 0.0
        app_ratio = 0.0
        web_ratio = 0.0

    total_time = total_active_seconds + total_idle
    idle_ratio = round(total_idle / max(total_time, 1.0), 3) if total_time > 0 else 0.0

    total_active_minutes = max(total_active_seconds / 60.0, 1.0)
    focus_stability_index = round(1.0 / (1.0 + (total_switches / total_active_minutes)), 3)

    last_elapsed = windows[-1].session_elapsed_seconds if windows else 0.0
    violation_rate_per_hour = round((total_violations / max(last_elapsed, 60.0)) * 3600.0, 2)
    last_completeness = getattr(windows[-1], "feature_completeness_percent", 100.0) if windows else 100.0

    # Check professor post-session label
    label_rec = db.query(SessionEngagementLabel).filter(
        SessionEngagementLabel.session_id == session_id,
        SessionEngagementLabel.student_id == student_id
    ).first()
    label_val = label_rec.label if label_rec else None

    # Fetch latest prediction for this student in this session (if any)
    latest_pred = db.query(EngagementPrediction).filter(
        EngagementPrediction.session_id == session_id,
        EngagementPrediction.student_id == student_id
    ).order_by(EngagementPrediction.generated_at.desc()).first()

    pred_avail = False
    pred_reason = None
    pred_engagement = None
    confidence = None
    prob_high = None
    prob_med = None
    prob_low = None
    model_ver = None
    pred_type = None
    rev_status = None
    pred_id = None
    override_label = None

    if latest_pred:
        pred_avail = True
        pred_engagement = latest_pred.prediction
        confidence = latest_pred.confidence
        prob_high = latest_pred.probability_high
        prob_med = latest_pred.probability_medium
        prob_low = latest_pred.probability_low
        pred_type = latest_pred.prediction_type
        rev_status = latest_pred.review_status
        pred_id = latest_pred.id
        override_label = latest_pred.professor_override_label
        if latest_pred.model_version_id:
            m_rec = db.get(MLModelVersion, latest_pred.model_version_id)
            model_ver = m_rec.version_tag if m_rec else latest_pred.model_version_id
    else:
        # Check active model and 5m guard reason
        active_model = get_active_model(db)
        if not active_model:
            pred_reason = "No approved ML model is currently active"
        elif last_elapsed < 300.0 or window_count < 1:
            pred_reason = "Collecting live activity data"
        else:
            pred_reason = "Processing incoming telemetry"

    return LiveEngagementStudentItem(
        student_id=student_id,
        student_name=student_name,
        student_email=student_email,
        batch_id=batch_id,
        joined=has_joined,
        last_window_at=last_window_at,
        window_count=window_count,
        allowed_academic_application_active_seconds=round(total_app, 1),
        allowed_academic_website_active_seconds=round(total_web, 1),
        unknown_or_unavailable_seconds=round(total_unknown, 1),
        total_academic_seconds=round(total_academic, 1),
        total_non_academic_seconds=round(total_non_academic, 1),
        total_idle_seconds=round(total_idle, 1),
        total_switches=total_switches,
        total_unauthorized_attempts=total_unauthorized,
        total_blocked_website_attempts=total_blocked,
        total_policy_violations=total_violations,
        academic_ratio=academic_ratio,
        allowed_app_ratio=app_ratio,
        allowed_website_ratio=web_ratio,
        idle_ratio=idle_ratio,
        focus_stability_index=focus_stability_index,
        violation_rate_per_hour=violation_rate_per_hour,
        feature_completeness_percent=last_completeness or 100.0,
        approved_apps_summary=apps_summary,
        approved_websites_summary=websites_summary,
        label=label_val,
        prediction_available=pred_avail,
        prediction_reason=pred_reason,
        predicted_engagement=pred_engagement,
        confidence=confidence,
        probability_high=prob_high,
        probability_medium=prob_med,
        probability_low=prob_low,
        model_version=model_ver,
        prediction_type=pred_type,
        review_status=rev_status,
        latest_prediction_id=pred_id,
        professor_override_label=override_label
    )


class EngagementService:

    @staticmethod
    def record_engagement_window(
        db: Session,
        window_data: EngagementFeatureWindowCreate,
        current_user: User
    ) -> EngagementFeatureWindowResponse:
        """
        Validate and ingest a privacy-minimized 5-minute engagement feature window from the Local Agent.
        Strictly enforces device ownership, session activity, batch enrollment, and joins.
        """
        # 1. Idempotency Check
        existing = db.query(EngagementFeatureWindow).filter(
            EngagementFeatureWindow.event_id == window_data.event_id
        ).first()
        if existing:
            return EngagementFeatureWindowResponse(
                id=existing.id,
                event_id=window_data.event_id,
                status="duplicate",
                message="Feature window already processed"
            )

        # 2. Device Check
        device = db.query(AgentDevice).filter(
            (AgentDevice.id == window_data.device_id) | (AgentDevice.device_identifier == window_data.device_id)
        ).first()

        if not device or device.user_id != window_data.student_id:
            _audit_rejection(
                db, current_user.id, window_data.session_id,
                "Device does not belong to student",
                {"device_id": window_data.device_id, "student_id": window_data.student_id}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device does not belong to the student"
            )

        # 3. Caller Identity Verification
        if current_user.id != window_data.student_id and current_user.role not in ("admin", "professor"):
            _audit_rejection(
                db, current_user.id, window_data.session_id,
                "Student identity mismatch with authenticated token",
                {"token_user": current_user.id, "student_id": window_data.student_id}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student identity mismatch"
            )

        # 4. Session Existence & State
        session = db.query(SessionModel).filter(SessionModel.id == window_data.session_id).first()
        if not session:
            _audit_rejection(
                db, current_user.id, window_data.session_id,
                "Session not found",
                {"session_id": window_data.session_id}
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )

        if session.status.lower() != "active" or not session.is_active:
            _audit_rejection(
                db, current_user.id, window_data.session_id,
                f"Session is not active (status={session.status}, is_active={session.is_active})",
                {"status": session.status, "is_active": session.is_active}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session is not currently active or has ended"
            )

        # 5. Batch Match
        if session.batch_id != window_data.batch_id:
            _audit_rejection(
                db, current_user.id, window_data.session_id,
                "Batch ID mismatch with session batch",
                {"session_batch_id": session.batch_id, "provided_batch_id": window_data.batch_id}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch ID does not match session batch"
            )

        # 6. Student assigned to Batch
        batch_member = db.query(BatchMember).filter(
            BatchMember.batch_id == window_data.batch_id,
            BatchMember.student_id == window_data.student_id,
            BatchMember.status == "active"
        ).first()
        if not batch_member:
            _audit_rejection(
                db, current_user.id, window_data.session_id,
                "Student is not assigned to this session batch",
                {"batch_id": window_data.batch_id, "student_id": window_data.student_id}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student is not assigned to the session batch"
            )

        # 7. Student joined session at least once
        participant = db.query(SessionParticipant).filter(
            SessionParticipant.session_id == window_data.session_id,
            SessionParticipant.student_id == window_data.student_id
        ).first()
        if not participant:
            _audit_rejection(
                db, current_user.id, window_data.session_id,
                "Student has not joined this session at least once",
                {"session_id": window_data.session_id, "student_id": window_data.student_id}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student has not joined this session at least once"
            )

        # 8. Bounds and sanity validation
        window_duration = (window_data.window_end_at - window_data.window_start_at).total_seconds()
        if window_duration <= 0:
            _audit_rejection(
                db, current_user.id, window_data.session_id,
                "Invalid window duration <= 0",
                {"duration": window_duration}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Window duration must be strictly positive"
            )

        acad_app = getattr(window_data, "allowed_academic_application_active_seconds", 0.0) or 0.0
        acad_web = getattr(window_data, "allowed_academic_website_active_seconds", 0.0) or 0.0
        acad_total = getattr(window_data, "academic_active_seconds", 0.0) or 0.0
        if acad_app > 0.0 or acad_web > 0.0:
            acad_total = acad_app + acad_web
        elif acad_total > 0.0 and acad_app == 0.0 and acad_web == 0.0:
            acad_app = acad_total

        unknown_sec = getattr(window_data, "unknown_or_unavailable_seconds", 0.0) or 0.0

        total_durations = (
            acad_total +
            window_data.non_academic_active_seconds +
            window_data.idle_seconds +
            unknown_sec
        )

        validation_status = "valid"
        validation_error = None

        if any(x < 0 for x in [
            acad_app,
            acad_web,
            acad_total,
            window_data.non_academic_active_seconds,
            window_data.idle_seconds,
            unknown_sec,
            window_data.session_elapsed_seconds
        ]):
            validation_status = "invalid"
            validation_error = "Metrics contain negative values"
        elif total_durations > (window_duration + 5.0):
            validation_status = "invalid"
            validation_error = f"Total duration ({total_durations}s) exceeds window duration ({window_duration}s)"

        # Persist window
        window_record = EngagementFeatureWindow(
            event_id=window_data.event_id,
            student_id=window_data.student_id,
            device_id=device.id,
            batch_id=window_data.batch_id,
            session_id=window_data.session_id,
            window_start_at=window_data.window_start_at,
            window_end_at=window_data.window_end_at,
            policy_version=window_data.policy_version,
            allowed_academic_application_active_seconds=acad_app,
            allowed_academic_website_active_seconds=acad_web,
            academic_active_seconds=acad_total,
            non_academic_active_seconds=window_data.non_academic_active_seconds,
            idle_seconds=window_data.idle_seconds,
            unknown_or_unavailable_seconds=unknown_sec,
            active_resource_sample_count=getattr(window_data, "active_resource_sample_count", 0) or 0,
            unknown_resource_sample_count=getattr(window_data, "unknown_resource_sample_count", 0) or 0,
            feature_completeness_percent=getattr(window_data, "feature_completeness_percent", 100.0) or 100.0,
            approved_resources_breakdown=getattr(window_data, "approved_resources_breakdown", None),
            application_switch_count=window_data.application_switch_count,
            unauthorized_application_attempt_count=window_data.unauthorized_application_attempt_count,
            blocked_website_attempt_count=window_data.blocked_website_attempt_count,
            policy_violation_count=window_data.policy_violation_count,
            session_elapsed_seconds=window_data.session_elapsed_seconds,
            validation_status=validation_status,
            validation_error=validation_error
        )
        db.add(window_record)
        db.commit()
        db.refresh(window_record)

        # Audit events when the device cannot report activity reliably
        completeness = getattr(window_data, "feature_completeness_percent", 100.0) or 100.0
        if completeness < 80.0 or (window_duration > 10.0 and unknown_sec / window_duration > 0.2):
            try:
                audit = AuditLog(
                    actor_user_id=current_user.id,
                    action="DEVICE_ACTIVITY_REPORT_UNRELIABLE",
                    entity_type="device",
                    entity_id=device.id,
                    metadata_json={
                        "student_id": window_data.student_id,
                        "session_id": window_data.session_id,
                        "feature_completeness_percent": completeness,
                        "unknown_or_unavailable_seconds": unknown_sec,
                        "window_duration": window_duration,
                        "reason": "Device telemetry contains high unknown or unavailable activity (< 80% completeness)"
                    }
                )
                db.add(audit)
                db.commit()
            except Exception as e:
                logger.warning(f"Failed to record unreliable activity audit: {e}")

        if validation_status == "invalid":
            return EngagementFeatureWindowResponse(
                id=window_record.id,
                event_id=window_data.event_id,
                status="invalid",
                message=validation_error
            )

        # Execute ML live prediction pipeline (if valid)
        try:
            process_live_prediction_for_window(db=db, window=window_record, session=session)
        except Exception as e:
            logger.error(f"Failed to process live prediction for window {window_record.id}: {e}")

        # Broadcast real-time aggregate update exclusively to owning professor
        student_user = db.query(User).filter(User.id == window_data.student_id).first()
        student_name = student_user.full_name if student_user else "Student"
        student_email = student_user.email if student_user else ""

        try:
            live_student = compute_student_engagement(
                db=db,
                session_id=session.id,
                student_id=student_user.id,
                student_name=student_name,
                student_email=student_email,
                batch_id=session.batch_id
            )
            broadcast_payload = {
                "session_id": session.id,
                "student": live_student.model_dump() if hasattr(live_student, "model_dump") else live_student.dict(),
                "prediction_available": live_student.prediction_available,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            broadcast_engagement_features(broadcast_payload, professor_id=session.created_by)
        except Exception as e:
            logger.warning(f"Failed to broadcast engagement feature update to professor: {e}")

        return EngagementFeatureWindowResponse(
            id=window_record.id,
            event_id=window_data.event_id,
            status="accepted",
            message="Feature window successfully recorded"
        )

    @staticmethod
    def get_live_session_engagement(
        db: Session,
        session_id: str,
        current_user: User
    ) -> LiveEngagementResponse:
        """
        Fetch privacy-minimized live engagement aggregation for all students in a session.
        Authorized only for session creator professor or admin.
        prediction_available is strictly False.
        """
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        # Professor authorization
        if current_user.role != "admin" and session.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view engagement features for this session"
            )

        # Get all students in the batch
        batch_members = db.query(BatchMember, User).join(
            User, BatchMember.student_id == User.id
        ).filter(
            BatchMember.batch_id == session.batch_id,
            BatchMember.status == "active"
        ).all()

        students: List[LiveEngagementStudentItem] = []
        for bm, user in batch_members:
            item = compute_student_engagement(
                db=db,
                session_id=session.id,
                student_id=user.id,
                student_name=user.full_name,
                student_email=user.email,
                batch_id=session.batch_id
            )
            students.append(item)

        has_pred = any(s.prediction_available for s in students)
        return LiveEngagementResponse(
            session_id=session.id,
            session_title=session.title,
            session_status=session.status,
            is_active=session.is_active,
            prediction_available=has_pred,
            students=students
        )

    @staticmethod
    def get_session_prediction_history(
        db: Session,
        session_id: str,
        current_user: User
    ) -> List[EngagementPrediction]:
        """Fetch all historical engagement predictions generated for a session."""
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        if current_user.role != "admin" and session.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view predictions for this session"
            )

        return (
            db.query(EngagementPrediction)
            .filter(EngagementPrediction.session_id == session_id)
            .order_by(EngagementPrediction.generated_at.desc())
            .all()
        )

    @staticmethod
    def review_prediction(
        db: Session,
        prediction_id: str,
        override_label: Optional[str],
        current_user: User
    ) -> EngagementPrediction:
        """Allow professor to review and optionally override an advisory engagement prediction."""
        pred = db.get(EngagementPrediction, prediction_id)
        if not pred:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")

        session = db.get(SessionModel, pred.session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated session not found")

        if current_user.role != "admin" and session.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to review predictions for this session"
            )

        now = datetime.now(timezone.utc)
        pred.review_status = "reviewed"
        pred.reviewed_by = current_user.id
        pred.reviewed_at = now
        if override_label:
            pred.professor_override_label = override_label

        db.commit()
        db.refresh(pred)
        return pred

    @staticmethod
    def create_or_update_session_label(
        db: Session,
        session_id: str,
        label_data: SessionEngagementLabelCreate,
        current_user: User
    ) -> SessionEngagementLabelResponse:
        """
        Record professor post-session human label (High, Medium, Low).
        Strictly allowed ONLY for completed (ended or inactive) sessions.
        """
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        if current_user.role != "admin" and session.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the professor who conducted this session can provide engagement labels"
            )

        # Must be completed session
        if session.is_active or session.status.lower() not in ("ended", "cancelled", "completed"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Engagement labelling is only allowed for completed sessions. Active sessions cannot be labelled."
            )

        # Verify student exists in batch or session
        student = db.query(User).filter(User.id == label_data.student_id).first()
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

        existing_label = db.query(SessionEngagementLabel).filter(
            SessionEngagementLabel.session_id == session_id,
            SessionEngagementLabel.student_id == label_data.student_id
        ).first()

        now = datetime.now(timezone.utc)
        if existing_label:
            existing_label.label = label_data.label
            existing_label.notes = label_data.notes
            existing_label.updated_at = now
            db.commit()
            db.refresh(existing_label)
            return existing_label
        else:
            new_label = SessionEngagementLabel(
                session_id=session_id,
                student_id=label_data.student_id,
                professor_id=current_user.id,
                label=label_data.label,
                notes=label_data.notes,
                created_at=now,
                updated_at=now
            )
            db.add(new_label)
            db.commit()
            db.refresh(new_label)
            return new_label

    @staticmethod
    def get_session_labels(
        db: Session,
        session_id: str,
        current_user: User
    ) -> List[SessionEngagementLabelResponse]:
        """Fetch all professor engagement labels for a session."""
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        if current_user.role != "admin" and session.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view labels for this session"
            )

        return db.query(SessionEngagementLabel).filter(
            SessionEngagementLabel.session_id == session_id
        ).all()

    @staticmethod
    def get_professor_batches(db: Session, current_user: User) -> List[EngagementBatchItem]:
        """Fetch all batches owned by the logged-in professor or all batches if administrator."""
        if current_user.role == "admin":
            batches = db.query(Batch).order_by(Batch.created_at.desc()).all()
        else:
            batches = (
                db.query(Batch)
                .filter(Batch.professor_id == current_user.id)
                .order_by(Batch.created_at.desc())
                .all()
            )

        items: List[EngagementBatchItem] = []
        for b in batches:
            active_students = (
                db.query(BatchMember)
                .filter(BatchMember.batch_id == b.id, BatchMember.status == "active")
                .count()
            )
            items.append(
                EngagementBatchItem(
                    id=b.id,
                    name=b.name,
                    code=b.batch_code,
                    description=b.description,
                    student_count=active_students,
                    created_at=b.created_at,
                )
            )
        return items

    @staticmethod
    def get_batch_sessions(
        db: Session,
        batch_id: str,
        status_filter: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        current_user: User,
    ) -> List[EngagementSessionItem]:
        """Fetch sessions for a batch with strict ownership verification and optional filters."""
        batch = db.get(Batch, batch_id)
        if not batch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        if (
            current_user.role != "admin"
            and batch.professor_id != current_user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this batch's sessions.",
            )

        query = db.query(SessionModel).filter(SessionModel.batch_id == batch_id)

        if status_filter and status_filter.lower() != "all":
            sf = status_filter.lower()
            if sf == "active":
                query = query.filter(
                    (SessionModel.is_active == True) | (SessionModel.status.ilike("active"))
                )
            elif sf == "completed":
                query = query.filter(
                    (SessionModel.is_active == False)
                    | (SessionModel.status.in_(["ended", "completed", "cancelled"]))
                )

        if start_date:
            try:
                sd = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                query = query.filter(SessionModel.created_at >= sd)
            except Exception:
                pass

        if end_date:
            try:
                ed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                query = query.filter(SessionModel.created_at <= ed)
            except Exception:
                pass

        sessions = query.order_by(SessionModel.created_at.desc()).all()

        items: List[EngagementSessionItem] = []
        for s in sessions:
            p_count = (
                db.query(SessionParticipant)
                .filter(SessionParticipant.session_id == s.id)
                .count()
            )
            items.append(
                EngagementSessionItem(
                    id=s.id,
                    batch_id=s.batch_id,
                    title=s.title,
                    status=s.status,
                    is_active=s.is_active,
                    start_time=s.started_at or s.start_at_utc or s.start_at,
                    end_time=s.ended_at or s.end_at_utc or s.end_at,
                    created_at=s.created_at,
                    participant_count=p_count,
                )
            )
        return items

    @staticmethod
    def get_session_engagement_detail(
        db: Session,
        session_id: str,
        current_user: User,
    ) -> SessionEngagementDetailResponse:
        """Fetch student engagement details for a session (live telemetry or saved final metrics)."""
        session = db.get(SessionModel, session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        batch = db.get(Batch, session.batch_id) if session.batch_id else None
        is_owner = (session.created_by == current_user.id) or (
            batch and batch.professor_id == current_user.id
        )
        if current_user.role != "admin" and not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this session",
            )

        active_model = get_active_model(db)
        is_live = bool(session.is_active and session.status.lower() == "active")

        # Discover students who joined the session or are enrolled in the session's batch/class
        participants = (
            db.query(SessionParticipant)
            .filter(SessionParticipant.session_id == session_id)
            .all()
        )
        presences = (
            db.query(SessionPresence)
            .filter(SessionPresence.session_id == session_id)
            .all()
        )
        summaries = (
            db.query(EngagementSessionSummary)
            .filter(EngagementSessionSummary.session_id == session_id)
            .all()
        )
        window_students = (
            db.query(EngagementFeatureWindow.student_id)
            .filter(
                EngagementFeatureWindow.session_id == session_id,
                EngagementFeatureWindow.validation_status == "valid",
            )
            .distinct()
            .all()
        )
        assignments = (
            db.query(AgentPolicyAssignment.student_id)
            .filter(AgentPolicyAssignment.session_id == session_id)
            .all()
        )
        batch_students = []
        if session.batch_id:
            batch_students = (
                db.query(BatchMember.student_id)
                .filter(
                    BatchMember.batch_id == session.batch_id,
                    BatchMember.status == "active",
                )
                .all()
            )
        class_students = []
        if session.class_id:
            class_students = (
                db.query(ClassMember.student_id)
                .filter(ClassMember.class_id == session.class_id)
                .all()
            )

        joined_student_ids = set()
        for p in participants:
            if p.student_id:
                joined_student_ids.add(p.student_id)
        for pr in presences:
            if pr.student_id:
                joined_student_ids.add(pr.student_id)
        for sm in summaries:
            if sm.student_id:
                joined_student_ids.add(sm.student_id)
        for ws in window_students:
            if ws[0]:
                joined_student_ids.add(ws[0])
        for pa in assignments:
            if pa[0]:
                joined_student_ids.add(pa[0])
        for bs in batch_students:
            if bs[0]:
                joined_student_ids.add(bs[0])
        for cs in class_students:
            if cs[0]:
                joined_student_ids.add(cs[0])

        if not joined_student_ids:
            return SessionEngagementDetailResponse(
                session_id=session.id,
                session_title=session.title,
                batch_id=session.batch_id,
                batch_name=batch.name if batch else "Unknown Batch",
                session_status=session.status,
                is_active=is_live,
                has_active_model=bool(active_model),
                model_version_tag=active_model.version_tag if active_model else None,
                students=[],
                empty_reason="No students enrolled or joined in this session.",
            )

        p_map = {p.student_id: p for p in participants if p.student_id}
        pr_map = {pr.student_id: pr for pr in presences if pr.student_id}
        sm_map = {sm.student_id: sm for sm in summaries if sm.student_id}

        students_list: List[StudentEngagementRowItem] = []
        now = datetime.now(timezone.utc)

        for s_id in sorted(joined_student_ids):
            student_user = db.get(User, s_id)
            if not student_user:
                continue

            # Ensure only real students are processed - ignore synthetic/test accounts
            name_lower = (student_user.full_name or "").lower()
            email_lower = (student_user.email or "").lower()
            if "test agent" in name_lower or "test student" in name_lower or "student_test" in email_lower:
                continue

            student_name = student_user.full_name or "Student"
            student_email = student_user.email or ""

            p = p_map.get(s_id)
            pr = pr_map.get(s_id)
            sm = sm_map.get(s_id)
            has_joined = bool(p or pr or sm)

            # In ended sessions, only show students who actually attended / joined
            if not is_live and not has_joined:
                continue

            stud_devs = [d[0] for d in db.query(AgentDevice.id).filter(AgentDevice.user_id == s_id).all()]
            assigned_devs = [a[0] for a in db.query(AgentPolicyAssignment.device_id).filter(
                AgentPolicyAssignment.student_id == s_id,
                AgentPolicyAssignment.device_id.isnot(None)
            ).all()]
            for ad in assigned_devs:
                if ad and ad not in stud_devs:
                    stud_devs.append(ad)
            stud_dev_id = stud_devs[0] if stud_devs else None

            # Calculate genuine live policy violation counts for student
            live_violations = 0
            live_unauth = 0
            live_blocked = 0
            if stud_devs:
                live_violations = db.query(PolicyViolation).filter(
                    PolicyViolation.session_id == session_id,
                    PolicyViolation.device_id.in_(stud_devs)
                ).count()
                live_unauth = db.query(PolicyViolation).filter(
                    PolicyViolation.session_id == session_id,
                    PolicyViolation.device_id.in_(stud_devs),
                    PolicyViolation.violation_type == "process"
                ).count()
                live_blocked = db.query(PolicyViolation).filter(
                    PolicyViolation.session_id == session_id,
                    PolicyViolation.device_id.in_(stud_devs),
                    PolicyViolation.violation_type.in_(["web", "dns"])
                ).count()

            # Determine session presence status: Joined, Left, Offline, Not Joined
            if not is_live:
                if p and p.status and p.status.lower() == "left":
                    sess_status = "Left"
                elif has_joined:
                    sess_status = "Offline"
                else:
                    sess_status = "Not Joined"
            else:
                if p and p.status and p.status.lower() == "left":
                    sess_status = "Left"
                elif pr and pr.connected_socket_count > 0:
                    sess_status = "Joined"
                elif pr and pr.browser_last_seen_at:
                    seen = pr.browser_last_seen_at
                    if seen.tzinfo is None:
                        seen = seen.replace(tzinfo=timezone.utc)
                    if (now - seen).total_seconds() < 120:
                        sess_status = "Joined"
                    else:
                        sess_status = "Offline"
                elif p and p.status and p.status.lower() == "joined":
                    sess_status = "Joined"
                elif has_joined:
                    sess_status = "Offline"
                else:
                    sess_status = "Not Joined"

            # Determine policy enforcement status: Active, Restored, Failed, Inactive
            if not has_joined:
                pol_status = "Inactive"
            elif p and p.enforcement_stop_reason in ("failed", "error"):
                pol_status = "Failed"
            elif p and p.enforcement_stop_reason in ("restored", "resumed"):
                pol_status = "Restored"
            elif not is_live:
                pol_status = "Restored"
            elif p and p.enforcement_activated_at:
                pol_status = "Active"
            else:
                pol_status = "Active"

            if not is_live:
                # Completed session: load permanently saved data
                windows = []
                apps_summary = {}
                websites_summary = {}
                completeness = 100.0
                if sm:
                    app_sec = getattr(sm, "allowed_academic_application_active_seconds", 0.0) or 0.0
                    web_sec = getattr(sm, "allowed_academic_website_active_seconds", 0.0) or 0.0
                    acad_sec = getattr(sm, "allowed_academic_active_seconds", 0.0) or (app_sec + web_sec)
                    if acad_sec == 0.0:
                        acad_sec = sm.academic_active_seconds
                        app_sec = acad_sec
                    non_acad_sec = sm.non_academic_active_seconds
                    idle_sec = sm.idle_seconds
                    unknown_sec = getattr(sm, "unknown_or_unavailable_seconds", 0.0) or 0.0
                    switches = sm.application_switch_count
                    unauth = sm.unauthorized_application_attempt_count
                    blocked = sm.blocked_website_attempt_count
                    violations = sm.policy_violation_count
                    apps_summary = getattr(sm, "approved_apps_summary", {}) or {}
                    websites_summary = getattr(sm, "approved_websites_summary", {}) or {}
                    completeness = getattr(sm, "data_completeness_percent", 100.0) or 100.0
                    last_updated = sm.updated_at
                    final_pred_id = sm.final_prediction_id
                else:
                    windows = (
                        db.query(EngagementFeatureWindow)
                        .filter(
                            EngagementFeatureWindow.session_id == session_id,
                            EngagementFeatureWindow.student_id == s_id,
                            EngagementFeatureWindow.validation_status == "valid",
                        )
                        .all()
                    )
                    if windows:
                        app_sec = sum(getattr(w, "allowed_academic_application_active_seconds", 0.0) or 0.0 for w in windows)
                        web_sec = sum(getattr(w, "allowed_academic_website_active_seconds", 0.0) or 0.0 for w in windows)
                        acad_sec = app_sec + web_sec
                        if acad_sec == 0.0:
                            acad_sec = sum(w.academic_active_seconds for w in windows)
                            app_sec = acad_sec
                        non_acad_sec = sum(w.non_academic_active_seconds for w in windows)
                        idle_sec = sum(w.idle_seconds for w in windows)
                        unknown_sec = sum(getattr(w, "unknown_or_unavailable_seconds", 0.0) or 0.0 for w in windows)
                        switches = sum(w.application_switch_count for w in windows)
                        unauth = max(sum(w.unauthorized_application_attempt_count for w in windows), live_unauth)
                        blocked = max(sum(w.blocked_website_attempt_count for w in windows), live_blocked)
                        violations = max(sum(w.policy_violation_count for w in windows), live_violations)
                        last_updated = windows[-1].window_end_at
                        completeness = getattr(windows[-1], "feature_completeness_percent", 100.0) or 100.0
                        for w in windows:
                            bd = getattr(w, "approved_resources_breakdown", None) or {}
                            if isinstance(bd, dict):
                                for a_name, a_s in bd.get("applications", {}).items():
                                    apps_summary[a_name] = round(apps_summary.get(a_name, 0.0) + float(a_s), 2)
                                for w_name, w_s in bd.get("websites", {}).items():
                                    websites_summary[w_name] = round(websites_summary.get(w_name, 0.0) + float(w_s), 2)
                    elif p and p.joined_at:
                        end_t = p.left_at or session.ended_at or session.end_at_utc or p.joined_at
                        dur = max(0.0, (end_t - p.joined_at).total_seconds())
                        violations = live_violations
                        unauth = live_unauth
                        blocked = live_blocked
                        switches = 0
                        non_acad_sec = float(min(dur, violations * 10.0))
                        acad_sec = float(max(0.0, dur - non_acad_sec))
                        app_sec = acad_sec
                        web_sec = 0.0
                        idle_sec = 0.0
                        unknown_sec = 0.0
                        last_updated = end_t
                    else:
                        app_sec = 0.0
                        web_sec = 0.0
                        acad_sec = 0.0
                        non_acad_sec = 0.0
                        idle_sec = 0.0
                        unknown_sec = 0.0
                        switches = 0
                        unauth = 0
                        blocked = 0
                        violations = 0
                        last_updated = session.ended_at or session.end_at_utc or session.created_at
                    final_pred_id = None

                # Find final or latest prediction
                pred = None
                if final_pred_id:
                    pred = db.get(EngagementPrediction, final_pred_id)
                if not pred:
                    pred = (
                        db.query(EngagementPrediction)
                        .filter(
                            EngagementPrediction.session_id == session_id,
                            EngagementPrediction.student_id == s_id,
                        )
                        .order_by(EngagementPrediction.generated_at.desc())
                        .first()
                    )

                # If no prediction recorded yet, but active model exists and student attended/joined, evaluate on-the-fly
                if not pred and active_model and has_joined:
                    tot_elapsed = max(acad_sec + non_acad_sec + idle_sec + unknown_sec, 60.0)
                    raw_dict = {
                        "allowed_academic_application_active_seconds": app_sec,
                        "allowed_academic_website_active_seconds": web_sec,
                        "academic_active_seconds": acad_sec,
                        "non_academic_active_seconds": non_acad_sec,
                        "idle_seconds": idle_sec,
                        "unknown_or_unavailable_seconds": unknown_sec,
                        "application_switch_count": switches,
                        "unauthorized_application_attempt_count": unauth,
                        "blocked_website_attempt_count": blocked,
                        "policy_violation_count": violations,
                        "session_elapsed_seconds": tot_elapsed,
                    }
                    features = compute_feature_vector(raw_dict)
                    inference = predict_engagement_from_features(db, features)
                    if inference.get("prediction_available"):
                        now_utc = datetime.now(timezone.utc)
                        pred = EngagementPrediction(
                            model_version_id=active_model.id,
                            student_id=s_id,
                            device_id=stud_dev_id,
                            batch_id=session.batch_id,
                            session_id=session_id,
                            prediction=inference["prediction"],
                            confidence=inference["confidence"],
                            probability_high=inference["probability_high"],
                            probability_medium=inference["probability_medium"],
                            probability_low=inference["probability_low"],
                            feature_snapshot_json=features,
                            prediction_type="final",
                            review_status="pending",
                            generated_at=now_utc,
                        )
                        db.add(pred)
                        db.commit()
                        db.refresh(pred)

                if pred:
                    m_tag = None
                    if pred.model_version_id:
                        m_rec = db.get(MLModelVersion, pred.model_version_id)
                        m_tag = m_rec.version_tag if m_rec else pred.model_version_id

                    students_list.append(
                        StudentEngagementRowItem(
                            student_name=student_name,
                            student_id=s_id,
                            student_email=student_email,
                            session_status=sess_status,
                            policy_status=pol_status,
                            allowed_academic_application_active_seconds=round(app_sec, 1),
                            allowed_academic_website_active_seconds=round(web_sec, 1),
                            allowed_academic_active_seconds=round(acad_sec, 1),
                            academic_activity_seconds=round(acad_sec, 1),
                            non_academic_activity_seconds=round(non_acad_sec, 1),
                            idle_seconds=round(idle_sec, 1),
                            unknown_or_unavailable_seconds=round(unknown_sec, 1),
                            feature_completeness_percent=completeness,
                            approved_apps_summary=apps_summary or None,
                            approved_websites_summary=websites_summary or None,
                            application_switch_count=switches,
                            blocked_website_attempt_count=blocked,
                            unauthorized_application_attempt_count=unauth,
                            policy_violation_count=violations,
                            engagement_estimate=pred.prediction,
                            confidence=pred.confidence,
                            probability_high=pred.probability_high,
                            probability_medium=pred.probability_medium,
                            probability_low=pred.probability_low,
                            collection_status="final_prediction",
                            valid_windows_received=len(windows) if windows else 1,
                            minimum_windows_required=1,
                            session_elapsed_seconds=round(acad_sec + non_acad_sec + idle_sec + unknown_sec, 1),
                            last_telemetry_at=last_updated,
                            prediction_type="Final" if pred.prediction_type == "final" else "Live Preliminary",
                            prediction_available=True,
                            prediction_reason=None,
                            last_updated_time=pred.generated_at or last_updated,
                            professor_review_status=pred.review_status,
                            professor_override_label=pred.professor_override_label,
                            prediction_id=pred.id,
                            model_version=m_tag,
                            is_advisory=True,
                            review_required=True,
                        )
                    )
                else:
                    reason = (
                        "Student did not attend this session"
                        if not has_joined
                        else "Historical session has no recorded prediction"
                    )
                    students_list.append(
                        StudentEngagementRowItem(
                            student_name=student_name,
                            student_id=s_id,
                            student_email=student_email,
                            session_status=sess_status,
                            policy_status=pol_status,
                            allowed_academic_application_active_seconds=round(app_sec, 1),
                            allowed_academic_website_active_seconds=round(web_sec, 1),
                            allowed_academic_active_seconds=round(acad_sec, 1),
                            academic_activity_seconds=round(acad_sec, 1),
                            non_academic_activity_seconds=round(non_acad_sec, 1),
                            idle_seconds=round(idle_sec, 1),
                            unknown_or_unavailable_seconds=round(unknown_sec, 1),
                            feature_completeness_percent=completeness,
                            approved_apps_summary=apps_summary or None,
                            approved_websites_summary=websites_summary or None,
                            application_switch_count=switches,
                            blocked_website_attempt_count=blocked,
                            unauthorized_application_attempt_count=unauth,
                            policy_violation_count=violations,
                            engagement_estimate=None,
                            confidence=None,
                            probability_high=None,
                            probability_medium=None,
                            probability_low=None,
                            collection_status="data_insufficient",
                            valid_windows_received=len(windows),
                            minimum_windows_required=1,
                            session_elapsed_seconds=round(acad_sec + non_acad_sec + idle_sec + unknown_sec, 1),
                            last_telemetry_at=last_updated,
                            prediction_type="Final",
                            prediction_available=False,
                            prediction_reason=reason,
                            last_updated_time=last_updated,
                            professor_review_status=None,
                            professor_override_label=None,
                            prediction_id=None,
                            model_version=None,
                            is_advisory=True,
                            review_required=True,
                        )
                    )

            else:
                # Active session: aggregate live rolling telemetry windows
                windows = (
                    db.query(EngagementFeatureWindow)
                    .filter(
                        EngagementFeatureWindow.session_id == session_id,
                        EngagementFeatureWindow.student_id == s_id,
                        EngagementFeatureWindow.validation_status == "valid",
                    )
                    .order_by(EngagementFeatureWindow.window_start_at.asc())
                    .all()
                )

                apps_summary = {}
                websites_summary = {}
                completeness = 100.0

                if windows:
                    app_sec = sum(getattr(w, "allowed_academic_application_active_seconds", 0.0) or 0.0 for w in windows)
                    web_sec = sum(getattr(w, "allowed_academic_website_active_seconds", 0.0) or 0.0 for w in windows)
                    acad_sec = app_sec + web_sec
                    if acad_sec == 0.0:
                        acad_sec = sum(w.academic_active_seconds for w in windows)
                        app_sec = acad_sec
                    non_acad_sec = sum(w.non_academic_active_seconds for w in windows)
                    idle_sec = sum(w.idle_seconds for w in windows)
                    unknown_sec = sum(getattr(w, "unknown_or_unavailable_seconds", 0.0) or 0.0 for w in windows)
                    switches = sum(w.application_switch_count for w in windows)
                    unauth = max(sum(w.unauthorized_application_attempt_count for w in windows), live_unauth)
                    blocked = max(sum(w.blocked_website_attempt_count for w in windows), live_blocked)
                    violations = max(sum(w.policy_violation_count for w in windows), live_violations)
                    last_updated = windows[-1].window_end_at
                    last_elapsed = windows[-1].session_elapsed_seconds
                    completeness = getattr(windows[-1], "feature_completeness_percent", 100.0) or 100.0
                    for w in windows:
                        bd = getattr(w, "approved_resources_breakdown", None) or {}
                        if isinstance(bd, dict):
                            for a_name, a_s in bd.get("applications", {}).items():
                                apps_summary[a_name] = round(apps_summary.get(a_name, 0.0) + float(a_s), 2)
                            for w_name, w_s in bd.get("websites", {}).items():
                                websites_summary[w_name] = round(websites_summary.get(w_name, 0.0) + float(w_s), 2)
                elif p and p.joined_at:
                    p_joined = p.joined_at if p.joined_at.tzinfo else p.joined_at.replace(tzinfo=timezone.utc)
                    dur = max(0.0, (now - p_joined).total_seconds())
                    violations = live_violations
                    unauth = live_unauth
                    blocked = live_blocked
                    switches = 0
                    non_acad_sec = float(min(dur, violations * 10.0))
                    acad_sec = float(max(0.0, dur - non_acad_sec))
                    app_sec = acad_sec
                    web_sec = 0.0
                    idle_sec = 0.0
                    unknown_sec = 0.0
                    last_updated = now
                    last_elapsed = dur
                else:
                    app_sec = 0.0
                    web_sec = 0.0
                    acad_sec = 0.0
                    non_acad_sec = 0.0
                    idle_sec = 0.0
                    unknown_sec = 0.0
                    switches = 0
                    unauth = 0
                    blocked = 0
                    violations = 0
                    last_updated = session.created_at
                    last_elapsed = 0.0

                latest_pred = (
                    db.query(EngagementPrediction)
                    .filter(
                        EngagementPrediction.session_id == session_id,
                        EngagementPrediction.student_id == s_id,
                    )
                    .order_by(EngagementPrediction.generated_at.desc())
                    .first()
                )

                # If joined in live session without a saved prediction yet and at least one 5-minute window or 300s elapsed, generate live preliminary prediction
                if not latest_pred and active_model and (sess_status == "Joined" or has_joined or acad_sec > 0) and completeness >= 80.0 and (last_elapsed >= 300.0 or len(windows) >= 1):
                    tot_elapsed = max(acad_sec + non_acad_sec + idle_sec + unknown_sec, last_elapsed, 1.0)
                    raw_dict = {
                        "allowed_academic_application_active_seconds": app_sec,
                        "allowed_academic_website_active_seconds": web_sec,
                        "academic_active_seconds": acad_sec,
                        "non_academic_active_seconds": non_acad_sec,
                        "idle_seconds": idle_sec,
                        "unknown_or_unavailable_seconds": unknown_sec,
                        "application_switch_count": switches,
                        "unauthorized_application_attempt_count": unauth,
                        "blocked_website_attempt_count": blocked,
                        "policy_violation_count": violations,
                        "session_elapsed_seconds": tot_elapsed,
                    }
                    features = compute_feature_vector(raw_dict)
                    inference = predict_engagement_from_features(db, features)
                    if inference.get("prediction_available"):
                        now_utc = datetime.now(timezone.utc)
                        latest_pred = EngagementPrediction(
                            model_version_id=active_model.id,
                            student_id=s_id,
                            device_id=stud_dev_id,
                            batch_id=session.batch_id,
                            session_id=session_id,
                            prediction=inference["prediction"],
                            confidence=inference["confidence"],
                            probability_high=inference["probability_high"],
                            probability_medium=inference["probability_medium"],
                            probability_low=inference["probability_low"],
                            feature_snapshot_json=features,
                            prediction_type="live",
                            review_status="preliminary",
                            generated_at=now_utc,
                        )
                        db.add(latest_pred)
                        db.commit()
                        db.refresh(latest_pred)

                if latest_pred and latest_pred.prediction:
                    m_tag = None
                    if latest_pred.model_version_id:
                        m_rec = db.get(MLModelVersion, latest_pred.model_version_id)
                        m_tag = m_rec.version_tag if m_rec else latest_pred.model_version_id

                    students_list.append(
                        StudentEngagementRowItem(
                            student_name=student_name,
                            student_id=s_id,
                            student_email=student_email,
                            session_status=sess_status,
                            policy_status=pol_status,
                            allowed_academic_application_active_seconds=round(app_sec, 1),
                            allowed_academic_website_active_seconds=round(web_sec, 1),
                            allowed_academic_active_seconds=round(acad_sec, 1),
                            academic_activity_seconds=round(acad_sec, 1),
                            non_academic_activity_seconds=round(non_acad_sec, 1),
                            idle_seconds=round(idle_sec, 1),
                            unknown_or_unavailable_seconds=round(unknown_sec, 1),
                            feature_completeness_percent=completeness,
                            approved_apps_summary=apps_summary or None,
                            approved_websites_summary=websites_summary or None,
                            application_switch_count=switches,
                            blocked_website_attempt_count=blocked,
                            unauthorized_application_attempt_count=unauth,
                            policy_violation_count=violations,
                            engagement_estimate=latest_pred.prediction,
                            confidence=latest_pred.confidence,
                            probability_high=latest_pred.probability_high,
                            probability_medium=latest_pred.probability_medium,
                            probability_low=latest_pred.probability_low,
                            collection_status="preliminary_prediction",
                            valid_windows_received=max(len(windows), 1),
                            minimum_windows_required=1,
                            session_elapsed_seconds=round(last_elapsed, 1),
                            last_telemetry_at=last_updated,
                            prediction_type="Live Preliminary",
                            prediction_available=True,
                            prediction_reason=None,
                            last_updated_time=latest_pred.generated_at or last_updated,
                            professor_review_status=latest_pred.review_status,
                            professor_override_label=latest_pred.professor_override_label,
                            prediction_id=latest_pred.id,
                            model_version=m_tag,
                            is_advisory=True,
                            review_required=True,
                        )
                    )
                else:
                    if not active_model:
                        reason = "No approved ML model is available yet"
                        c_status = "data_insufficient"
                    elif sess_status == "Not Joined":
                        reason = "Student has not joined this session yet"
                        c_status = "collecting"
                    elif len(windows) < 1 or last_elapsed < 300.0:
                        reason = "Collecting live activity data"
                        c_status = "collecting"
                    elif completeness < 80.0:
                        reason = f"Data completeness is {completeness:.1f}%, which is below the 80% threshold. More valid activity data is required for an estimate."
                        c_status = "data_insufficient"
                    else:
                        reason = "More valid activity data is required for an estimate."
                        c_status = "data_insufficient"

                    students_list.append(
                        StudentEngagementRowItem(
                            student_name=student_name,
                            student_id=s_id,
                            student_email=student_email,
                            session_status=sess_status,
                            policy_status=pol_status,
                            allowed_academic_application_active_seconds=round(app_sec, 1),
                            allowed_academic_website_active_seconds=round(web_sec, 1),
                            allowed_academic_active_seconds=round(acad_sec, 1),
                            academic_activity_seconds=round(acad_sec, 1),
                            non_academic_activity_seconds=round(non_acad_sec, 1),
                            idle_seconds=round(idle_sec, 1),
                            unknown_or_unavailable_seconds=round(unknown_sec, 1),
                            feature_completeness_percent=completeness,
                            approved_apps_summary=apps_summary or None,
                            approved_websites_summary=websites_summary or None,
                            application_switch_count=switches,
                            blocked_website_attempt_count=blocked,
                            unauthorized_application_attempt_count=unauth,
                            policy_violation_count=violations,
                            engagement_estimate=None,
                            confidence=None,
                            probability_high=None,
                            probability_medium=None,
                            probability_low=None,
                            collection_status=c_status,
                            valid_windows_received=len(windows),
                            minimum_windows_required=1,
                            session_elapsed_seconds=round(last_elapsed, 1),
                            last_telemetry_at=last_updated,
                            prediction_type="Collecting" if c_status == "collecting" else "Live Preliminary",
                            prediction_available=False,
                            prediction_reason=reason,
                            last_updated_time=last_updated,
                            professor_review_status=None,
                            professor_override_label=None,
                            prediction_id=None,
                            model_version=None,
                            is_advisory=True,
                            review_required=True,
                        )
                    )

        return SessionEngagementDetailResponse(
            session_id=session.id,
            session_title=session.title,
            batch_id=session.batch_id,
            batch_name=batch.name if batch else "Unknown Batch",
            session_status=session.status,
            is_active=is_live,
            has_active_model=bool(active_model),
            model_version_tag=active_model.version_tag if active_model else None,
            students=students_list,
            empty_reason=None if students_list else "No students joined this session.",
        )

    @staticmethod
    def get_session_prediction_history(
        db: Session,
        session_id: str,
        current_user: User,
        student_id: Optional[str] = None,
    ) -> List[dict]:
        """Retrieve all engagement prediction history for a session."""
        session = db.get(SessionModel, session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        batch = db.get(Batch, session.batch_id) if session.batch_id else None
        is_owner = (session.created_by == current_user.id) or (
            batch and batch.professor_id == current_user.id
        )
        if current_user.role != "admin" and not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view prediction history for this session",
            )

        query = db.query(EngagementPrediction).filter(EngagementPrediction.session_id == session_id)
        if student_id:
            query = query.filter(EngagementPrediction.student_id == student_id)
        
        preds = query.order_by(EngagementPrediction.generated_at.asc()).all()

        results = []
        for p in preds:
            model = db.get(MLModelVersion, p.model_version_id) if p.model_version_id else None
            win_start = (
                p.feature_window.window_start_at.isoformat()
                if (p.feature_window and p.feature_window.window_start_at)
                else None
            )
            win_end = (
                p.feature_window.window_end_at.isoformat()
                if (p.feature_window and p.feature_window.window_end_at)
                else None
            )
            results.append({
                "id": p.id,
                "session_id": p.session_id,
                "student_id": p.student_id,
                "prediction": p.prediction,
                "confidence": p.confidence,
                "prediction_type": p.prediction_type,
                "review_status": p.review_status,
                "professor_override_label": p.professor_override_label,
                "model_version_tag": model.version_tag if model else None,
                "window_start_at": win_start,
                "window_end_at": win_end,
                "generated_at": p.generated_at.isoformat() if p.generated_at else None,
            })
        return results

    @staticmethod
    def review_prediction_with_audit(
        db: Session,
        prediction_id: str,
        review_data: PredictionReviewRequest,
        current_user: User,
    ) -> PredictionReviewResponse:
        """Review and optionally override an engagement prediction, preserving immutable model output and writing an audit log."""
        pred = db.get(EngagementPrediction, prediction_id)
        if not pred:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")

        session = db.get(SessionModel, pred.session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        batch = db.get(Batch, session.batch_id) if session.batch_id else None
        is_owner = (session.created_by == current_user.id) or (
            batch and batch.professor_id == current_user.id
        )
        if current_user.role != "admin" and not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to review predictions for this session",
            )

        now = datetime.now(timezone.utc)
        action_type = review_data.action.lower()

        if action_type == "confirm":
            pred.review_status = "confirmed"
            pred.professor_override_label = None
            msg = "Prediction confirmed successfully"
        else:
            pred.review_status = "overridden"
            pred.professor_override_label = review_data.override_label or "High"
            msg = f"Prediction overridden to {pred.professor_override_label} successfully"

        pred.reviewed_by = current_user.id
        pred.reviewed_at = now

        # Create audit record
        audit = AuditLog(
            actor_user_id=current_user.id,
            action="REVIEW_ENGAGEMENT_PREDICTION",
            entity_type="engagement_prediction",
            entity_id=pred.id,
            metadata_json={
                "session_id": pred.session_id,
                "student_id": pred.student_id,
                "model_estimate": pred.prediction,
                "confidence": pred.confidence,
                "action": action_type,
                "review_status": pred.review_status,
                "override_label": pred.professor_override_label,
                "notes": review_data.notes,
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(pred)

        return PredictionReviewResponse(
            prediction_id=pred.id,
            session_id=pred.session_id,
            student_id=pred.student_id,
            model_estimate=pred.prediction,
            confidence=pred.confidence,
            professor_review_status=pred.review_status,
            professor_override_label=pred.professor_override_label,
            reviewed_by=current_user.id,
            reviewed_at=now,
            message=msg,
        )
