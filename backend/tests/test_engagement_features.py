"""
Automated Test Suite for Privacy-Minimized Student Engagement Telemetry,
Feature Window Ingestion, Live Aggregation, and Professor Labelling.
Verifies all 8 core requirements and strict authorization constraints.
"""

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import status
from unittest.mock import patch

from app.models.user import User
from app.models.device import AgentDevice
from app.models.batch import Batch, BatchMember
from app.models.session import SessionModel, SessionParticipant
from app.models.engagement import EngagementFeatureWindow, SessionEngagementLabel
from app.core.security import hash_password, create_access_token


def _create_user(db_session, email, role="student", full_name=None):
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        role=role,
        full_name=full_name or email.split("@")[0].capitalize(),
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_header(user):
    token = create_access_token(data={"sub": user.id, "email": user.email, "role": user.role, "type": "access"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_setup(db_session):
    """Setup professor, batch, students, enrolled devices, and active session."""
    professor = _create_user(db_session, "prof_smith@example.edu", role="professor", full_name="Prof. Smith")
    other_prof = _create_user(db_session, "prof_jones@example.edu", role="professor", full_name="Prof. Jones")
    student1 = _create_user(db_session, "alice@example.edu", role="student", full_name="Alice Student")
    student2 = _create_user(db_session, "bob@example.edu", role="student", full_name="Bob Student")
    unassigned_student = _create_user(db_session, "charlie@example.edu", role="student", full_name="Charlie Unassigned")

    # Devices
    device1 = AgentDevice(
        user_id=student1.id,
        device_name="Alice Laptop",
        device_identifier="DEV-ALICE-WIN11",
        public_key="ed25519_pub_key_alice_test_12345678",
        platform="windows",
        agent_version="2.3.0",
        is_active=True
    )
    device2 = AgentDevice(
        user_id=student2.id,
        device_name="Bob Laptop",
        device_identifier="DEV-BOB-WIN11",
        public_key="ed25519_pub_key_bob_test_1234567890",
        platform="windows",
        agent_version="2.3.0",
        is_active=True
    )
    db_session.add_all([device1, device2])
    db_session.commit()
    db_session.refresh(device1)
    db_session.refresh(device2)

    # Batch
    batch = Batch(
        professor_id=professor.id,
        name="CS101 Intro to Programming",
        is_active=True
    )
    db_session.add(batch)
    db_session.commit()
    db_session.refresh(batch)

    # Memberships
    bm1 = BatchMember(batch_id=batch.id, student_id=student1.id, status="active")
    bm2 = BatchMember(batch_id=batch.id, student_id=student2.id, status="active")
    db_session.add_all([bm1, bm2])
    db_session.commit()

    # Active Session
    now = datetime.now(timezone.utc)
    session = SessionModel(
        title="Lab 1: Python Basics",
        created_by=professor.id,
        batch_id=batch.id,
        status="active",
        is_active=True,
        policy_version=1,
        start_at_utc=now - timedelta(minutes=30),
        end_at_utc=now + timedelta(minutes=60),
        started_at=now - timedelta(minutes=30)
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    # Alice has joined session
    sp1 = SessionParticipant(session_id=session.id, student_id=student1.id, status="joined")
    db_session.add(sp1)
    db_session.commit()

    return {
        "professor": professor,
        "other_prof": other_prof,
        "student1": student1,
        "student2": student2,
        "unassigned_student": unassigned_student,
        "device1": device1,
        "device2": device2,
        "batch": batch,
        "session": session
    }


def test_feature_window_ingestion_valid(client, db_session, test_setup):
    """Test successful ingestion of a valid 5-minute engagement feature window."""
    s = test_setup
    now = datetime.now(timezone.utc)
    window_payload = {
        "event_id": str(uuid.uuid4()),
        "student_id": s["student1"].id,
        "device_id": s["device1"].id,
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=5)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 240.0,
        "non_academic_active_seconds": 30.0,
        "idle_seconds": 30.0,
        "application_switch_count": 4,
        "unauthorized_application_attempt_count": 1,
        "blocked_website_attempt_count": 2,
        "policy_violation_count": 3,
        "session_elapsed_seconds": 300.0
    }

    with patch("app.services.engagement_service.broadcast_engagement_features") as mock_ws:
        res = client.post(
            "/api/v1/agent/telemetry/engagement-windows",
            json=window_payload,
            headers=_auth_header(s["student1"])
        )
        assert res.status_code == status.HTTP_200_OK, res.text
        data = res.json()
        assert data["status"] == "accepted"
        assert data["event_id"] == window_payload["event_id"]
        assert data["id"] is not None

        # Verify broadcast was sent exclusively to owning professor
        mock_ws.assert_called_once()
        args, kwargs = mock_ws.call_args
        assert kwargs.get("professor_id") == s["professor"].id


def test_feature_window_idempotency(client, db_session, test_setup):
    """Duplicate window submissions with the same event_id must return duplicate status without error."""
    s = test_setup
    now = datetime.now(timezone.utc)
    ev_id = str(uuid.uuid4())
    window_payload = {
        "event_id": ev_id,
        "student_id": s["student1"].id,
        "device_id": s["device1"].id,
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=5)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 200.0,
        "non_academic_active_seconds": 50.0,
        "idle_seconds": 50.0,
        "application_switch_count": 2,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 300.0
    }

    res1 = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=window_payload,
        headers=_auth_header(s["student1"])
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "accepted"

    # Second submission with exact same event_id
    res2 = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=window_payload,
        headers=_auth_header(s["student1"])
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate"


def test_strict_rejection_rules(client, db_session, test_setup):
    """Test strict rejection rules on invalid devices, batches, sessions, or join status."""
    s = test_setup
    now = datetime.now(timezone.utc)

    # 1. Device does not belong to student
    bad_device_payload = {
        "event_id": str(uuid.uuid4()),
        "student_id": s["student1"].id,
        "device_id": s["device2"].id,  # Device 2 belongs to Bob!
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=5)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 250.0,
        "non_academic_active_seconds": 20.0,
        "idle_seconds": 30.0,
        "application_switch_count": 1,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 300.0
    }
    res = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=bad_device_payload,
        headers=_auth_header(s["student1"])
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # 2. Student not assigned to session batch
    unassigned_payload = {
        "event_id": str(uuid.uuid4()),
        "student_id": s["unassigned_student"].id,
        "device_id": s["device1"].id,
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=5)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 250.0,
        "non_academic_active_seconds": 20.0,
        "idle_seconds": 30.0,
        "application_switch_count": 1,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 300.0
    }
    res = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=unassigned_payload,
        headers=_auth_header(s["unassigned_student"])
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # 3. Student has not joined session
    # Bob is in batch and owns device2, but has NOT joined session
    bob_payload = {
        "event_id": str(uuid.uuid4()),
        "student_id": s["student2"].id,
        "device_id": s["device2"].id,
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=5)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 250.0,
        "non_academic_active_seconds": 20.0,
        "idle_seconds": 30.0,
        "application_switch_count": 1,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 300.0
    }
    res = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=bob_payload,
        headers=_auth_header(s["student2"])
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # 4. Session inactive or ended
    s["session"].status = "ended"
    s["session"].is_active = False
    db_session.commit()

    ended_payload = {
        "event_id": str(uuid.uuid4()),
        "student_id": s["student1"].id,
        "device_id": s["device1"].id,
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=5)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 250.0,
        "non_academic_active_seconds": 20.0,
        "idle_seconds": 30.0,
        "application_switch_count": 1,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 300.0
    }
    res = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=ended_payload,
        headers=_auth_header(s["student1"])
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST


