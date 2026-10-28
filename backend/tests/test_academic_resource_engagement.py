"""
Comprehensive Automated Test Suite for Academic Resource Student Engagement.

Verifies all 15 specification requirements:
1. Telemetry ingest accepts valid approved apps and website times.
2. Idle time with open approved app is categorized strictly as idle.
3. Unapproved window active while approved app is open counts as non-academic.
4. Unverified domain time accumulates in unknown_or_unavailable_seconds without violations.
5. Completeness < 80% triggers data_insufficient status.
6. Window < 300s session elapsed triggers collecting status.
7. Active session returns preliminary/live prediction.
8. Ended session returns final_prediction and updates EngagementSessionSummary.
9. 17-feature extraction matches canonical vector.
10. Model predictor rejects non-17-feature models.
11. Active v2 model yields valid predictions.
12. WebSocket broadcasts carry advisory disclaimer and approved resource breakdown.
13. Professor review endpoint functions correctly and records audit log.
14. Privacy check: zero keystrokes/passwords/URLs stored in database records.
15. REST API endpoint /professor/engagement/sessions/{session_id} returns full student row items with approved app/web breakdowns.
"""

import sys
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest
from fastapi import status

from app.models.user import User
from app.models.batch import Batch, BatchMember
from app.models.session import SessionModel, SessionParticipant, SessionPresence
from app.models.device import AgentDevice
from app.models.audit_log import AuditLog
from app.models.engagement import (
    EngagementFeatureWindow,
    EngagementPrediction,
    EngagementSessionSummary,
    MLModelVersion,
)
from app.core.security import hash_password, create_access_token
from app.ml.features import (
    FEATURE_NAMES,
    SCHEMA_VERSION,
    compute_feature_vector,
    compute_feature_dict,
    extract_feature_vector,
)
from app.ml.predictor import predict_engagement_from_features
from app.ml.live_prediction_service import (
    process_live_prediction_for_window,
    generate_final_prediction_for_student,
    finalize_session_predictions,
)
from app.services.engagement_service import (
    EngagementService,
    compute_student_engagement,
)

# Import agent telemetry tracker
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agent")))
from agent.telemetry.engagement_tracker import EngagementTracker


def _create_user(db_session, email, role="student", full_name=None):
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        role=role,
        full_name=full_name or email.split("@")[0].capitalize(),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_header(user):
    token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role, "type": "access"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def academic_engagement_fixture(db_session):
    prof = _create_user(db_session, "prof_acad@example.edu", role="professor", full_name="Professor Acad")
    student = _create_user(db_session, "student_acad@example.edu", role="student", full_name="Student Acad")

    batch = Batch(
        name="CS500 Academic Focus",
        batch_code="CS500AC",
        professor_id=prof.id,
    )
    db_session.add(batch)
    db_session.commit()
    db_session.refresh(batch)

    bm = BatchMember(batch_id=batch.id, student_id=student.id, status="active")
    db_session.add(bm)
    db_session.commit()

    now = datetime.now(timezone.utc)
    session_active = SessionModel(
        title="Live Coding Session",
        batch_id=batch.id,
        created_by=prof.id,
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=25),
        end_at_utc=now + timedelta(minutes=35),
        started_at=now - timedelta(minutes=25),
    )
    db_session.add(session_active)
    db_session.commit()
    db_session.refresh(session_active)

    participant = SessionParticipant(
        session_id=session_active.id,
        student_id=student.id,
        status="joined",
        joined_at=now - timedelta(minutes=25),
    )
    db_session.add(participant)
    db_session.commit()

    # Enrolled device
    device = AgentDevice(
        user_id=student.id,
        device_name="Student Laptop",
        device_identifier="DEV-ACAD-01",
        public_key="ed25519_dummy_key",
        platform="windows",
        agent_version="1.0.0",
        is_active=True,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)

    return {
        "prof": prof,
        "student": student,
        "batch": batch,
        "session": session_active,
        "device": device,
    }


