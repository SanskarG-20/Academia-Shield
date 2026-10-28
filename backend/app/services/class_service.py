"""
Class and Session Business Logic Service.
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..models.class_model import ClassModel, ClassMember
from ..models.session import SessionModel
from ..models.audit_log import AuditLog
from ..models.user import User
from ..schemas.class_schema import ClassCreate
from ..schemas.session import SessionCreate, SessionUpdate

class ClassService:
    """Manages Classes, Student memberships, Academic Sessions, and Audit Logging."""

    @staticmethod
    def _log_audit(actor_id: str, action: str, entity_type: str, entity_id: str, metadata: dict, db: Session):
        audit = AuditLog(
            actor_user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata
        )
        db.add(audit)

    @staticmethod
    def create_class(req: ClassCreate, professor: User, db: Session) -> ClassModel:
        class_obj = ClassModel(
            professor_id=professor.id,
            name=req.name.strip(),
            course_code=req.course_code.strip().upper(),
            description=req.description
        )
        db.add(class_obj)
        db.commit()
        db.refresh(class_obj)
        return class_obj

    @staticmethod
    def get_classes_for_user(user: User, db: Session) -> List[ClassModel]:
        if user.role == "admin":
            return db.query(ClassModel).all()
        elif user.role == "professor":
            return db.query(ClassModel).filter(ClassModel.professor_id == user.id).all()
        else:  # student
            memberships = db.query(ClassMember).filter(ClassMember.student_id == user.id).all()
            class_ids = [m.class_id for m in memberships]
            return db.query(ClassModel).filter(ClassModel.id.in_(class_ids)).all()

    @staticmethod
    def add_student_to_class(class_id: str, student_email_or_id: str, professor: User, db: Session) -> ClassMember:
        class_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
        if not class_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

        if professor.role != "admin" and class_obj.professor_id != professor.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only class owner can manage students")

        student = db.query(User).filter(User.email == student_email_or_id.strip().lower()).first()
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found with specified email")

        if student.role != "student":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target user is not a student")

        existing = db.query(ClassMember).filter(ClassMember.class_id == class_id, ClassMember.student_id == student.id).first()
        if existing:
            return existing

        member = ClassMember(class_id=class_id, student_id=student.id)
        db.add(member)
        db.commit()
        db.refresh(member)
        return member

    @staticmethod
    def verify_class_access(class_id: str, user: User, db: Session) -> ClassModel:
        """Verify user has permission to view class data."""
        class_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
        if not class_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

        if user.role == "admin":
            return class_obj
        if user.role == "professor":
            if class_obj.professor_id != user.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to unowned class")
            return class_obj
        # Student
        enrolled = db.query(ClassMember).filter(ClassMember.class_id == class_id, ClassMember.student_id == user.id).first()
        if not enrolled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Student not enrolled in class")
        return class_obj

    @staticmethod
    def create_session(class_id: str, req: SessionCreate, user: User, db: Session) -> SessionModel:
        class_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
        if not class_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

        if user.role != "admin" and class_obj.professor_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only class owner can create sessions")

        dt_start = req.start_at_utc or req.start_at
        dt_end = req.end_at_utc or req.end_at
        if not dt_start or not dt_end:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_at_utc and end_at_utc are required")

        if req.timezone and req.timezone != "UTC":
            try:
                import zoneinfo
                zoneinfo.ZoneInfo(req.timezone)
            except Exception:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Invalid IANA timezone: {req.timezone}")

        if dt_start.tzinfo is None or dt_end.tzinfo is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Timezone offset or Z is required for timestamps.")

        start_utc = dt_start.astimezone(timezone.utc)
        end_utc = dt_end.astimezone(timezone.utc)

        if req.recurrence_type and req.recurrence_type.lower() not in ("none", "daily", "weekly"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Invalid recurrence_type '{req.recurrence_type}'. Must be 'none', 'daily', or 'weekly'.")

        if end_utc <= start_utc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Session end time must be strictly after start time.")

        session_obj = SessionModel(
            class_id=class_id,
            created_by=user.id,
            title=req.title.strip(),
            start_at=start_utc,
            end_at=end_utc,
            start_at_utc=start_utc,
            end_at_utc=end_utc,
            timezone=req.timezone,
            recurrence_type=req.recurrence_type,
            recurrence_interval=req.recurrence_interval,
            recurrence_days_of_week=req.recurrence_days_of_week,
            recurrence_until_utc=req.recurrence_until_utc,
            status="scheduled",
            is_active=False,
            policy_version=1
        )
        db.add(session_obj)
        db.flush()

        ClassService._log_audit(
            actor_id=user.id,
            action="session_created",
            entity_type="session",
            entity_id=session_obj.id,
            metadata={"class_id": class_id, "title": session_obj.title, "timezone": req.timezone},
            db=db
        )

        db.commit()
        db.refresh(session_obj)
        session_obj.server_time_utc = datetime.now(timezone.utc).isoformat()
        return session_obj

    @staticmethod
    def list_class_sessions(class_id: str, user: User, db: Session) -> List[SessionModel]:
        ClassService.verify_class_access(class_id, user, db)
        return db.query(SessionModel).filter(SessionModel.class_id == class_id).all()

    @staticmethod
    def get_session(session_id: str, user: User, db: Session) -> SessionModel:
        session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        ClassService.verify_class_access(session_obj.class_id, user, db)
        return session_obj

    @staticmethod
    def update_session(session_id: str, req: SessionUpdate, user: User, db: Session) -> SessionModel:
        session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        class_obj = db.query(ClassModel).filter(ClassModel.id == session_obj.class_id).first()
        if user.role != "admin" and class_obj.professor_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only class owner can edit sessions")

        if req.title is not None:
            session_obj.title = req.title.strip()
        dt_start = req.start_at_utc or req.start_at
        if dt_start is not None:
            session_obj.start_at_utc = dt_start.astimezone(timezone.utc)
            session_obj.start_at = session_obj.start_at_utc

        dt_end = req.end_at_utc or req.end_at
        if dt_end is not None:
            session_obj.end_at_utc = dt_end.astimezone(timezone.utc)
            session_obj.end_at = session_obj.end_at_utc
        if req.timezone is not None:
            session_obj.timezone = req.timezone
        if req.recurrence_type is not None:
            session_obj.recurrence_type = req.recurrence_type
        if req.recurrence_interval is not None:
            session_obj.recurrence_interval = req.recurrence_interval
        if req.recurrence_days_of_week is not None:
            session_obj.recurrence_days_of_week = req.recurrence_days_of_week
        if req.recurrence_until_utc is not None:
            session_obj.recurrence_until_utc = req.recurrence_until_utc
        if req.status is not None:
            session_obj.status = req.status
            if req.status == "active":
                session_obj.is_active = True
            elif req.status in ("ended", "cancelled", "scheduled"):
                session_obj.is_active = False

        session_obj.policy_version += 1
        session_obj.updated_at = datetime.now(timezone.utc)

        ClassService._log_audit(
            actor_id=user.id,
            action="session_updated",
            entity_type="session",
            entity_id=session_id,
            metadata={"new_version": session_obj.policy_version, "status": session_obj.status},
            db=db
        )

        db.commit()
        db.refresh(session_obj)
        return session_obj

    @staticmethod
    def start_session(session_id: str, user: User, db: Session) -> SessionModel:
        session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        class_obj = db.query(ClassModel).filter(ClassModel.id == session_obj.class_id).first()
        if user.role != "admin" and class_obj.professor_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only class owner can start session")

        now = datetime.now(timezone.utc)
        session_obj.status = "active"
        session_obj.is_active = True
        session_obj.start_at_utc = now
        session_obj.start_at = now
        session_obj.policy_version += 1
        session_obj.updated_at = now

        ClassService._log_audit(
            actor_id=user.id,
            action="session_started",
            entity_type="session",
            entity_id=session_id,
            metadata={"policy_version": session_obj.policy_version},
            db=db
        )

        db.commit()
        db.refresh(session_obj)
        return session_obj

    @staticmethod
    def end_session(session_id: str, user: User, db: Session) -> SessionModel:
        session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        class_obj = db.query(ClassModel).filter(ClassModel.id == session_obj.class_id).first()
        if user.role != "admin" and class_obj.professor_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only class owner can end session")

        now = datetime.now(timezone.utc)
        session_obj.status = "ended"
        session_obj.is_active = False
        session_obj.end_at_utc = now
        session_obj.end_at = now
        session_obj.policy_version += 1
        session_obj.updated_at = now

        ClassService._log_audit(
            actor_id=user.id,
            action="session_ended",
            entity_type="session",
            entity_id=session_id,
            metadata={"policy_version": session_obj.policy_version},
            db=db
        )

        db.commit()
        db.refresh(session_obj)
        return session_obj

    @staticmethod
    def cancel_session(session_id: str, user: User, db: Session) -> SessionModel:
        session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        class_obj = db.query(ClassModel).filter(ClassModel.id == session_obj.class_id).first()
        if user.role != "admin" and class_obj.professor_id != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only class owner can cancel session")

        now = datetime.now(timezone.utc)
        session_obj.status = "cancelled"
        session_obj.is_active = False
        session_obj.policy_version += 1
        session_obj.updated_at = now

        ClassService._log_audit(
            actor_id=user.id,
            action="session_cancelled",
            entity_type="session",
            entity_id=session_id,
            metadata={"policy_version": session_obj.policy_version},
            db=db
        )

        db.commit()
        db.refresh(session_obj)
        return session_obj
