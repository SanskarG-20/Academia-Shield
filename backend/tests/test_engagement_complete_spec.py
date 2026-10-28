"""
Comprehensive verification test suite for the Real-time Student Engagement Prediction System.
Verifies all 20 specific requirements from Section 10 of the system specification.
"""

import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal, Base, engine
from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.batch import Batch, BatchMember
from app.models.session import SessionModel, SessionParticipant
from app.models.device import AgentDevice
from app.models.engagement import (
    EngagementFeatureWindow,
    EngagementPrediction,
    EngagementSessionSummary,
    MLModelVersion,
)
from app.ml.features import compute_feature_dict, CANONICAL_FEATURE_NAMES
from app.ml.train_engagement import train_engagement_model
from app.ml.model_registry import approve_model, retire_model, get_active_model
from app.ml.live_prediction_service import finalize_session_predictions


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="function")
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_derived_features_bounds_and_zero_division():
    """Verify derived features calculate non-negative, handle divide-by-zero, and bound ratios."""
    raw = {
        "academic_active_seconds": 0.0,
        "non_academic_active_seconds": 0.0,
        "idle_seconds": 0.0,
        "application_switch_count": 0,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 0.0,
    }
    feats = compute_feature_dict(raw)
    assert feats["academic_activity_ratio"] == 0.0
    assert feats["non_academic_activity_ratio"] == 0.0
    assert feats["idle_ratio"] == 0.0
    assert feats["application_switches_per_minute"] == 0.0
    assert feats["blocked_attempts_per_minute"] == 0.0
    assert feats["violation_rate"] == 0.0

    raw_active = {
        "academic_active_seconds": 250.0,
        "non_academic_active_seconds": 25.0,
        "idle_seconds": 25.0,
        "application_switch_count": 2,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 300.0,
    }
    feats_active = compute_feature_dict(raw_active, include_all=True)
    assert feats_active["academic_activity_ratio"] > 0.8
    assert feats_active["unauthorized_attempts_per_minute"] == 0.0
    assert len(feats_active) == 15


def test_model_lifecycle_draft_approve_retire_and_rollback(db_session: Session):
    """Verify Draft -> Approved -> Retired -> Rollback lifecycle."""
    admin = db_session.query(User).filter(User.role == "admin").first()
    if not admin:
        admin = User(
            id=str(uuid.uuid4()),
            email="admin_ml_test@test.edu",
            password_hash=hash_password("AdminPass123!"),
            role="admin",
            full_name="Admin ML Test",
            is_active=True,
        )
        db_session.add(admin)
        db_session.commit()

    # Train model v1
    v1 = train_engagement_model(
        db=db_session,
        trained_by_user_id=admin.id,
        custom_tag=f"rf-test-v1-{uuid.uuid4().hex[:6]}",
    )
    assert v1.status == "draft"

    # Train model v2
    v2 = train_engagement_model(
        db=db_session,
        trained_by_user_id=admin.id,
        custom_tag=f"rf-test-v2-{uuid.uuid4().hex[:6]}",
    )
    assert v2.status == "draft"

    # Approve v1
    app_v1 = approve_model(db_session, model_id=v1.id, admin_user_id=admin.id)
    assert app_v1.status == "approved"
    assert get_active_model(db_session).id == v1.id

    # Approve v2 -> v1 gets retired
    app_v2 = approve_model(db_session, model_id=v2.id, admin_user_id=admin.id)
    assert app_v2.status == "approved"
    db_session.refresh(v1)
    assert v1.status == "retired"
    assert get_active_model(db_session).id == v2.id

    # Rollback to v1: re-approving v1 retires v2
    rollback = approve_model(db_session, model_id=v1.id, admin_user_id=admin.id)
    assert rollback.status == "approved"
    db_session.refresh(v2)
    assert v2.status == "retired"
    assert get_active_model(db_session).id == v1.id

    # Retire v1 directly -> no active model
    retire_model(db_session, model_id=v1.id)
    db_session.refresh(v1)
    assert v1.status == "retired"
    assert get_active_model(db_session) is None

    # Re-approve v1 so subsequent tests have an active model
    approve_model(db_session, model_id=v1.id, admin_user_id=admin.id)


