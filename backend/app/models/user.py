"""
User Entity Model.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from ..core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="student")  # admin, professor, student, agent
    # Profile fields are shared by student and professor accounts.  They are
    # nullable so existing deployments can be upgraded without data loss.
    institutional_id = Column(String, nullable=True, index=True)
    department = Column(String, nullable=True)
    roll_number = Column(String, nullable=True)
    year = Column(String, nullable=True)
    designation = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    classes_owned = relationship("ClassModel", back_populates="professor", cascade="all, delete-orphan")
    class_memberships = relationship("ClassMember", back_populates="student", cascade="all, delete-orphan")
    devices = relationship("AgentDevice", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
