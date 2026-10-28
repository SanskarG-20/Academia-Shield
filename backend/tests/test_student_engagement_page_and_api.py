"""
Comprehensive Test Suite for Professor-Only Student Engagement Page and APIs.

Covers all requirements:
1. Student cannot call engagement APIs (403 Forbidden).
2. Professor sees only batches they own.
3. Professor sees only sessions from selected batch.
4. Another professor cannot access a session's engagement data (403 Forbidden).
5. Live prediction WebSocket updates correct student channel and payload.
6. Completed session shows saved final data from PostgreSQL (engagement_session_summaries & final predictions).
7. Review override creates audit record without mutating original model prediction.
8. Historical data remains available after session ends.
"""

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
def engagement_fixture(db_session):
    # Create professors
    prof_a = _create_user(db_session, "prof_a@example.edu", role="professor", full_name="Professor A")
    prof_b = _create_user(db_session, "prof_b@example.edu", role="professor", full_name="Professor B")
    student = _create_user(db_session, "student_1@example.edu", role="student", full_name="Student One")

    # Create batches
    batch_a = Batch(
        name="CS101 - Prof A",
        batch_code="CS101A",
        professor_id=prof_a.id,
    )
    batch_b = Batch(
        name="CS102 - Prof B",
        batch_code="CS102B",
        professor_id=prof_b.id,
    )
    db_session.add_all([batch_a, batch_b])
    db_session.commit()
    db_session.refresh(batch_a)
    db_session.refresh(batch_b)

    # Enroll student in batch A
    bm = BatchMember(batch_id=batch_a.id, student_id=student.id, status="active")
    db_session.add(bm)
    db_session.commit()

    now = datetime.now(timezone.utc)
    # Create active session for Batch A
    session_active = SessionModel(
        title="Live Lecture 1",
        batch_id=batch_a.id,
        created_by=prof_a.id,
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=20),
        end_at_utc=now + timedelta(minutes=40),
        started_at=now - timedelta(minutes=20),
    )
    # Create completed session for Batch A
    session_ended = SessionModel(
        title="Completed Lecture 0",
        batch_id=batch_a.id,
        created_by=prof_a.id,
        status="ended",
        is_active=False,
        start_at_utc=now - timedelta(hours=2),
        end_at_utc=now - timedelta(hours=1),
        started_at=now - timedelta(hours=2),
        ended_at=now - timedelta(hours=1),
    )
    # Create session for Batch B
    session_b = SessionModel(
        title="Prof B Session",
        batch_id=batch_b.id,
        created_by=prof_b.id,
        status="active",
        is_active=True,
        start_at_utc=now - timedelta(minutes=10),
        end_at_utc=now + timedelta(minutes=50),
        started_at=now - timedelta(minutes=10),
    )
    db_session.add_all([session_active, session_ended, session_b])
    db_session.commit()
    db_session.refresh(session_active)
    db_session.refresh(session_ended)
    db_session.refresh(session_b)

    # Participant in active session
    part_active = SessionParticipant(
        session_id=session_active.id,
        student_id=student.id,
        status="joined",
    )
    # Participant in ended session
    part_ended = SessionParticipant(
        session_id=session_ended.id,
        student_id=student.id,
        status="left",
    )
    db_session.add_all([part_active, part_ended])
    db_session.commit()

    return {
        "prof_a": prof_a,
        "prof_b": prof_b,
        "student": student,
        "batch_a": batch_a,
        "batch_b": batch_b,
        "session_active": session_active,
        "session_ended": session_ended,
        "session_b": session_b,
    }


