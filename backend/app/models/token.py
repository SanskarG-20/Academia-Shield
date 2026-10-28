"""
RefreshToken Entity Model.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .user import generate_uuid, utc_now
from ..core.database import Base

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String, ForeignKey("agent_devices.id", ondelete="CASCADE"), nullable=True, index=True)
    token_hash = Column(String, unique=True, index=True, nullable=False)  # SHA-256 hash
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")
    device = relationship("AgentDevice", back_populates="refresh_tokens")
