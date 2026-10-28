"""
TelemetryEvent and PolicyViolation Entity Models.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .user import generate_uuid, utc_now
from ..core.database import Base

class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id = Column(String, primary_key=True, default=generate_uuid)
    event_id = Column(String, unique=True, index=True, nullable=False)  # Unique UUID idempotency key
    device_id = Column(String, ForeignKey("agent_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)  # dns_block, process_violation, heartbeat, tamper_alert
    payload_json = Column(JSON, nullable=False)
    occurred_at = Column(DateTime, nullable=False)
    received_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    device = relationship("AgentDevice", back_populates="telemetry_events")
    session = relationship("SessionModel", back_populates="telemetry_events")

class PolicyViolation(Base):
    __tablename__ = "policy_violations"

    id = Column(String, primary_key=True, default=generate_uuid)
    device_id = Column(String, ForeignKey("agent_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    rule_id = Column(String, nullable=True)
    violation_type = Column(String, nullable=False)  # web, process, drift
    target_value = Column(String, nullable=False)  # e.g. domain name or exe name
    action_taken = Column(String, nullable=False)  # blocked, closed, warning
    occurred_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    device = relationship("AgentDevice", back_populates="policy_violations")
    session = relationship("SessionModel", back_populates="policy_violations")
