"""
AuditLog Entity Model.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .user import generate_uuid, utc_now
from ..core.database import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    actor_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(String, nullable=False, index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    actor = relationship("User")