def test_student_cannot_call_engagement_apis(client, engagement_fixture):
    """Students must receive 403 Forbidden on all engagement endpoints."""
    headers = _auth_header(engagement_fixture["student"])
    sess_id = engagement_fixture["session_active"].id
    batch_id = engagement_fixture["batch_a"].id

    r1 = client.get("/api/v1/professor/engagement/batches", headers=headers)
    assert r1.status_code == status.HTTP_403_FORBIDDEN

    r2 = client.get(f"/api/v1/professor/engagement/batches/{batch_id}/sessions", headers=headers)
    assert r2.status_code == status.HTTP_403_FORBIDDEN

    r3 = client.get(f"/api/v1/professor/engagement/sessions/{sess_id}", headers=headers)
    assert r3.status_code == status.HTTP_403_FORBIDDEN

    r4 = client.get(f"/api/v1/professor/engagement/sessions/{sess_id}/history", headers=headers)
    assert r4.status_code == status.HTTP_403_FORBIDDEN

    r5 = client.patch(
        "/api/v1/professor/engagement/predictions/dummy-id/review",
        json={"action": "confirm"},
        headers=headers,
    )
    assert r5.status_code == status.HTTP_403_FORBIDDEN


def test_professor_sees_only_owned_batches(client, engagement_fixture):
    """Professor A sees only batches they own; Professor B sees only theirs."""
    headers_a = _auth_header(engagement_fixture["prof_a"])
    headers_b = _auth_header(engagement_fixture["prof_b"])

    res_a = client.get("/api/v1/professor/engagement/batches", headers=headers_a)
    assert res_a.status_code == status.HTTP_200_OK
    batches_a = res_a.json()
    assert len(batches_a) == 1
    assert batches_a[0]["id"] == engagement_fixture["batch_a"].id
    assert batches_a[0]["name"] == "CS101 - Prof A"

    res_b = client.get("/api/v1/professor/engagement/batches", headers=headers_b)
    assert res_b.status_code == status.HTTP_200_OK
    batches_b = res_b.json()
    assert len(batches_b) == 1
    assert batches_b[0]["id"] == engagement_fixture["batch_b"].id
    assert batches_b[0]["name"] == "CS102 - Prof B"


def test_professor_sees_only_sessions_from_selected_batch(client, engagement_fixture):
    """Professor A gets sessions belonging only to Batch A."""
    headers_a = _auth_header(engagement_fixture["prof_a"])
    batch_a_id = engagement_fixture["batch_a"].id

    res = client.get(f"/api/v1/professor/engagement/batches/{batch_a_id}/sessions", headers=headers_a)
    assert res.status_code == status.HTTP_200_OK
    sessions = res.json()
    # Batch A has 2 sessions: live and ended
    assert len(sessions) == 2
    titles = [s["title"] for s in sessions]
    assert "Live Lecture 1" in titles
    assert "Completed Lecture 0" in titles

    # Status filter: Active
    res_active = client.get(
        f"/api/v1/professor/engagement/batches/{batch_a_id}/sessions?status=Active",
        headers=headers_a,
    )
    assert res_active.status_code == status.HTTP_200_OK
    active_sessions = res_active.json()
    assert len(active_sessions) == 1
    assert active_sessions[0]["title"] == "Live Lecture 1"

    # Status filter: Completed
    res_comp = client.get(
        f"/api/v1/professor/engagement/batches/{batch_a_id}/sessions?status=Completed",
        headers=headers_a,
    )
    assert res_comp.status_code == status.HTTP_200_OK
    comp_sessions = res_comp.json()
    assert len(comp_sessions) == 1
    assert comp_sessions[0]["title"] == "Completed Lecture 0"


def test_another_professor_cannot_access_session_engagement(client, engagement_fixture):
    """Professor B cannot access Professor A's session or batch sessions."""
    headers_b = _auth_header(engagement_fixture["prof_b"])
    session_a_id = engagement_fixture["session_active"].id
    batch_a_id = engagement_fixture["batch_a"].id

    # Trying to get Batch A's sessions
    r1 = client.get(f"/api/v1/professor/engagement/batches/{batch_a_id}/sessions", headers=headers_b)
    assert r1.status_code == status.HTTP_403_FORBIDDEN

    # Trying to get Session A's engagement detail
    r2 = client.get(f"/api/v1/professor/engagement/sessions/{session_a_id}", headers=headers_b)
    assert r2.status_code == status.HTTP_403_FORBIDDEN


