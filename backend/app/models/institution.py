"""
Academia Shield Institution Settings Model.
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime
from .user import generate_uuid, utc_now
from ..core.database import Base

class InstitutionSetting(Base):
    __tablename__ = "institution_settings"

    id = Column(String, primary_key=True, default=generate_uuid)
    institution_name = Column(String, default="Academia Shield Institution", nullable=False)
    allow_usb_blocking = Column(Boolean, default=True, nullable=False)
    fail_safe_grace_seconds = Column(Integer, default=120, nullable=False)
    max_session_duration_minutes = Column(Integer, default=240, nullable=False)
    require_student_consent = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
