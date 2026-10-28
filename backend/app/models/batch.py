"""
Batch and BatchMember Entity Models.
"""

import secrets
import string
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .user import generate_uuid, utc_now
from ..core.database import Base

def generate_batch_code(length: int = 6) -> str:
    """Generate a secure, random uppercase alphanumeric batch join code."""
    chars = string.ascii_uppercase + string.digits
    # Remove potentially confusing characters (0, O, 1, I)
    chars = chars.translate(str.maketrans("", "", "0O1I"))
    return "".join(secrets.choice(chars) for _ in range(length))

class Batch(Base):
    __tablename__ = "batches"

    id = Column(String, primary_key=True, default=generate_uuid)
    professor_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    batch_code = Column(String, unique=True, index=True, nullable=False, default=generate_batch_code)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    professor = relationship("User", foreign_keys=[professor_id])
    members = relationship("BatchMember", back_populates="batch", cascade="all, delete-orphan")

class BatchMember(Base):
    __tablename__ = "batch_members"
    __table_args__ = (
        UniqueConstraint("batch_id", "student_id", name="uq_batch_student"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    batch_id = Column(String, ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="active")  # active, removed
    joined_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    batch = relationship("Batch", back_populates="members")
    student = relationship("User", foreign_keys=[student_id])