def test_live_prediction_broadcast_and_socket_room(client, db_session, engagement_fixture):
    """Live prediction triggers broadcast to professor channel with safe metrics and prediction."""
    prof_a = engagement_fixture["prof_a"]
    student = engagement_fixture["student"]
    session = engagement_fixture["session_active"]

    from app.core.sockets import broadcast_engagement_prediction
    from app.ml.live_prediction_service import broadcast_prediction_to_professor

    with patch("app.ml.live_prediction_service.broadcast_engagement_prediction") as mock_pred_broad, \
         patch("app.ml.live_prediction_service.broadcast_engagement_features") as mock_feat_broad:

        pred_payload = {
            "prediction": "High",
            "confidence": 0.88,
            "probability_high": 0.88,
            "probability_medium": 0.10,
            "probability_low": 0.02,
            "feature_snapshot_json": {
                "academic_active_seconds": 250.0,
                "idle_seconds": 20.0,
                "application_switch_count": 2,
            },
        }

        broadcast_prediction_to_professor(
            session=session,
            student_id=student.id,
            window_id="win-123",
            prediction_payload=pred_payload,
        )

        assert mock_pred_broad.called
        call_args = mock_pred_broad.call_args
        payload_sent = call_args[0][0]
        prof_sent = call_args[1]["professor_id"]

        assert prof_sent == prof_a.id
        assert payload_sent["session_id"] == session.id
        assert payload_sent["student_id"] == student.id
        assert payload_sent["safe_metrics"]["academic_active_seconds"] == 250.0
        assert payload_sent["safe_metrics"]["idle_seconds"] == 20.0