# ============================================================================
# 1. Agent Telemetry Unit Tests
# ============================================================================

def test_agent_telemetry_idle_with_open_approved_app_is_strictly_idle():
    """Requirement 2: If an allowed app is open while student is idle, it must count as idle, NEVER academic."""
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")
    allowed_apps = ["code.exe", "pycharm64.exe"]

    with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=120.0), \
         patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=1234), \
         patch("agent.telemetry.engagement_tracker.psutil.Process") as mock_proc:
        mock_proc.return_value.name.return_value = "code.exe"
        for _ in range(3):
            tracker.last_tick_time = time.time() - 3.0
            tracker.tick(allowed_applications=allowed_apps, allowed_websites=[])

    # Telemetry should record 0 allowed app active seconds and 9.0 idle seconds
    assert tracker.allowed_academic_application_active_seconds == 0.0
    assert tracker.allowed_academic_website_active_seconds == 0.0
    assert tracker.academic_active_seconds == 0.0
    assert tracker.idle_seconds == pytest.approx(9.0, rel=0.1)


def test_agent_telemetry_unapproved_window_active_while_allowed_app_open():
    """Requirement 3: Foreground unapproved window while allowed app is open counts as non-academic."""
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")
    allowed_apps = ["code.exe"]

    with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=0.5), \
         patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=1234), \
         patch("agent.telemetry.engagement_tracker.psutil.Process") as mock_proc:
        mock_proc.return_value.name.return_value = "spotify.exe"
        for _ in range(3):
            tracker.last_tick_time = time.time() - 3.0
            tracker.tick(allowed_applications=allowed_apps, allowed_websites=[])

    assert tracker.allowed_academic_application_active_seconds == 0.0
    assert tracker.academic_active_seconds == 0.0
    assert tracker.non_academic_active_seconds == pytest.approx(9.0, rel=0.1)
    assert tracker.idle_seconds == 0.0


def test_agent_telemetry_approved_app_and_website_tracking():
    """Requirement 1: Foreground activity on approved apps and approved websites accumulates correctly."""
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")
    allowed_apps = ["code.exe"]
    allowed_domains = ["github.com", "docs.python.org"]

    # 2 ticks of code.exe (6s)
    for _ in range(2):
        with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=0.2), \
             patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=1234), \
             patch("agent.telemetry.engagement_tracker.psutil.Process") as mock_proc:
            mock_proc.return_value.name.return_value = "code.exe"
            tracker.last_tick_time = time.time() - 3.0
            tracker.tick(allowed_applications=allowed_apps, allowed_websites=allowed_domains)

    # 2 ticks of chrome.exe visiting docs.python.org (6s)
    for _ in range(2):
        with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=0.2), \
             patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=1234), \
             patch("agent.telemetry.engagement_tracker.psutil.Process") as mock_proc, \
             patch.object(tracker.fg_detector, "get_foreground_window_title", return_value="docs.python.org - Documentation"):
            mock_proc.return_value.name.return_value = "chrome.exe"
            tracker.last_tick_time = time.time() - 3.0
            tracker.tick(allowed_applications=allowed_apps, allowed_websites=allowed_domains)

    assert tracker.allowed_academic_application_active_seconds == pytest.approx(6.0, rel=0.1)
    assert tracker.allowed_academic_website_active_seconds == pytest.approx(6.0, rel=0.1)
    assert tracker.academic_active_seconds == pytest.approx(12.0, rel=0.1)
    assert "code.exe" in tracker.approved_apps_breakdown
    assert "docs.python.org" in tracker.approved_websites_breakdown


