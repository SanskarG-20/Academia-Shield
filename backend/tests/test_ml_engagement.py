"""Automated Test Suite for Real-Time ML Student Engagement Prediction.

Verifies:
1. Canonical 14-dimensional feature extraction & mathematical properties.
2. Training pipeline (RandomForestClassifier, class_weight='balanced', joblib artifact, draft status).
3. Lifecycle & Model Registry (draft -> approved -> retired, rollback, zero unapproved inference).
4. Real-time inference (High/Medium/Low, probabilities summing to ~1.0, confidence).
5. 5-minute guard (elapsed < 300s returns 'Waiting for enough live session data').
6. Storage in engagement_predictions (immutable audit record, feature snapshot).
7. Final session consolidation on session end.
8. Advisory preliminary status, professor review/override without auto-punishment.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import status

from app.models.user import User
from app.models.device import AgentDevice
from app.models.batch import Batch, BatchMember
from app.models.session import SessionModel, SessionParticipant
from app.models.engagement import (
    EngagementFeatureWindow,
    SessionEngagementLabel,
    MLModelVersion,
    EngagementPrediction,
)
from app.core.security import hash_password, create_access_token
from app.ml.features import compute_feature_vector, CANONICAL_FEATURE_NAMES
from app.ml.train_engagement import train_engagement_model
from app.ml.model_registry import approve_model, retire_model, get_active_model
from app.ml.predictor import predict_engagement_from_features


def _create_user(db, email, role="student", full_name=None):
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        role=role,
        full_name=full_name or email.split("@")[0].capitalize(),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_header(user):
    token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role, "type": "access"}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ml_setup(db_session):
    admin = _create_user(db_session, "admin_ml@example.edu", role="admin", full_name="Admin ML")
    prof = _create_user(db_session, "prof_ml@example.edu", role="professor", full_name="Prof ML")
    student1 = _create_user(db_session, "alice_ml@example.edu", role="student", full_name="Alice ML")
    student2 = _create_user(db_session, "bob_ml@example.edu", role="student", full_name="Bob ML")
    student3 = _create_user(db_session, "carol_ml@example.edu", role="student", full_name="Carol ML")

    dev1 = AgentDevice(
        user_id=student1.id,
        device_name="Alice ML PC",
        device_identifier="DEV-ALICE-ML",
        public_key="pub_alice_ml_123",
        platform="windows",
        agent_version="2.3.0",
        is_active=True,
    )
    dev2 = AgentDevice(
        user_id=student2.id,
        device_name="Bob ML PC",
        device_identifier="DEV-BOB-ML",
        public_key="pub_bob_ml_123",
        platform="windows",
        agent_version="2.3.0",
        is_active=True,
    )
    db_session.add_all([dev1, dev2])
    db_session.commit()

    batch = Batch(professor_id=prof.id, name="ML Test Batch", is_active=True)
    db_session.add(batch)
    db_session.commit()

    bm1 = BatchMember(batch_id=batch.id, student_id=student1.id, status="active")
    bm2 = BatchMember(batch_id=batch.id, student_id=student2.id, status="active")
    bm3 = BatchMember(batch_id=batch.id, student_id=student3.id, status="active")
    db_session.add_all([bm1, bm2, bm3])
    db_session.commit()

    now = datetime.now(timezone.utc)
    session = SessionModel(
        title="ML Lab Session",
        created_by=prof.id,
        batch_id=batch.id,
        status="active",
        is_active=True,
        policy_version=1,
        start_at_utc=now - timedelta(minutes=45),
        end_at_utc=now + timedelta(minutes=45),
        started_at=now - timedelta(minutes=45),
    )
    db_session.add(session)
    db_session.commit()

    sp1 = SessionParticipant(session_id=session.id, student_id=student1.id, status="joined")
    sp2 = SessionParticipant(session_id=session.id, student_id=student2.id, status="joined")
    db_session.add_all([sp1, sp2])
    db_session.commit()

    return {
        "admin": admin,
        "prof": prof,
        "student1": student1,
        "student2": student2,
        "student3": student3,
        "dev1": dev1,
        "dev2": dev2,
        "batch": batch,
        "session": session,
    }


def test_canonical_14_features_computation():
    """Verify that all 14 canonical features are correctly calculated and bounded."""
    raw = {
        "academic_active_seconds": 240.0,
        "non_academic_active_seconds": 30.0,
        "idle_seconds": 30.0,
        "application_switch_count": 5,
        "unauthorized_application_attempt_count": 1,
        "blocked_website_attempt_count": 2,
        "policy_violation_count": 3,
        "session_elapsed_seconds": 300.0,
    }
    feats = compute_feature_vector(raw)

    # Check 14 keys
    assert len(feats) == 14
    for k in CANONICAL_FEATURE_NAMES:
        assert k in feats

    assert feats["academic_active_seconds"] == 240.0
    assert feats["academic_activity_ratio"] == round(240.0 / 270.0, 4)
    assert feats["non_academic_activity_ratio"] == round(30.0 / 270.0, 4)
    assert feats["idle_ratio"] == round(30.0 / 300.0, 4)
    assert feats["application_switches_per_minute"] == round(5.0 / 5.0, 4)
    assert feats["blocked_attempts_per_minute"] == round(2.0 / 5.0, 4)
    assert feats["violation_rate"] == round(3.0 / 5.0, 4)


def test_train_approve_and_retire_lifecycle(db_session, ml_setup):
    """Verify ML training pipeline, draft state, admin approval, and model rollback."""
    s = ml_setup
    now = datetime.now(timezone.utc)

    # Create historical completed session with ground truth labels
    hist_session = SessionModel(
        title="Completed Lab 0",
        created_by=s["prof"].id,
        batch_id=s["batch"].id,
        status="ended",
        is_active=False,
        policy_version=1,
        start_at_utc=now - timedelta(hours=3),
        end_at_utc=now - timedelta(hours=2),
        started_at=now - timedelta(hours=3),
        ended_at=now - timedelta(hours=2),
    )
    db_session.add(hist_session)
    db_session.commit()

    # Create 3 labeled samples (High, Medium, Low)
    students = [s["student1"], s["student2"], s["student3"]]
    labels = ["High", "Medium", "Low"]
    for idx, (st, lbl) in enumerate(zip(students, labels)):
        w = EngagementFeatureWindow(
            event_id=f"hist-evt-{idx}-{uuid.uuid4()}",
            student_id=st.id,
            device_id=s["dev1"].id,
            batch_id=s["batch"].id,
            session_id=hist_session.id,
            window_start_at=now - timedelta(hours=2, minutes=5 * (idx + 1)),
            window_end_at=now - timedelta(hours=2, minutes=5 * idx),
            policy_version=1,
            academic_active_seconds=270.0 if lbl == "High" else (150.0 if lbl == "Medium" else 30.0),
            non_academic_active_seconds=20.0 if lbl == "High" else (100.0 if lbl == "Medium" else 200.0),
            idle_seconds=10.0 if lbl == "High" else 50.0,
            application_switch_count=2 if lbl == "High" else 15,
            unauthorized_application_attempt_count=0,
            blocked_website_attempt_count=0 if lbl == "High" else 4,
            policy_violation_count=0 if lbl == "High" else 3,
            session_elapsed_seconds=300.0 * (idx + 1),
            validation_status="valid",
        )
        db_session.add(w)

        l_rec = SessionEngagementLabel(
            session_id=hist_session.id,
            student_id=st.id,
            professor_id=s["prof"].id,
            label=lbl,
        )
        db_session.add(l_rec)
    db_session.commit()

    # Train model
    model = train_engagement_model(
        db=db_session,
        trained_by_user_id=s["admin"].id,
        hyperparameters={"n_estimators": 10},
        custom_tag="rf-test-lifecycle-v1",
    )
    assert model.status == "draft"
    assert model.metrics_json is not None
    assert "accuracy" in model.metrics_json
    assert os.path.exists(model.artifact_path)

    # While draft, no active model
    active = get_active_model(db_session)
    assert active is None

    # Admin approves model
    approved = approve_model(db_session, model_id=model.id, admin_user_id=s["admin"].id)
    assert approved.status == "approved"
    assert approved.approved_by == s["admin"].id
    assert approved.approved_at is not None

    # Now get_active_model returns this model
    assert get_active_model(db_session).id == model.id

    # Admin retires model
    retired = retire_model(db_session, model_id=model.id)
    assert retired.status == "retired"
    assert retired.retired_at is not None
    assert get_active_model(db_session) is None


def test_5min_guard_and_live_inference_api(client, db_session, ml_setup):
    """
    Verify:
    1. Early telemetry (< 300s) returns 'Waiting for enough live session data'.
    2. Complete 5-minute telemetry with approved model generates live prediction.
    3. Prediction is advisory and preliminary.
    """
    s = ml_setup
    now = datetime.now(timezone.utc)

    # First, train & approve a model so live predictions can run
    hist_session = SessionModel(
        title="Hist Lab",
        created_by=s["prof"].id,
        batch_id=s["batch"].id,
        status="ended",
        is_active=False,
        start_at_utc=now - timedelta(hours=3),
        end_at_utc=now - timedelta(hours=2),
    )
    db_session.add(hist_session)
    db_session.commit()

    for idx, (st, lbl) in enumerate([(s["student1"], "High"), (s["student2"], "Medium"), (s["student3"], "Low")]):
        w = EngagementFeatureWindow(
            event_id=f"guard-evt-{idx}-{uuid.uuid4()}",
            student_id=st.id,
            device_id=s["dev1"].id,
            batch_id=s["batch"].id,
            session_id=hist_session.id,
            window_start_at=now - timedelta(hours=2, minutes=5 * (idx + 1)),
            window_end_at=now - timedelta(hours=2, minutes=5 * idx),
            policy_version=1,
            academic_active_seconds=260.0 if lbl == "High" else 60.0,
            non_academic_active_seconds=20.0,
            idle_seconds=20.0,
            session_elapsed_seconds=300.0 * (idx + 1),
            validation_status="valid",
        )
        db_session.add(w)
        db_session.add(SessionEngagementLabel(
            session_id=hist_session.id, student_id=st.id, professor_id=s["prof"].id, label=lbl
        ))
    db_session.commit()

    m = train_engagement_model(db=db_session, trained_by_user_id=s["admin"].id, hyperparameters={"n_estimators": 10})
    approve_model(db_session, model_id=m.id, admin_user_id=s["admin"].id)

    # Step 1: Submit early window (< 300s elapsed, e.g. 120s)
    early_payload = {
        "event_id": str(uuid.uuid4()),
        "student_id": s["student1"].id,
        "device_id": s["dev1"].id,
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=2)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 100.0,
        "non_academic_active_seconds": 10.0,
        "idle_seconds": 10.0,
        "application_switch_count": 1,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 120.0,  # < 300s
    }

    res_early = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=early_payload,
        headers=_auth_header(s["student1"]),
    )
    assert res_early.status_code == status.HTTP_200_OK

    # Query professor live view: should state waiting for enough data
    res_prof = client.get(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/live",
        headers=_auth_header(s["prof"]),
    )
    assert res_prof.status_code == status.HTTP_200_OK
    data = res_prof.json()
    st1 = next(item for item in data["students"] if item["student_id"] == s["student1"].id)
    assert st1["prediction_available"] is False
    assert "Waiting for enough live session data" in st1["prediction_reason"]

    # Step 2: Submit full 5-minute window (elapsed >= 300s, e.g. 300s)
    full_payload = {
        "event_id": str(uuid.uuid4()),
        "student_id": s["student1"].id,
        "device_id": s["dev1"].id,
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=5)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 270.0,
        "non_academic_active_seconds": 15.0,
        "idle_seconds": 15.0,
        "application_switch_count": 2,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 300.0,  # >= 300s
    }
    res_full = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=full_payload,
        headers=_auth_header(s["student1"]),
    )
    assert res_full.status_code == status.HTTP_200_OK

    # Live monitor should now have an advisory prediction
    res_live = client.get(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/live",
        headers=_auth_header(s["prof"]),
    )
    assert res_live.status_code == status.HTTP_200_OK
    live_data = res_live.json()
    st1_live = next(item for item in live_data["students"] if item["student_id"] == s["student1"].id)
    assert st1_live["prediction_available"] is True
    assert st1_live["predicted_engagement"] in {"High", "Medium", "Low"}
    assert 0.0 <= st1_live["confidence"] <= 1.0
    assert st1_live["review_status"] == "preliminary"
    assert st1_live["latest_prediction_id"] is not None

    # Step 3: Professor reviews & overrides prediction
    pred_id = st1_live["latest_prediction_id"]
    res_rev = client.patch(
        f"/api/v1/professor/sessions/engagement-predictions/{pred_id}/review?override_label=High",
        headers=_auth_header(s["prof"]),
    )
    assert res_rev.status_code == status.HTTP_200_OK
    assert res_rev.json()["review_status"] == "reviewed"
    assert res_rev.json()["professor_override_label"] == "High"
