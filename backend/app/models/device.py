from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy.orm import relationship, synonym
from .user import generate_uuid, utc_now
from ..core.database import Base

class AgentDevice(Base):
    __tablename__ = "agent_devices"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_name = Column(String, nullable=False)
    device_identifier = Column(String, unique=True, index=True, nullable=False)
    public_key = Column(String, nullable=False)  # Ed25519 public key string
    platform = Column(String, nullable=False)  # windows, macos, linux
    platform_version = Column(String, nullable=True)
    agent_version = Column(String, nullable=False)
    enrollment_status = Column(String, default="enrolled", nullable=False)  # enrolled, revoked, pending
    is_active = Column(Boolean, default=True, nullable=False)
    capabilities_json = Column(JSON, nullable=True)
    compliance_status = Column(String, default="compliant", nullable=False)  # compliant, non_compliant, unknown
    compliance_level = Column(String, default="personal", nullable=False)  # personal, managed, strict
    policy_delivery_state = Column(String, default="idle", nullable=False)  # idle, delivered, acknowledged, active, restored, rejected
    last_policy_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    enrolled_at = Column(DateTime, default=utc_now, nullable=False)
    last_seen_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Synonyms / Aliases for student_id and os_version
    student_id = synonym("user_id")
    os_version = synonym("platform_version")

    # Relationships
    user = relationship("User", back_populates="devices")
    refresh_tokens = relationship("RefreshToken", back_populates="device", cascade="all, delete-orphan")
    telemetry_events = relationship("TelemetryEvent", back_populates="device", cascade="all, delete-orphan")
    policy_violations = relationship("PolicyViolation", back_populates="device", cascade="all, delete-orphan")
    compliance_reports = relationship("DeviceComplianceReport", back_populates="device", cascade="all, delete-orphan")


class DeviceEnrollmentToken(Base):
    __tablename__ = "device_enrollment_tokens"

    id = Column(String, primary_key=True, default=generate_uuid)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, unique=True, index=True, nullable=False)
    token = Column(String, nullable=True)  # Optional one-time plaintext token displayed during issuance
    is_used = Column(Boolean, default=False, nullable=False)
    used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    student = relationship("User")


class DeviceComplianceReport(Base):
    __tablename__ = "device_compliance_reports"

    id = Column(String, primary_key=True, default=generate_uuid)
    device_id = Column(String, ForeignKey("agent_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    reported_at = Column(DateTime, default=utc_now, nullable=False)
    agent_running = Column(Boolean, default=True, nullable=False)
    policy_signature_valid = Column(Boolean, default=True, nullable=False)
    dns_or_content_filter_status = Column(String, default="active", nullable=False)  # active, degraded, unavailable
    browser_policy_status = Column(String, default="active", nullable=False)  # active, degraded, unavailable
    application_control_status = Column(String, default="active", nullable=False)  # active, degraded, unavailable
    removable_storage_status = Column(String, default="allowed", nullable=False)  # allowed, restricted, unavailable
    compliance_level = Column(String, default="personal", nullable=False)  # personal, managed, strict
    error_reason = Column(String, nullable=True)

    # Relationships
    device = relationship("AgentDevice", back_populates="compliance_reports")


class AgentPolicy(Base):
    __tablename__ = "agent_policies"

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_version = Column(Integer, default=1, nullable=False)
    batch_id = Column(String, ForeignKey("batches.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True)
    target_platform = Column(String, nullable=False)  # windows, macos, all
    enforcement_level = Column(String, default="development", nullable=False)  # audit, personal, managed, strict
    issued_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    integrity_hash = Column(String, nullable=False)
    signature = Column(String, nullable=False)
    payload_json = Column(JSON, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    # Relationships
    batch = relationship("Batch")
    session = relationship("SessionModel")


class AgentPolicyAssignment(Base):
    __tablename__ = "agent_policy_assignments"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", "device_id", name="uq_session_student_device"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    policy_id = Column(String, ForeignKey("agent_policies.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String, ForeignKey("agent_devices.id", ondelete="CASCADE"), nullable=True, index=True)
    state = Column(String, default="pending", nullable=False, index=True)  # pending, active, revoked, restored, failed
    assigned_at = Column(DateTime, default=utc_now, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    restored_at = Column(DateTime, nullable=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    failure_reason = Column(String, nullable=True)

    # Relationships
    session = relationship("SessionModel")
    student = relationship("User", foreign_keys=[student_id])
    device = relationship("AgentDevice", foreign_keys=[device_id])
    policy = relationship("AgentPolicy", foreign_keys=[policy_id])