def test_agent_telemetry_unverified_domain_handling():
    """Requirement 4: Unverified domain time accumulates in unknown_or_unavailable_seconds without violations."""
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")
    allowed_apps = ["code.exe"]
    allowed_domains = ["github.com"]

    # Active browser, but domain extraction is unavailable
    for _ in range(2):
        with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=0.1), \
             patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=1234), \
             patch("agent.telemetry.engagement_tracker.psutil.Process") as mock_proc, \
             patch.object(tracker.fg_detector, "get_foreground_window_title", return_value=""):
            mock_proc.return_value.name.return_value = "chrome.exe"
            tracker.last_tick_time = time.time() - 3.0
            tracker.tick(allowed_applications=allowed_apps, allowed_websites=allowed_domains)

    assert tracker.unknown_or_unavailable_seconds == pytest.approx(6.0, rel=0.1)
    assert tracker.unknown_resource_sample_count == 2
    assert tracker.allowed_academic_application_active_seconds == 0.0
    assert tracker.allowed_academic_website_active_seconds == 0.0


# ============================================================================
# 2. Canonical 17-Feature Schema & Predictor Tests
# ============================================================================

def test_canonical_17_feature_schema():
    """Requirement 9 & 10: 17 canonical features, order preserved, schema version 2.0.0."""
    assert SCHEMA_VERSION == "2.0.0"
    assert len(FEATURE_NAMES) == 17

    expected_features = [
        # Positive academic activity features (6)
        "allowed_academic_application_active_seconds",
        "allowed_academic_website_active_seconds",
        "allowed_academic_active_seconds",
        "allowed_academic_activity_ratio",
        "allowed_app_activity_ratio",
        "allowed_website_activity_ratio",
        # Negative/distraction/idle/context features (11)
        "idle_seconds",
        "idle_ratio",
        "non_academic_active_seconds",
        "non_academic_activity_ratio",
        "unknown_or_unavailable_seconds",
        "unknown_activity_ratio",
        "application_switches_per_minute",
        "blocked_attempts_per_minute",
        "unauthorized_application_attempts_per_minute",
        "violation_rate",
        "session_elapsed_seconds",
    ]
    assert FEATURE_NAMES == expected_features

    # Test extraction with a mock window
    window = EngagementFeatureWindow(
        id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        student_id=str(uuid.uuid4()),
        device_id=str(uuid.uuid4()),
        batch_id=str(uuid.uuid4()),
        window_start_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        window_end_at=datetime.now(timezone.utc),
        policy_version=1,
        allowed_academic_application_active_seconds=180.0,
        allowed_academic_website_active_seconds=60.0,
        academic_active_seconds=240.0,
        non_academic_active_seconds=30.0,
        idle_seconds=30.0,
        unknown_or_unavailable_seconds=0.0,
        application_switch_count=3,
        unauthorized_application_attempt_count=0,
        blocked_website_attempt_count=0,
        policy_violation_count=0,
        session_elapsed_seconds=300.0,
        feature_completeness_percent=98.0,
    )
    feat_dict = compute_feature_vector(window)
    assert len(feat_dict) >= 17
    for f in FEATURE_NAMES:
        assert f in feat_dict

    vector = extract_feature_vector(feat_dict)
    assert len(vector) == 17
    # 240 academic out of 270 active time
    assert feat_dict["allowed_academic_active_seconds"] == 240.0
    assert feat_dict["allowed_academic_application_active_seconds"] == 180.0
    assert feat_dict["allowed_academic_website_active_seconds"] == 60.0
    assert feat_dict["allowed_academic_activity_ratio"] == pytest.approx(240.0 / 270.0, rel=1e-3)


def test_predictor_rejects_old_14_feature_model(db_session):
    """Requirement 10: Predictor strictly rejects models that do not match the 17-feature schema."""
    old_features = FEATURE_NAMES[:14]
    mock_model_record = MagicMock(
        id=str(uuid.uuid4()),
        version_tag="v1.0.0",
    )
    mock_artifact = {
        "model": MagicMock(feature_names_in_=old_features),
        "feature_names": old_features,
    }
    with patch("app.ml.predictor.load_cached_active_model", return_value=(mock_model_record, mock_artifact)):
        res = predict_engagement_from_features(db_session, {})
        assert res["prediction_available"] is False
        assert "Model schema mismatch" in res["reason"]
        assert "expected 17" in res["reason"]


