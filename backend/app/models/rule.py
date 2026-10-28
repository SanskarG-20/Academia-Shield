"""
RuleSet, WebsiteRule, DomainRule, ApplicationRule, and DevicePolicyRequirement Entity Models.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .user import generate_uuid, utc_now
from ..core.database import Base

class RuleSet(Base):
    __tablename__ = "rule_sets"

    id = Column(String, primary_key=True, default=generate_uuid)
    batch_id = Column(String, ForeignKey("batches.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    class_id = Column(String, ForeignKey("classes.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String, default="draft", nullable=False, index=True)  # draft, published, revoked
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    issued_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    integrity_hash = Column(String, nullable=False)  # SHA-256 hash
    signature = Column(String, nullable=True)  # Server cryptographic signature
    created_by = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    batch = relationship("Batch", foreign_keys=[batch_id])
    session = relationship("SessionModel", foreign_keys=[session_id])
    class_obj = relationship("ClassModel", back_populates="rule_sets")
    creator = relationship("User", foreign_keys=[created_by])
    website_rules = relationship("WebsiteRule", back_populates="rule_set", cascade="all, delete-orphan")
    domain_rules = relationship("DomainRule", back_populates="rule_set", cascade="all, delete-orphan")
    application_rules = relationship("ApplicationRule", back_populates="rule_set", cascade="all, delete-orphan")
    device_requirements = relationship("DevicePolicyRequirement", back_populates="rule_set", uselist=False, cascade="all, delete-orphan")

    @property
    def policy_hash(self) -> str:
        return self.integrity_hash

class WebsiteRule(Base):
    __tablename__ = "website_rules"

    id = Column(String, primary_key=True, default=generate_uuid)
    rule_set_id = Column(String, ForeignKey("rule_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    domain_pattern = Column(String, nullable=False, index=True)
    rule_mode = Column(String, default="blocked", nullable=False)  # allowed, blocked
    category = Column(String, default="general", nullable=False)  # academic, general
    priority = Column(Integer, default=10, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    rule_set = relationship("RuleSet", back_populates="website_rules")

class DomainRule(Base):
    """Backward compatibility model for domain_rules table."""
    __tablename__ = "domain_rules"

    id = Column(String, primary_key=True, default=generate_uuid)
    rule_set_id = Column(String, ForeignKey("rule_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    domain_pattern = Column(String, nullable=False, index=True)
    rule_type = Column(String, default="exact", nullable=False)  # exact, wildcard
    action = Column(String, default="block", nullable=False)  # block, allow, log
    priority = Column(Integer, default=10, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    reason = Column(String, nullable=True)

    # Relationships
    rule_set = relationship("RuleSet", back_populates="domain_rules")

class ApplicationRule(Base):
    __tablename__ = "application_rules"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "executable_name", name="uq_app_rule_set_exec"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    rule_set_id = Column(String, ForeignKey("rule_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    application_name = Column(String, nullable=True)
    executable_name = Column(String, nullable=False, index=True)
    executable_path_pattern = Column(String, nullable=True)
    trusted_hash = Column(String(64), nullable=True)
    rule_mode = Column(String, default="blocked", nullable=False)  # allowed, blocked
    category = Column(String, default="general", nullable=False)  # academic, general
    action = Column(String, default="close", nullable=False)  # log, warn, close
    priority = Column(Integer, default=0, nullable=False)
    cooldown_seconds = Column(Integer, default=0, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    rule_set = relationship("RuleSet", back_populates="application_rules")

class DevicePolicyRequirement(Base):
    __tablename__ = "device_policy_requirements"

    id = Column(String, primary_key=True, default=generate_uuid)
    rule_set_id = Column(String, ForeignKey("rule_sets.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    require_agent_enrolled = Column(Boolean, default=True, nullable=False)
    require_dns_or_content_filter = Column(Boolean, default=True, nullable=False)
    require_application_control = Column(Boolean, default=True, nullable=False)
    require_managed_browser_policy = Column(Boolean, default=False, nullable=False)
    require_usb_storage_restriction = Column(Boolean, default=False, nullable=False)
    required_enforcement_level = Column(String, default="development", nullable=False)  # audit, development, managed, strict
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    rule_set = relationship("RuleSet", back_populates="device_requirements")

class ProtectedProcess(Base):
    __tablename__ = "protected_processes"

    id = Column(String, primary_key=True, default=generate_uuid)
    executable_name = Column(String, unique=True, index=True, nullable=False)
    executable_path_pattern = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