def test_completed_session_shows_saved_final_data(client, db_session, engagement_fixture):
    """Completed session returns saved final totals from engagement_session_summaries and predictions."""
    prof_a = engagement_fixture["prof_a"]
    student = engagement_fixture["student"]
    sess_ended = engagement_fixture["session_ended"]
    batch_a = engagement_fixture["batch_a"]

    # Create active model
    model = MLModelVersion(
        version_tag="v1.0.0-test",
        algorithm="RandomForestClassifier",
        status="approved",
        artifact_path="/tmp/model.pkl",
        trained_by=prof_a.id,
    )
    db_session.add(model)
    db_session.commit()
    db_session.refresh(model)

    # Save final prediction
    final_pred = EngagementPrediction(
        model_version_id=model.id,
        student_id=student.id,
        device_id="DEV-TEST",
        batch_id=batch_a.id,
        session_id=sess_ended.id,
        prediction="Medium",
        confidence=0.76,
        probability_high=0.15,
        probability_medium=0.76,
        probability_low=0.09,
        feature_snapshot_json={"academic_active_seconds": 2520.0, "idle_seconds": 300.0},
        prediction_type="final",
        review_status="pending",
        generated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(final_pred)
    db_session.commit()
    db_session.refresh(final_pred)

    # Save final session summary
    summary = EngagementSessionSummary(
        session_id=sess_ended.id,
        student_id=student.id,
        batch_id=batch_a.id,
        device_id="DEV-TEST",
        academic_active_seconds=2520.0,
        non_academic_active_seconds=120.0,
        idle_seconds=300.0,
        application_switch_count=4,
        unauthorized_application_attempt_count=1,
        blocked_website_attempt_count=2,
        policy_violation_count=3,
        session_elapsed_seconds=3600.0,
        final_prediction_id=final_pred.id,
    )
    db_session.add(summary)
    db_session.commit()

    headers = _auth_header(prof_a)
    res = client.get(f"/api/v1/professor/engagement/sessions/{sess_ended.id}", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()

    assert data["session_id"] == sess_ended.id
    assert data["is_active"] is False
    assert len(data["students"]) == 1

    stud = data["students"][0]
    assert stud["student_id"] == student.id
    assert stud["academic_activity_seconds"] == 2520.0
    assert stud["idle_seconds"] == 300.0
    assert stud["blocked_website_attempt_count"] == 2
    assert stud["policy_violation_count"] == 3
    assert stud["engagement_estimate"] == "Medium"
    assert stud["confidence"] == 0.76
    assert stud["prediction_type"] == "Final"
    assert stud["prediction_id"] == final_pred.id


def test_historical_session_engagement_detail_without_summary_fallback(client, db_session, engagement_fixture):
    """An ended session with participant but no summary table record aggregates without 500 error."""
    prof_a = engagement_fixture["prof_a"]
    sess_ended = engagement_fixture["session_ended"]
    student = engagement_fixture["student"]

    headers = _auth_header(prof_a)
    res = client.get(f"/api/v1/professor/engagement/sessions/{sess_ended.id}", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["session_id"] == sess_ended.id
    assert data["is_active"] is False
    assert len(data["students"]) == 1
    stud = data["students"][0]
    assert stud["student_id"] == student.id
    assert stud["academic_activity_seconds"] == 0.0
    assert stud["prediction_available"] is False
    assert stud["prediction_reason"] == "Historical session has no recorded prediction"


def test_review_override_creates_audit_record(client, db_session, engagement_fixture):
    """Professor review/override creates AuditLog, updates review status, and keeps model estimate intact."""
    prof_a = engagement_fixture["prof_a"]
    student = engagement_fixture["student"]
    session = engagement_fixture["session_ended"]
    batch = engagement_fixture["batch_a"]

    pred = EngagementPrediction(
        student_id=student.id,
        device_id="DEV-TEST",
        batch_id=batch.id,
        session_id=session.id,
        prediction="Low",
        confidence=0.65,
        probability_high=0.05,
        probability_medium=0.30,
        probability_low=0.65,
        feature_snapshot_json={},
        prediction_type="final",
        review_status="pending",
    )
    db_session.add(pred)
    db_session.commit()
    db_session.refresh(pred)

    headers = _auth_header(prof_a)

    # Perform override to High
    patch_res = client.patch(
        f"/api/v1/professor/engagement/predictions/{pred.id}/review",
        json={
            "action": "override",
            "override_label": "High",
            "notes": "Student had network trouble but participated actively verbally.",
        },
        headers=headers,
    )
    assert patch_res.status_code == status.HTTP_200_OK
    body = patch_res.json()

    assert body["prediction_id"] == pred.id
    assert body["model_estimate"] == "Low"  # Original model output NOT overwritten!
    assert body["professor_review_status"] == "overridden"
    assert body["professor_override_label"] == "High"
    assert body["reviewed_by"] == prof_a.id

    # Verify AuditLog created in database
    audit = db_session.query(AuditLog).filter(
        AuditLog.entity_type == "engagement_prediction",
        AuditLog.entity_id == pred.id,
    ).first()
    assert audit is not None
    assert audit.action == "REVIEW_ENGAGEMENT_PREDICTION"
    assert audit.actor_user_id == prof_a.id
    assert audit.metadata_json["override_label"] == "High"
    assert audit.metadata_json["model_estimate"] == "Low"

    # Verify model prediction in DB remains "Low" while override is "High"
    db_session.refresh(pred)
    assert pred.prediction == "Low"
    assert pred.professor_override_label == "High"
    assert pred.review_status == "overridden"


def test_historical_data_remains_available_after_session_ends(client, db_session, engagement_fixture):
    """Ending a session and fetching historical engagement preserves permanently stored records."""
    prof_a = engagement_fixture["prof_a"]
    sess_ended = engagement_fixture["session_ended"]
    student = engagement_fixture["student"]
    batch_a = engagement_fixture["batch_a"]

    # Historical prediction
    h_pred = EngagementPrediction(
        student_id=student.id,
        device_id="DEV-TEST",
        batch_id=batch_a.id,
        session_id=sess_ended.id,
        prediction="High",
        confidence=0.92,
        probability_high=0.92,
        probability_medium=0.06,
        probability_low=0.02,
        feature_snapshot_json={},
        prediction_type="final",
        review_status="confirmed",
    )
    db_session.add(h_pred)
    db_session.commit()

    headers = _auth_header(prof_a)
    res = client.get(f"/api/v1/professor/engagement/sessions/{sess_ended.id}/history", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    history = res.json()
    assert len(history) >= 1
    assert history[0]["prediction"] == "High"
    assert history[0]["session_id"] == sess_ended.id