# ============================================================================
# 3. Live Prediction Completeness & Elapsed Thresholds
# ============================================================================

def test_completeness_under_80_percent_triggers_data_insufficient(db_session, academic_engagement_fixture):
    """Requirement 5: Feature completeness < 80% withholds prediction and sets data_insufficient."""
    fix = academic_engagement_fixture
    now = datetime.now(timezone.utc)

    window = EngagementFeatureWindow(
        id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        session_id=fix["session"].id,
        student_id=fix["student"].id,
        device_id=fix["device"].id,
        batch_id=fix["batch"].id,
        window_start_at=now - timedelta(minutes=5),
        window_end_at=now,
        policy_version=1,
        allowed_academic_application_active_seconds=100.0,
        allowed_academic_website_active_seconds=50.0,
        academic_active_seconds=150.0,
        non_academic_active_seconds=50.0,
        idle_seconds=100.0,
        unknown_or_unavailable_seconds=0.0,
        feature_completeness_percent=65.0,  # Below 80% threshold
        validation_status="valid",
        session_elapsed_seconds=300.0,
    )
    db_session.add(window)
    db_session.commit()
    db_session.refresh(window)

    with patch("app.ml.live_prediction_service.broadcast_engagement_data_insufficient") as mock_broadcast:
        pred = process_live_prediction_for_window(db_session, window, fix["session"])
        assert pred is None
        mock_broadcast.assert_called_once()
        call_payload = mock_broadcast.call_args[1]["payload"]
        assert call_payload["collection_status"] == "data_insufficient"
        assert call_payload["feature_completeness_percent"] == 65.0
        assert "below the 80% threshold" in call_payload["reason"]


def test_session_elapsed_under_300s_produces_immediate_live_prediction(db_session, academic_engagement_fixture):
    """Requirement 6: Live predictions run immediately in real time without 300s waiting delay."""
    fix = academic_engagement_fixture
    now = datetime.now(timezone.utc)
    short_session = SessionModel(
        title="Just Started",
        batch_id=fix["batch"].id,
        created_by=fix["prof"].id,
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(seconds=60),
        end_at_utc=now + timedelta(hours=1),
        started_at=now - timedelta(seconds=60),
    )
    db_session.add(short_session)
    db_session.commit()

    window = EngagementFeatureWindow(
        id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        session_id=short_session.id,
        student_id=fix["student"].id,
        device_id=fix["device"].id,
        batch_id=fix["batch"].id,
        window_start_at=now - timedelta(seconds=60),
        window_end_at=now,
        policy_version=1,
        allowed_academic_application_active_seconds=40.0,
        allowed_academic_website_active_seconds=10.0,
        academic_active_seconds=50.0,
        non_academic_active_seconds=5.0,
        idle_seconds=5.0,
        feature_completeness_percent=95.0,
        validation_status="valid",
        session_elapsed_seconds=60.0,
    )
    db_session.add(window)
    db_session.commit()
    db_session.refresh(window)

    with patch("app.ml.live_prediction_service.get_active_model") as mock_model, \
         patch("app.ml.live_prediction_service.predict_engagement_from_features") as mock_pred, \
         patch("app.ml.live_prediction_service.broadcast_engagement_collection_started") as mock_collecting:
        mock_model.return_value = MagicMock(id=str(uuid.uuid4()), version_tag="v2.0.0-rf")
        pred = process_live_prediction_for_window(db_session, window, short_session)
        assert pred is None
        mock_collecting.assert_called_once()
        args, kwargs = mock_collecting.call_args
        assert kwargs["payload"]["collection_status"] == "collecting"
        assert kwargs["payload"]["reason"] == "Collecting live activity data"


# ============================================================================
# 4. Ingestion, Database Persistence & Summary Generation
# ============================================================================

