"""
Session Entity Model.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from .user import generate_uuid, utc_now
from ..core.database import Base

class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    batch_id = Column(String, ForeignKey("batches.id", ondelete="CASCADE"), nullable=True, index=True)
    class_id = Column(String, ForeignKey("classes.id", ondelete="CASCADE"), nullable=True, index=True)
    rule_set_id = Column(String, ForeignKey("rule_sets.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    start_at_utc = Column(DateTime, nullable=False)
    end_at_utc = Column(DateTime, nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    timezone = Column(String, default="UTC", nullable=False)
    recurrence_type = Column(String, default="none", nullable=False)  # none, daily, weekly
    recurrence_interval = Column(Integer, default=1, nullable=False)
    recurrence_days_of_week = Column(JSON, nullable=True)
    recurrence_until_utc = Column(DateTime, nullable=True)
    status = Column(String, default="scheduled", nullable=False, index=True)  # scheduled, active, paused, ended, cancelled
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    policy_version = Column(Integer, default=1, nullable=False)
    session_code = Column(String(12), nullable=True, index=True)
    idle_threshold_seconds = Column(Integer, default=60, nullable=False)
    emergency_stopped_at = Column(DateTime, nullable=True)
    emergency_stopped_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    emergency_stop_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    batch = relationship("Batch", foreign_keys=[batch_id])
    class_obj = relationship("ClassModel", back_populates="sessions")
    rule_set = relationship("RuleSet", foreign_keys=[rule_set_id])
    creator = relationship("User", foreign_keys=[created_by])
    emergency_stopper = relationship("User", foreign_keys=[emergency_stopped_by])
    telemetry_events = relationship("TelemetryEvent", back_populates="session", cascade="all, delete-orphan")
    policy_violations = relationship("PolicyViolation", back_populates="session", cascade="all, delete-orphan")
    participants = relationship("SessionParticipant", back_populates="session", cascade="all, delete-orphan")
    unlock_requests = relationship("UnlockRequest", back_populates="session", cascade="all, delete-orphan")

class SessionParticipant(Base):
    __tablename__ = "session_participants"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="joined")  # joined, left
    joined_at = Column(DateTime, default=utc_now, nullable=False)
    left_at = Column(DateTime, nullable=True)
    enforcement_activated_at = Column(DateTime, nullable=True)
    enforcement_stop_reason = Column(String, nullable=True)
    policy_acknowledged_at = Column(DateTime, nullable=True)

    # Relationships
    session = relationship("SessionModel", back_populates="participants")
    student = relationship("User", foreign_keys=[student_id])


class SessionPresence(Base):
    __tablename__ = "session_presence"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_presence_student"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    browser_last_seen_at = Column(DateTime, nullable=True)
    agent_last_seen_at = Column(DateTime, nullable=True)
    connected_socket_count = Column(Integer, default=0, nullable=False)
    joined_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    session = relationship("SessionModel", foreign_keys=[session_id])
    student = relationship("User", foreign_keys=[student_id])


class UnlockRequest(Base):
    __tablename__ = "unlock_requests"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    issue_type = Column(String, default="technical_issue", nullable=False)  # unlock_request, technical_issue, emergency
    description = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False, index=True)  # pending, approved, rejected, resolved
    resolution_notes = Column(String, nullable=True)
    resolved_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    session = relationship("SessionModel", back_populates="unlock_requests")
    student = relationship("User", foreign_keys=[student_id])
    resolver = relationship("User", foreign_keys=[resolved_by])


