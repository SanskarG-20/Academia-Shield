"""
Class and ClassMember Entity Models.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .user import generate_uuid, utc_now
from ..core.database import Base

class ClassModel(Base):
    __tablename__ = "classes"

    id = Column(String, primary_key=True, default=generate_uuid)
    professor_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    course_code = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    professor = relationship("User", back_populates="classes_owned")
    members = relationship("ClassMember", back_populates="class_obj", cascade="all, delete-orphan")
    sessions = relationship("SessionModel", back_populates="class_obj", cascade="all, delete-orphan")
    rule_sets = relationship("RuleSet", back_populates="class_obj", cascade="all, delete-orphan")

class ClassMember(Base):
    __tablename__ = "class_members"
    __table_args__ = (
        UniqueConstraint("class_id", "student_id", name="uq_class_student"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    class_id = Column(String, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    class_obj = relationship("ClassModel", back_populates="members")
    student = relationship("User", back_populates="class_memberships")