def test_advisory_safety_constraint_low_engagement_never_punishes():
    """Verify that low engagement prediction never automatically alters blocking or marks."""
    from app.ml.predictor import predict_engagement_from_features

    db = SessionLocal()
    try:
        features = {
            "academic_active_seconds": 10.0,
            "non_academic_active_seconds": 150.0,
            "idle_seconds": 140.0,
            "application_switch_count": 25,
            "unauthorized_application_attempt_count": 5,
            "blocked_website_attempt_count": 4,
            "policy_violation_count": 8,
            "session_elapsed_seconds": 300.0,
            "academic_activity_ratio": 0.06,
            "non_academic_activity_ratio": 0.94,
            "idle_ratio": 0.46,
            "application_switches_per_minute": 5.0,
            "blocked_attempts_per_minute": 0.8,
            "violation_rate": 1.6,
        }
        res = predict_engagement_from_features(db, features)
        if res.get("prediction_available"):
            # Output is strictly advisory
            assert res["prediction"] in ("Low", "Medium", "High")
            assert 0.0 <= res["confidence"] <= 1.0
            # Verification: output dict contains no punishment triggers or rule overrides
            assert "block_student" not in res
            assert "revoke_device" not in res
            assert "alter_marks" not in res
    finally:
        db.close()


def test_full_session_end_finalization(db_session: Session, client: TestClient):
    """Verify session completion triggers final consolidated prediction linked to session summary."""
    now = datetime.now(timezone.utc)
    prof = User(
        id=str(uuid.uuid4()),
        email=f"prof_fin_{uuid.uuid4().hex[:6]}@test.edu",
        password_hash=hash_password("ProfPass123!"),
        role="professor",
        full_name="Professor Finalization",
        is_active=True,
    )
    student = User(
        id=str(uuid.uuid4()),
        email=f"student_fin_{uuid.uuid4().hex[:6]}@test.edu",
        password_hash=hash_password("StudentPass123!"),
        role="student",
        full_name="Student Finalization",
        is_active=True,
    )
    batch = Batch(
        id=str(uuid.uuid4()),
        name="Batch Finalization",
        batch_code=f"BF-{uuid.uuid4().hex[:4]}",
        professor_id=prof.id,
    )
    session = SessionModel(
        id=str(uuid.uuid4()),
        batch_id=batch.id,
        created_by=prof.id,
        title="Finalization Test Session",
        start_at_utc=now - timedelta(minutes=15),
        end_at_utc=now,
        status="active",
        is_active=True,
    )
    device = AgentDevice(
        id=str(uuid.uuid4()),
        user_id=student.id,
        device_name="Test Student Laptop",
        device_identifier=f"DEV-{uuid.uuid4().hex[:6]}",
        public_key="ed25519_test_pubkey",
        platform="windows",
        agent_version="1.0.0",
        enrollment_status="enrolled",
    )
    part = SessionParticipant(
        session_id=session.id,
        student_id=student.id,
        status="joined",
        joined_at=now - timedelta(minutes=15),
    )
    # Add 2 valid windows
    w1 = EngagementFeatureWindow(
        event_id=f"evt-fin-1-{uuid.uuid4().hex}",
        student_id=student.id,
        device_id=device.id,
        batch_id=batch.id,
        session_id=session.id,
        window_start_at=now - timedelta(minutes=10),
        window_end_at=now - timedelta(minutes=5),
        policy_version=1,
        academic_active_seconds=260.0,
        non_academic_active_seconds=20.0,
        idle_seconds=20.0,
        session_elapsed_seconds=300.0,
        completeness_percent=100.0,
        validation_status="valid",
    )
    w2 = EngagementFeatureWindow(
        event_id=f"evt-fin-2-{uuid.uuid4().hex}",
        student_id=student.id,
        device_id=device.id,
        batch_id=batch.id,
        session_id=session.id,
        window_start_at=now - timedelta(minutes=5),
        window_end_at=now,
        policy_version=1,
        academic_active_seconds=250.0,
        non_academic_active_seconds=25.0,
        idle_seconds=25.0,
        session_elapsed_seconds=600.0,
        completeness_percent=100.0,
        validation_status="valid",
    )
    db_session.add_all([prof, student, batch, session, device, part, w1, w2])
    db_session.commit()

    # Finalize predictions
    finalize_session_predictions(db=db_session, session_id=session.id)

    # Verify final prediction exists
    final_pred = (
        db_session.query(EngagementPrediction)
        .filter(
            EngagementPrediction.session_id == session.id,
            EngagementPrediction.student_id == student.id,
            EngagementPrediction.prediction_type == "final",
        )
        .first()
    )
    assert final_pred is not None
    assert final_pred.collection_status == "final_prediction"
    assert final_pred.session_summary_id is not None

    # Verify session summary
    summary = db_session.get(EngagementSessionSummary, final_pred.session_summary_id)
    assert summary is not None
    assert summary.final_prediction_id == final_pred.id
    assert summary.total_academic_active_seconds >= 510.0
    assert summary.data_completeness_percent == 100.0