def test_metrics_bounds_and_invalid_durations(client, db_session, test_setup):
    """Submissions exceeding window duration beyond tolerance must be recorded as invalid and excluded from live aggregation."""
    s = test_setup
    now = datetime.now(timezone.utc)

    # Window duration is 300s (5 minutes), but total durations = 400 + 100 + 100 = 600s
    invalid_payload = {
        "event_id": str(uuid.uuid4()),
        "student_id": s["student1"].id,
        "device_id": s["device1"].id,
        "batch_id": s["batch"].id,
        "session_id": s["session"].id,
        "window_start_at": (now - timedelta(minutes=5)).isoformat(),
        "window_end_at": now.isoformat(),
        "policy_version": 1,
        "academic_active_seconds": 400.0,
        "non_academic_active_seconds": 100.0,
        "idle_seconds": 100.0,
        "application_switch_count": 3,
        "unauthorized_application_attempt_count": 0,
        "blocked_website_attempt_count": 0,
        "policy_violation_count": 0,
        "session_elapsed_seconds": 300.0
    }

    res = client.post(
        "/api/v1/agent/telemetry/engagement-windows",
        json=invalid_payload,
        headers=_auth_header(s["student1"])
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "invalid"
    assert "exceeds window duration" in data["message"]

    # Verify it is recorded in DB with validation_status == "invalid"
    rec = db_session.query(EngagementFeatureWindow).filter(
        EngagementFeatureWindow.event_id == invalid_payload["event_id"]
    ).first()
    assert rec is not None
    assert rec.validation_status == "invalid"


def test_live_aggregation_and_safe_ratios(client, db_session, test_setup):
    """Test live engagement feature aggregation, rolling totals, safe ratios, and prediction_available: False."""
    s = test_setup
    now = datetime.now(timezone.utc)

    # Add 2 valid windows for Alice
    w1 = EngagementFeatureWindow(
        event_id=str(uuid.uuid4()),
        student_id=s["student1"].id,
        device_id=s["device1"].id,
        batch_id=s["batch"].id,
        session_id=s["session"].id,
        window_start_at=now - timedelta(minutes=10),
        window_end_at=now - timedelta(minutes=5),
        policy_version=1,
        academic_active_seconds=240.0,
        non_academic_active_seconds=30.0,
        idle_seconds=30.0,
        application_switch_count=3,
        unauthorized_application_attempt_count=1,
        blocked_website_attempt_count=0,
        policy_violation_count=1,
        session_elapsed_seconds=300.0,
        validation_status="valid"
    )
    w2 = EngagementFeatureWindow(
        event_id=str(uuid.uuid4()),
        student_id=s["student1"].id,
        device_id=s["device1"].id,
        batch_id=s["batch"].id,
        session_id=s["session"].id,
        window_start_at=now - timedelta(minutes=5),
        window_end_at=now,
        policy_version=1,
        academic_active_seconds=250.0,
        non_academic_active_seconds=20.0,
        idle_seconds=30.0,
        application_switch_count=2,
        unauthorized_application_attempt_count=0,
        blocked_website_attempt_count=1,
        policy_violation_count=1,
        session_elapsed_seconds=600.0,
        validation_status="valid"
    )
    db_session.add_all([w1, w2])
    db_session.commit()

    # Query GET /api/v1/professor/sessions/{session_id}/engagement/live
    res = client.get(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/live",
        headers=_auth_header(s["professor"])
    )
    assert res.status_code == status.HTTP_200_OK, res.text
    data = res.json()

    assert data["session_id"] == s["session"].id
    # Strict requirement: prediction_available must be False
    assert data["prediction_available"] is False

    alice_data = next((item for item in data["students"] if item["student_id"] == s["student1"].id), None)
    assert alice_data is not None
    assert alice_data["joined"] is True
    assert alice_data["window_count"] == 2
    assert alice_data["total_academic_seconds"] == 490.0
    assert alice_data["total_non_academic_seconds"] == 50.0
    assert alice_data["total_idle_seconds"] == 60.0
    assert alice_data["total_switches"] == 5
    assert alice_data["total_policy_violations"] == 2

    # Verify safe ratios:
    # academic_ratio: 490 / (490 + 50) = 490 / 540 = 0.907
    assert alice_data["academic_ratio"] == pytest.approx(0.907, rel=1e-2)
    # focus_stability_index: 1.0 / (1.0 + (5 / (540/60))) = 1.0 / (1.0 + (5/9)) = 1.0 / 1.555 = 0.643
    assert alice_data["focus_stability_index"] == pytest.approx(0.643, rel=1e-2)
    # violation_rate_per_hour: (2 / 600) * 3600 = 12.0
    assert alice_data["violation_rate_per_hour"] == 12.0


def test_professor_authorization_on_live_engagement(client, db_session, test_setup):
    """Only the session's creator professor or an admin can access live engagement features."""
    s = test_setup

    # Other professor should be forbidden
    res = client.get(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/live",
        headers=_auth_header(s["other_prof"])
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # Student should be forbidden
    res_st = client.get(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/live",
        headers=_auth_header(s["student1"])
    )
    assert res_st.status_code == status.HTTP_403_FORBIDDEN


def test_post_session_labelling_rules(client, db_session, test_setup):
    """Test post-session human labelling: only completed sessions can be labelled, only by creator."""
    s = test_setup

    # 1. Active session cannot be labelled
    res_active = client.post(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/label",
        json={"student_id": s["student1"].id, "label": "High", "notes": "Actively participated"},
        headers=_auth_header(s["professor"])
    )
    assert res_active.status_code == status.HTTP_400_BAD_REQUEST
    assert "only allowed for completed sessions" in res_active.text

    # 2. Complete the session
    s["session"].status = "ended"
    s["session"].is_active = False
    db_session.commit()

    # 3. Label with invalid label string
    res_invalid_label = client.post(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/label",
        json={"student_id": s["student1"].id, "label": "Outstanding", "notes": "Invalid label"},
        headers=_auth_header(s["professor"])
    )
    assert res_invalid_label.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY or res_invalid_label.status_code == status.HTTP_400_BAD_REQUEST

    # 4. Successful labelling by owning professor
    res_valid = client.post(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/label",
        json={"student_id": s["student1"].id, "label": "High", "notes": "Excellent sustained focus"},
        headers=_auth_header(s["professor"])
    )
    assert res_valid.status_code == status.HTTP_200_OK, res_valid.text
    data = res_valid.json()
    assert data["label"] == "High"
    assert data["student_id"] == s["student1"].id
    assert data["professor_id"] == s["professor"].id

    # 5. Update the label
    res_update = client.post(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/label",
        json={"student_id": s["student1"].id, "label": "Medium", "notes": "Revised after review"},
        headers=_auth_header(s["professor"])
    )
    assert res_update.status_code == status.HTTP_200_OK
    assert res_update.json()["label"] == "Medium"

    # 6. Verify in GET labels
    res_get = client.get(
        f"/api/v1/professor/sessions/{s['session'].id}/engagement/labels",
        headers=_auth_header(s["professor"])
    )
    assert res_get.status_code == 200
    labels = res_get.json()
    assert len(labels) == 1
    assert labels[0]["label"] == "Medium"