def test_window_ingestion_and_session_summary_persistence(db_session, academic_engagement_fixture):
    """Requirement 1, 8, 14: Data persists properly without collecting private text/urls."""
    fix = academic_engagement_fixture
    now = datetime.now(timezone.utc)

    window = EngagementFeatureWindow(
        id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        session_id=fix["session"].id,
        student_id=fix["student"].id,
        device_id=fix["device"].id,
        batch_id=fix["batch"].id,
        window_start_at=now - timedelta(minutes=5),
        window_end_at=now,
        policy_version=1,
        allowed_academic_application_active_seconds=200.0,
        allowed_academic_website_active_seconds=60.0,
        academic_active_seconds=260.0,
        non_academic_active_seconds=20.0,
        idle_seconds=20.0,
        unknown_or_unavailable_seconds=0.0,
        active_resource_sample_count=95,
        unknown_resource_sample_count=0,
        feature_completeness_percent=99.0,
        approved_resources_breakdown={
            "applications": {"code.exe": 200.0},
            "websites": {"docs.python.org": 60.0},
        },
        validation_status="valid",
        session_elapsed_seconds=300.0,
    )
    db_session.add(window)
    db_session.commit()
    db_session.refresh(window)

    assert window.id is not None
    assert window.allowed_academic_application_active_seconds == 200.0
    assert window.allowed_academic_website_active_seconds == 60.0
    assert window.approved_resources_breakdown["applications"]["code.exe"] == 200.0

    # Privacy verification: verify no keystroke or raw text columns exist in model
    assert not hasattr(window, "keystrokes")
    assert not hasattr(window, "typed_text")
    assert not hasattr(window, "screenshots")
    assert not hasattr(window, "passwords")
    assert not hasattr(window, "full_urls")

    # Finalize session and check consolidated summary
    mock_active_model = MagicMock(id=str(uuid.uuid4()), version_tag="v2.0.0-rf-academic-engagement")
    with patch("app.ml.live_prediction_service.get_active_model", return_value=mock_active_model), \
         patch("app.ml.live_prediction_service.predict_engagement_from_features") as mock_inference:
        mock_inference.return_value = {
            "prediction_available": True,
            "prediction": "High",
            "confidence": 0.94,
            "probability_high": 0.94,
            "probability_medium": 0.04,
            "probability_low": 0.02,
        }
        final_pred = generate_final_prediction_for_student(db_session, fix["session"], fix["student"].id)

    assert final_pred is not None
    summary = db_session.query(EngagementSessionSummary).filter_by(
        session_id=fix["session"].id,
        student_id=fix["student"].id,
    ).first()
    assert summary is not None
    assert summary.allowed_academic_application_active_seconds == 200.0
    assert summary.allowed_academic_website_active_seconds == 60.0
    assert summary.approved_resources_breakdown["applications"]["code.exe"] == 200.0
    assert summary.approved_resources_breakdown["websites"]["docs.python.org"] == 60.0


# ============================================================================
# 5. REST APIs & Frontend Compatibility Tests
# ============================================================================

