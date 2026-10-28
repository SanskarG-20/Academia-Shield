"""
Session State Management & Evaluation Service.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from ..models.session import SessionModel
from ..models.audit_log import AuditLog
from .schedule_evaluator import ScheduleEvaluator, ScheduleEvaluationResult

LOGGER = logging.getLogger(__name__)

class SessionStateService:
    """Evaluates session state transitions and updates active session statuses."""

    @staticmethod
    def evaluate_session(session_model: SessionModel, now_utc: Optional[datetime] = None) -> ScheduleEvaluationResult:
        """Evaluate schedule state for a given SessionModel instance."""
        return ScheduleEvaluator.evaluate(
            start_at_utc=session_model.start_at_utc,
            end_at_utc=session_model.end_at_utc,
            status=session_model.status,
            tz_name=session_model.timezone,
            recurrence_type=session_model.recurrence_type,
            recurrence_interval=session_model.recurrence_interval,
            recurrence_days_of_week=session_model.recurrence_days_of_week,
            recurrence_until_utc=session_model.recurrence_until_utc,
            now_utc=now_utc
        )

    @staticmethod
    def sync_active_session_states(db: Session, now_utc: Optional[datetime] = None) -> int:
        """
        Periodically sync session is_active and status fields based on current UTC time.
        Returns count of updated sessions.
        """
        now = now_utc or datetime.now(timezone.utc)
        sessions = db.query(SessionModel).filter(SessionModel.status.in_(["scheduled", "active", "Upcoming", "Active"])).all()

        updated_count = 0
        for sess in sessions:
            res = SessionStateService.evaluate_session(sess, now_utc=now)
            if res.state == "active" and not sess.is_active:
                sess.is_active = True
                sess.status = "active"
                sess.policy_version += 1
                sess.updated_at = now
                updated_count += 1
            elif res.state in ("ended", "expired") and sess.is_active:
                sess.is_active = False
                sess.status = "ended"
                sess.policy_version += 1
                sess.updated_at = now
                updated_count += 1

        if updated_count > 0:
            db.commit()

        return updated_count
