"""
Engagement Telemetry Feature Window and Professor Labelling Entity Models.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from .user import generate_uuid, utc_now
from ..core.database import Base

class EngagementFeatureWindow(Base):
    __tablename__ = "engagement_feature_windows"

    id = Column(String, primary_key=True, default=generate_uuid)
    event_id = Column(String, unique=True, index=True, nullable=False)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String, ForeignKey("agent_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String, ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    window_start_at = Column(DateTime, nullable=False)
    window_end_at = Column(DateTime, nullable=False)
    policy_version = Column(Integer, nullable=False)

    # Privacy-minimized aggregated telemetry features
    allowed_academic_application_active_seconds = Column(Float, nullable=False, default=0.0)
    allowed_academic_website_active_seconds = Column(Float, nullable=False, default=0.0)
    academic_active_seconds = Column(Float, nullable=False, default=0.0)
    non_academic_active_seconds = Column(Float, nullable=False, default=0.0)
    idle_seconds = Column(Float, nullable=False, default=0.0)
    unknown_or_unavailable_seconds = Column(Float, nullable=False, default=0.0)
    active_resource_sample_count = Column(Integer, nullable=False, default=0)
    unknown_resource_sample_count = Column(Integer, nullable=False, default=0)
    application_switch_count = Column(Integer, nullable=False, default=0)
    unauthorized_application_attempt_count = Column(Integer, nullable=False, default=0)
    blocked_website_attempt_count = Column(Integer, nullable=False, default=0)
    policy_violation_count = Column(Integer, nullable=False, default=0)
    session_elapsed_seconds = Column(Float, nullable=False, default=0.0)
    feature_completeness_percent = Column(Float, nullable=False, default=100.0)
    completeness_percent = Column(Float, nullable=False, default=100.0)
    approved_resources_breakdown = Column(JSON, nullable=True)

    # Validation & Auditing
    validation_status = Column(String, default="valid", nullable=False, index=True)  # valid, invalid, rejected
    validation_error = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    student = relationship("User", foreign_keys=[student_id])
    device = relationship("AgentDevice", foreign_keys=[device_id])
    batch = relationship("Batch", foreign_keys=[batch_id])
    session = relationship("SessionModel", foreign_keys=[session_id])


class SessionEngagementLabel(Base):
    __tablename__ = "session_engagement_labels"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student_engagement_label"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    professor_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String, nullable=False)  # High, Medium, Low
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    session = relationship("SessionModel", foreign_keys=[session_id])
    student = relationship("User", foreign_keys=[student_id])
    professor = relationship("User", foreign_keys=[professor_id])


class MLModelVersion(Base):
    __tablename__ = "ml_models"

    id = Column(String, primary_key=True, default=generate_uuid)
    version_tag = Column(String, unique=True, index=True, nullable=False)
    algorithm = Column(String, default="RandomForestClassifier", nullable=False)
    status = Column(String, default="draft", nullable=False, index=True)  # draft, approved, retired
    hyperparameters_json = Column(JSON, nullable=True)
    metrics_json = Column(JSON, nullable=True)  # accuracy, precision, recall, f1, confusion_matrix, etc.
    artifact_path = Column(String, nullable=False)
    trained_by = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    approved_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    retired_at = Column(DateTime, nullable=True)

    # Relationships
    trainer = relationship("User", foreign_keys=[trained_by])
    approver = relationship("User", foreign_keys=[approved_by])
    predictions = relationship("EngagementPrediction", back_populates="model_version")


class EngagementPrediction(Base):
    __tablename__ = "engagement_predictions"
    __table_args__ = (
        UniqueConstraint("model_version_id", "feature_window_id", name="uq_model_feature_window_prediction"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    model_version_id = Column(String, ForeignKey("ml_models.id", ondelete="SET NULL"), nullable=True, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String, ForeignKey("agent_devices.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String, ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_window_id = Column(String, ForeignKey("engagement_feature_windows.id", ondelete="SET NULL"), nullable=True, index=True)
    session_summary_id = Column(String, ForeignKey("engagement_session_summaries.id", ondelete="SET NULL", use_alter=True), nullable=True, index=True)

    # Prediction Output
    prediction = Column(String, nullable=False)  # High, Medium, Low
    confidence = Column(Float, nullable=False)
    probability_high = Column(Float, nullable=False)
    probability_medium = Column(Float, nullable=False)
    probability_low = Column(Float, nullable=False)
    feature_snapshot_json = Column(JSON, nullable=False)  # Strictly safe canonical features

    # Operational lifecycle
    collection_status = Column(String, default="preliminary_prediction", nullable=True)  # collecting, data_insufficient, preliminary_prediction, final_prediction
    prediction_type = Column(String, default="preliminary", nullable=False)  # preliminary, final
    review_status = Column(String, default="pending", nullable=False)  # pending, confirmed, overridden, reviewed
    professor_override_label = Column(String, nullable=True)  # High, Medium, Low
    generated_at = Column(DateTime, default=utc_now, nullable=False)
    reviewed_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # Relationships
    model_version = relationship("MLModelVersion", back_populates="predictions")
    student = relationship("User", foreign_keys=[student_id])
    device = relationship("AgentDevice", foreign_keys=[device_id])
    batch = relationship("Batch", foreign_keys=[batch_id])
    session = relationship("SessionModel", foreign_keys=[session_id])
    feature_window = relationship("EngagementFeatureWindow", foreign_keys=[feature_window_id])
    session_summary = relationship("EngagementSessionSummary", foreign_keys=[session_summary_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])


class EngagementSessionSummary(Base):
    __tablename__ = "engagement_session_summaries"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_session_student_engagement_summary"),
    )

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String, ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String, ForeignKey("agent_devices.id", ondelete="SET NULL"), nullable=True, index=True)

    allowed_academic_application_active_seconds = Column(Float, nullable=False, default=0.0)
    allowed_academic_website_active_seconds = Column(Float, nullable=False, default=0.0)
    allowed_academic_active_seconds = Column(Float, nullable=False, default=0.0)
    academic_active_seconds = Column(Float, nullable=False, default=0.0)
    non_academic_active_seconds = Column(Float, nullable=False, default=0.0)
    idle_seconds = Column(Float, nullable=False, default=0.0)
    unknown_or_unavailable_seconds = Column(Float, nullable=False, default=0.0)
    active_resource_sample_count = Column(Integer, nullable=False, default=0)
    unknown_resource_sample_count = Column(Integer, nullable=False, default=0)
    application_switch_count = Column(Integer, nullable=False, default=0)
    unauthorized_application_attempt_count = Column(Integer, nullable=False, default=0)
    blocked_website_attempt_count = Column(Integer, nullable=False, default=0)
    policy_violation_count = Column(Integer, nullable=False, default=0)
    session_elapsed_seconds = Column(Float, nullable=False, default=0.0)

    # Standardized total_* columns matching specification
    total_allowed_academic_application_active_seconds = Column(Float, nullable=True, default=0.0)
    total_allowed_academic_website_active_seconds = Column(Float, nullable=True, default=0.0)
    total_allowed_academic_active_seconds = Column(Float, nullable=True, default=0.0)
    total_academic_active_seconds = Column(Float, nullable=True, default=0.0)
    total_non_academic_active_seconds = Column(Float, nullable=True, default=0.0)
    total_idle_seconds = Column(Float, nullable=True, default=0.0)
    total_unknown_or_unavailable_seconds = Column(Float, nullable=True, default=0.0)
    total_application_switch_count = Column(Integer, nullable=True, default=0)
    total_unauthorized_application_attempt_count = Column(Integer, nullable=True, default=0)
    total_blocked_website_attempt_count = Column(Integer, nullable=True, default=0)
    total_policy_violation_count = Column(Integer, nullable=True, default=0)
    total_session_elapsed_seconds = Column(Float, nullable=True, default=0.0)

    data_completeness_percent = Column(Float, default=100.0, nullable=False)
    feature_completeness_percent = Column(Float, default=100.0, nullable=False)
    approved_resources_breakdown = Column(JSON, nullable=True)
    engagement_label = Column(String, nullable=True)  # high, medium, low
    labelled_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    labelled_at = Column(DateTime, nullable=True)

    final_prediction_id = Column(String, ForeignKey("engagement_predictions.id", ondelete="SET NULL", use_alter=True), nullable=True, index=True)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    session = relationship("SessionModel", foreign_keys=[session_id])
    student = relationship("User", foreign_keys=[student_id])
    batch = relationship("Batch", foreign_keys=[batch_id])
    device = relationship("AgentDevice", foreign_keys=[device_id])
    final_prediction = relationship("EngagementPrediction", foreign_keys=[final_prediction_id])
    labeller = relationship("User", foreign_keys=[labelled_by])


# Model alias for engagement model versioning
EngagementModelVersion = MLModelVersion