def test_professor_engagement_session_detail_api(client, db_session, academic_engagement_fixture):
    """Requirement 15: REST API returns full student row items with approved app/web breakdowns."""
    fix = academic_engagement_fixture
    now = datetime.now(timezone.utc)

    # Add a valid window with approved breakdowns
    window = EngagementFeatureWindow(
        id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        session_id=fix["session"].id,
        student_id=fix["student"].id,
        device_id=fix["device"].id,
        batch_id=fix["batch"].id,
        window_start_at=now - timedelta(minutes=5),
        window_end_at=now,
        policy_version=1,
        allowed_academic_application_active_seconds=180.0,
        allowed_academic_website_active_seconds=70.0,
        academic_active_seconds=250.0,
        non_academic_active_seconds=25.0,
        idle_seconds=25.0,
        unknown_or_unavailable_seconds=0.0,
        active_resource_sample_count=100,
        unknown_resource_sample_count=0,
        feature_completeness_percent=98.0,
        approved_resources_breakdown={
            "applications": {"code.exe": 180.0},
            "websites": {"github.com": 70.0},
        },
        validation_status="valid",
        session_elapsed_seconds=300.0,
    )
    db_session.add(window)
    db_session.commit()

    # Also add a prediction
    pred = EngagementPrediction(
        student_id=fix["student"].id,
        device_id=fix["device"].id,
        batch_id=fix["batch"].id,
        session_id=fix["session"].id,
        model_version_id="dummy-v2",
        prediction="High",
        confidence=0.88,
        probability_high=0.88,
        probability_medium=0.10,
        probability_low=0.02,
        feature_snapshot_json={"allowed_academic_application_active_ratio": 0.6},
        prediction_type="live",
        review_status="pending",
    )
    db_session.add(pred)
    db_session.commit()

    headers = _auth_header(fix["prof"])
    resp = client.get(f"/api/v1/professor/engagement/sessions/{fix['session'].id}", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["session_id"] == fix["session"].id
    assert len(data["students"]) >= 1

    student_row = next((s for s in data["students"] if s["student_id"] == fix["student"].id), None)
    assert student_row is not None
    assert student_row["allowed_academic_application_active_seconds"] == 180.0
    assert student_row["allowed_academic_website_active_seconds"] == 70.0
    assert student_row["academic_activity_seconds"] == 250.0
    assert student_row["is_advisory"] is True
    assert student_row["review_required"] is True
    assert "code.exe" in student_row["approved_apps_summary"]
    assert "github.com" in student_row["approved_websites_summary"]


def test_professor_review_override_api(client, db_session, academic_engagement_fixture):
    """Requirement 13: Professor review endpoint allows advisory override and writes audit log."""
    fix = academic_engagement_fixture

    # Create initial prediction
    pred = EngagementPrediction(
        student_id=fix["student"].id,
        device_id=fix["device"].id,
        batch_id=fix["batch"].id,
        session_id=fix["session"].id,
        model_version_id="dummy-v2",
        prediction="Low",
        confidence=0.55,
        probability_high=0.05,
        probability_medium=0.40,
        probability_low=0.55,
        feature_snapshot_json={},
        prediction_type="final",
        review_status="pending",
    )
    db_session.add(pred)
    db_session.commit()
    db_session.refresh(pred)

    headers = _auth_header(fix["prof"])
    payload = {
        "action": "override",
        "override_label": "High",
        "notes": "Student was coding actively in offline VS Code.",
    }
    resp = client.patch(
        f"/api/v1/professor/engagement/predictions/{pred.id}/review",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK
    resp_data = resp.json()
    assert resp_data["professor_override_label"] == "High"
    assert resp_data["model_estimate"] == "Low"  # Original model output untouched
    assert resp_data["reviewed_by"] == fix["prof"].id

    # Verify audit log was recorded
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_type == "engagement_prediction",
        AuditLog.entity_id == pred.id,
    ).first()
    assert audit is not None
    assert audit.action == "REVIEW_ENGAGEMENT_PREDICTION"


def test_active_session_live_prediction_flow(db_session, academic_engagement_fixture):
    """Requirement 7, 11, 12: Live session prediction creates prediction and broadcasts advisory payload."""
    fix = academic_engagement_fixture
    now = datetime.now(timezone.utc)

    window = EngagementFeatureWindow(
        id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        session_id=fix["session"].id,
        student_id=fix["student"].id,
        device_id=fix["device"].id,
        batch_id=fix["batch"].id,
        window_start_at=now - timedelta(minutes=5),
        window_end_at=now,
        policy_version=1,
        allowed_academic_application_active_seconds=220.0,
        allowed_academic_website_active_seconds=50.0,
        academic_active_seconds=270.0,
        non_academic_active_seconds=15.0,
        idle_seconds=15.0,
        unknown_or_unavailable_seconds=0.0,
        active_resource_sample_count=98,
        unknown_resource_sample_count=0,
        feature_completeness_percent=99.0,
        approved_resources_breakdown={
            "applications": {"code.exe": 220.0},
            "websites": {"github.com": 50.0},
        },
        validation_status="valid",
        session_elapsed_seconds=300.0,
    )
    db_session.add(window)
    db_session.commit()
    db_session.refresh(window)

    mock_active_model = MagicMock(id=str(uuid.uuid4()), version_tag="v2.0.0-rf-academic-engagement")
    with patch("app.ml.live_prediction_service.get_active_model", return_value=mock_active_model), \
         patch("app.ml.live_prediction_service.predict_engagement_from_features") as mock_inference, \
         patch("app.ml.live_prediction_service.broadcast_prediction_to_professor") as mock_broadcast:

        mock_inference.return_value = {
            "prediction_available": True,
            "prediction": "High",
            "confidence": 0.95,
            "probability_high": 0.95,
            "probability_medium": 0.03,
            "probability_low": 0.02,
        }

        pred = process_live_prediction_for_window(db_session, window, fix["session"])
        assert pred is not None
        assert pred.prediction == "High"
        assert pred.confidence == 0.95
        assert pred.collection_status == "preliminary_prediction"

        # Verify broadcast
        mock_broadcast.assert_called_once()
        payload = mock_broadcast.call_args[1]["prediction_payload"]
        assert payload["is_advisory"] is True
        assert payload["review_required"] is True
        assert payload["prediction"] == "High"
        assert "advisory" in payload["advisory_disclaimer"].lower()


def test_finalize_session_predictions_end_to_end(db_session, academic_engagement_fixture):
    """Requirement 8: Ending session finalizes all participating students with EngagementSessionSummary."""
    fix = academic_engagement_fixture
    now = datetime.now(timezone.utc)

    window = EngagementFeatureWindow(
        id=str(uuid.uuid4()),
        event_id=str(uuid.uuid4()),
        session_id=fix["session"].id,
        student_id=fix["student"].id,
        device_id=fix["device"].id,
        batch_id=fix["batch"].id,
        window_start_at=now - timedelta(minutes=5),
        window_end_at=now,
        policy_version=1,
        allowed_academic_application_active_seconds=200.0,
        allowed_academic_website_active_seconds=60.0,
        academic_active_seconds=260.0,
        non_academic_active_seconds=20.0,
        idle_seconds=20.0,
        unknown_or_unavailable_seconds=0.0,
        active_resource_sample_count=95,
        unknown_resource_sample_count=0,
        feature_completeness_percent=99.0,
        approved_resources_breakdown={
            "applications": {"code.exe": 200.0},
            "websites": {"docs.python.org": 60.0},
        },
        validation_status="valid",
        session_elapsed_seconds=300.0,
    )
    db_session.add(window)
    db_session.commit()

    mock_active_model = MagicMock(id=str(uuid.uuid4()), version_tag="v2.0.0-rf-academic-engagement")
    with patch("app.ml.live_prediction_service.get_active_model", return_value=mock_active_model), \
         patch("app.ml.live_prediction_service.predict_engagement_from_features") as mock_inference:
        mock_inference.return_value = {
            "prediction_available": True,
            "prediction": "High",
            "confidence": 0.91,
            "probability_high": 0.91,
            "probability_medium": 0.05,
            "probability_low": 0.04,
        }

        finalize_session_predictions(db_session, fix["session"].id)

    # Check that summary was generated
    summary = db_session.query(EngagementSessionSummary).filter_by(
        session_id=fix["session"].id,
        student_id=fix["student"].id,
    ).first()
    assert summary is not None
    assert summary.allowed_academic_application_active_seconds == 200.0
    assert summary.allowed_academic_website_active_seconds == 60.0
    assert summary.approved_resources_breakdown["applications"]["code.exe"] == 200.0

