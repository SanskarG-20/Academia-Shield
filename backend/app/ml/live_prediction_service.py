"""Orchestration service for live engagement prediction and lifecycle hooks.

Responsibilities:
1. Process incoming valid feature windows from the agent telemetry pipeline.
2. Check 5-minute guard (elapsed seconds < 300s or < 1 valid window -> waiting state).
3. Compute canonical 14 features using rolling windows.
4. Execute inference with the approved ML model via `predictor.py`.
5. Persist prediction immutably in `engagement_predictions`.
6. Broadcast advisory prediction update exclusively to the owning professor.
7. Finalize predictions on session completion.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.engagement import (
    EngagementFeatureWindow,
    EngagementPrediction,
    MLModelVersion,
    EngagementSessionSummary,
)
from app.models.session import SessionModel
from app.models.user import User
from app.ml.features import compute_feature_vector
from app.ml.predictor import predict_engagement_from_features
from app.ml.model_registry import get_active_model
from app.core.sockets import (
    broadcast_engagement_features,
    broadcast_engagement_prediction,
    broadcast_engagement_collection_started,
    broadcast_engagement_data_insufficient,
    broadcast_engagement_prediction_finalized,
)

logger = logging.getLogger(__name__)


def process_live_prediction_for_window(
    db: Session,
    window: EngagementFeatureWindow,
    session: SessionModel,
) -> Optional[EngagementPrediction]:
    """
    Executes live engagement prediction following a newly saved valid feature window.
    Strictly follows guidelines:
    - If window is not valid, broadcast data_insufficient and return.
    - If feature completeness < 80%, broadcast data_insufficient and return.
    - If active model is missing, return waiting/unavailable.
    - If session_elapsed_seconds < 300s, broadcast collection_started.
    - Save prediction record to engagement_predictions with collection_status.
    - Broadcast prediction event to professor with advisory disclaimer.
    """
    if window.validation_status != "valid":
        broadcast_engagement_data_insufficient(
            payload={
                "session_id": session.id,
                "student_id": window.student_id,
                "collection_status": "data_insufficient",
                "reason": window.validation_error or "More valid activity data is required for an estimate.",
                "feature_completeness_percent": getattr(window, "feature_completeness_percent", 0.0),
                "last_telemetry_at": window.window_end_at.isoformat() if window.window_end_at else None,
            },
            professor_id=session.created_by,
        )
        return None

    completeness = getattr(window, "feature_completeness_percent", 100.0)
    if completeness is None:
        completeness = 100.0
    if completeness < 80.0:
        reason = f"Data completeness is {completeness:.1f}%, which is below the 80% threshold. More valid activity data is required for an estimate."
        broadcast_engagement_data_insufficient(
            payload={
                "session_id": session.id,
                "student_id": window.student_id,
                "collection_status": "data_insufficient",
                "reason": reason,
                "feature_completeness_percent": completeness,
                "last_telemetry_at": window.window_end_at.isoformat() if window.window_end_at else None,
            },
            professor_id=session.created_by,
        )
        return None

    # Do not show a prediction until at least one complete valid 5-minute feature window is received
    elapsed = getattr(window, "session_elapsed_seconds", 0.0) or 0.0
    if elapsed < 300.0:
        broadcast_engagement_collection_started(
            payload={
                "session_id": session.id,
                "student_id": window.student_id,
                "collection_status": "collecting",
                "reason": "Collecting live activity data",
                "valid_windows_received": 1,
                "session_elapsed_seconds": elapsed,
                "last_telemetry_at": window.window_end_at.isoformat() if window.window_end_at else None,
            },
            professor_id=session.created_by,
        )
        return None

    active_model = get_active_model(db)
    features = compute_feature_vector(window)

    if not active_model:
        reason = "No approved ML model is currently active"
        broadcast_prediction_to_professor(
            session=session,
            student_id=window.student_id,
            window_id=window.id,
            prediction_payload={
                "prediction_available": False,
                "collection_status": "data_insufficient",
                "reason": reason,
                "model_version_id": None,
                "model_version_tag": None,
                "prediction": None,
                "confidence": None,
                "probability_high": None,
                "probability_medium": None,
                "probability_low": None,
                "prediction_type": "live",
                "is_advisory": True,
                "review_required": True,
                "feature_snapshot_json": features,
            },
            window=window,
        )
        return None

    # Run inference
    inference_result = predict_engagement_from_features(db, features)

    if not inference_result.get("prediction_available"):
        broadcast_prediction_to_professor(
            session=session,
            student_id=window.student_id,
            window_id=window.id,
            prediction_payload={
                "prediction_available": False,
                "collection_status": "data_insufficient",
                "reason": inference_result.get("reason", "Prediction unavailable"),
                "model_version_id": active_model.id,
                "model_version_tag": active_model.version_tag,
                "prediction": None,
                "confidence": None,
                "probability_high": None,
                "probability_medium": None,
                "probability_low": None,
                "prediction_type": "live",
                "is_advisory": True,
                "review_required": True,
                "feature_snapshot_json": features,
            },
            window=window,
        )
        return None

    # Idempotent check: if prediction for this (model_version_id, feature_window_id) exists, return it
    existing = db.execute(
        select(EngagementPrediction).where(
            EngagementPrediction.model_version_id == active_model.id,
            EngagementPrediction.feature_window_id == window.id,
        )
    ).scalars().first()

    if existing:
        pred_record = existing
    else:
        now = datetime.now(timezone.utc)
        pred_record = EngagementPrediction(
            model_version_id=active_model.id,
            student_id=window.student_id,
            device_id=window.device_id,
            batch_id=window.batch_id,
            session_id=window.session_id,
            feature_window_id=window.id,
            prediction=inference_result.get("prediction"),
            confidence=inference_result.get("confidence"),
            probability_high=inference_result.get("probability_high", inference_result.get("probabilities", {}).get("high")),
            probability_medium=inference_result.get("probability_medium", inference_result.get("probabilities", {}).get("medium")),
            probability_low=inference_result.get("probability_low", inference_result.get("probabilities", {}).get("low")),
            feature_snapshot_json=features,
            collection_status="preliminary_prediction",
            prediction_type="live",
            review_status="preliminary",
            generated_at=now,
        )
        db.add(pred_record)
        db.commit()
        db.refresh(pred_record)

    # Broadcast to professor
    broadcast_prediction_to_professor(
        session=session,
        student_id=window.student_id,
        window_id=window.id,
        prediction_payload={
            "id": pred_record.id,
            "prediction_available": True,
            "collection_status": "preliminary_prediction",
            "model_version_id": active_model.id,
            "model_version_tag": active_model.version_tag,
            "prediction": pred_record.prediction,
            "confidence": pred_record.confidence,
            "probability_high": pred_record.probability_high,
            "probability_medium": pred_record.probability_medium,
            "probability_low": pred_record.probability_low,
            "prediction_type": "live",
            "review_status": pred_record.review_status,
            "is_advisory": True,
            "review_required": True,
            "advisory_disclaimer": "Advisory only for professor review. Never automatically penalizes or grades students.",
            "feature_snapshot_json": features,
            "generated_at": pred_record.generated_at.isoformat(),
        },
        window=window,
    )

    return pred_record


def generate_final_prediction_for_student(
    db: Session,
    session: SessionModel,
    student_id: str,
) -> Optional[EngagementPrediction]:
    """
    Generates one final consolidated advisory prediction upon session completion for a student.
    Aggregates all valid feature windows across the entire session.
    """
    windows = (
        db.execute(
            select(EngagementFeatureWindow)
            .where(
                EngagementFeatureWindow.session_id == session.id,
                EngagementFeatureWindow.student_id == student_id,
                EngagementFeatureWindow.validation_status == "valid",
            )
            .order_by(EngagementFeatureWindow.window_start_at.asc())
        )
        .scalars()
        .all()
    )

    if not windows:
        return None

    active_model = get_active_model(db)
    if not active_model:
        return None

    # Consolidated totals across all windows
    last_window = windows[-1]
    total_app = sum(getattr(w, "allowed_academic_application_active_seconds", 0.0) or 0.0 for w in windows)
    total_web = sum(getattr(w, "allowed_academic_website_active_seconds", 0.0) or 0.0 for w in windows)
    total_acad = total_app + total_web
    if total_acad == 0.0:
        total_acad = sum(w.academic_active_seconds for w in windows)

    total_non_acad = sum(w.non_academic_active_seconds for w in windows)
    total_idle = sum(w.idle_seconds for w in windows)
    total_unknown = sum(getattr(w, "unknown_or_unavailable_seconds", 0.0) or 0.0 for w in windows)
    total_switches = sum(w.application_switch_count for w in windows)
    total_unauth = sum(w.unauthorized_application_attempt_count for w in windows)
    total_blocked = sum(w.blocked_website_attempt_count for w in windows)
    total_viol = sum(w.policy_violation_count for w in windows)
    total_elapsed = max(last_window.session_elapsed_seconds, total_acad + total_non_acad + total_idle + total_unknown)

    # Merge resource breakdown summaries
    merged_apps: Dict[str, float] = {}
    merged_websites: Dict[str, float] = {}
    for w in windows:
        bd = getattr(w, "approved_resources_breakdown", None) or {}
        if isinstance(bd, dict):
            for a_name, a_sec in bd.get("applications", {}).items():
                merged_apps[a_name] = round(merged_apps.get(a_name, 0.0) + float(a_sec), 2)
            for w_name, w_sec in bd.get("websites", {}).items():
                merged_websites[w_name] = round(merged_websites.get(w_name, 0.0) + float(w_sec), 2)

    raw_summary = {
        "allowed_academic_application_active_seconds": total_app,
        "allowed_academic_website_active_seconds": total_web,
        "academic_active_seconds": total_acad,
        "non_academic_active_seconds": total_non_acad,
        "idle_seconds": total_idle,
        "unknown_or_unavailable_seconds": total_unknown,
        "application_switch_count": total_switches,
        "unauthorized_application_attempt_count": total_unauth,
        "blocked_website_attempt_count": total_blocked,
        "policy_violation_count": total_viol,
        "session_elapsed_seconds": total_elapsed,
    }
    features = compute_feature_vector(raw_summary)

    inference = predict_engagement_from_features(db, features)
    if not inference.get("prediction_available"):
        return None

    now = datetime.now(timezone.utc)
    final_pred = EngagementPrediction(
        model_version_id=active_model.id,
        student_id=student_id,
        device_id=last_window.device_id,
        batch_id=last_window.batch_id,
        session_id=session.id,
        feature_window_id=last_window.id,
        prediction=inference["prediction"],
        confidence=inference["confidence"],
        probability_high=inference["probability_high"],
        probability_medium=inference["probability_medium"],
        probability_low=inference["probability_low"],
        feature_snapshot_json=features,
        collection_status="final_prediction",
        prediction_type="final",
        review_status="pending",
        generated_at=now,
    )
    db.add(final_pred)
    db.commit()
    db.refresh(final_pred)

    # Persist or update permanent EngagementSessionSummary
    try:
        existing_summary = db.query(EngagementSessionSummary).filter(
            EngagementSessionSummary.session_id == session.id,
            EngagementSessionSummary.student_id == student_id,
        ).first()

        if existing_summary:
            existing_summary.allowed_academic_application_active_seconds = round(float(total_app), 2)
            existing_summary.allowed_academic_website_active_seconds = round(float(total_web), 2)
            existing_summary.allowed_academic_active_seconds = round(float(total_acad), 2)
            existing_summary.academic_active_seconds = round(float(total_acad), 2)
            existing_summary.non_academic_active_seconds = round(float(total_non_acad), 2)
            existing_summary.idle_seconds = round(float(total_idle), 2)
            existing_summary.unknown_or_unavailable_seconds = round(float(total_unknown), 2)
            existing_summary.application_switch_count = int(total_switches)
            existing_summary.unauthorized_application_attempt_count = int(total_unauth)
            existing_summary.blocked_website_attempt_count = int(total_blocked)
            existing_summary.policy_violation_count = int(total_viol)
            existing_summary.session_elapsed_seconds = round(float(total_elapsed), 2)

            existing_summary.total_allowed_academic_application_active_seconds = round(float(total_app), 2)
            existing_summary.total_allowed_academic_website_active_seconds = round(float(total_web), 2)
            existing_summary.total_allowed_academic_active_seconds = round(float(total_acad), 2)
            existing_summary.total_academic_active_seconds = round(float(total_acad), 2)
            existing_summary.total_non_academic_active_seconds = round(float(total_non_acad), 2)
            existing_summary.total_idle_seconds = round(float(total_idle), 2)
            existing_summary.total_unknown_or_unavailable_seconds = round(float(total_unknown), 2)
            existing_summary.total_application_switch_count = int(total_switches)
            existing_summary.total_unauthorized_application_attempt_count = int(total_unauth)
            existing_summary.total_blocked_website_attempt_count = int(total_blocked)
            existing_summary.total_policy_violation_count = int(total_viol)
            existing_summary.total_session_elapsed_seconds = round(float(total_elapsed), 2)

            existing_summary.approved_resources_breakdown = {"applications": merged_apps, "websites": merged_websites}
            existing_summary.final_prediction_id = final_pred.id
            existing_summary.updated_at = now
            summary_obj = existing_summary
        else:
            summary = EngagementSessionSummary(
                session_id=session.id,
                student_id=student_id,
                batch_id=last_window.batch_id,
                device_id=last_window.device_id,
                allowed_academic_application_active_seconds=round(float(total_app), 2),
                allowed_academic_website_active_seconds=round(float(total_web), 2),
                allowed_academic_active_seconds=round(float(total_acad), 2),
                academic_active_seconds=round(float(total_acad), 2),
                non_academic_active_seconds=round(float(total_non_acad), 2),
                idle_seconds=round(float(total_idle), 2),
                unknown_or_unavailable_seconds=round(float(total_unknown), 2),
                application_switch_count=int(total_switches),
                unauthorized_application_attempt_count=int(total_unauth),
                blocked_website_attempt_count=int(total_blocked),
                policy_violation_count=int(total_viol),
                session_elapsed_seconds=round(float(total_elapsed), 2),
                total_allowed_academic_application_active_seconds=round(float(total_app), 2),
                total_allowed_academic_website_active_seconds=round(float(total_web), 2),
                total_allowed_academic_active_seconds=round(float(total_acad), 2),
                total_academic_active_seconds=round(float(total_acad), 2),
                total_non_academic_active_seconds=round(float(total_non_acad), 2),
                total_idle_seconds=round(float(total_idle), 2),
                total_unknown_or_unavailable_seconds=round(float(total_unknown), 2),
                total_application_switch_count=int(total_switches),
                total_unauthorized_application_attempt_count=int(total_unauth),
                total_blocked_website_attempt_count=int(total_blocked),
                total_policy_violation_count=int(total_viol),
                total_session_elapsed_seconds=round(float(total_elapsed), 2),
                approved_resources_breakdown={"applications": merged_apps, "websites": merged_websites},
                data_completeness_percent=100.0,
                feature_completeness_percent=100.0,
                final_prediction_id=final_pred.id,
                created_at=now,
                updated_at=now,
            )
            db.add(summary)
            summary_obj = summary
        db.commit()
        db.refresh(summary_obj)
        final_pred.session_summary_id = summary_obj.id
        db.commit()

        # Broadcast finalized prediction
        broadcast_engagement_prediction_finalized(
            payload={
                "session_id": session.id,
                "student_id": student_id,
                "prediction_id": final_pred.id,
                "prediction": final_pred.prediction,
                "confidence": final_pred.confidence,
                "probability_high": final_pred.probability_high,
                "probability_medium": final_pred.probability_medium,
                "probability_low": final_pred.probability_low,
                "prediction_type": "final",
                "collection_status": "final_prediction",
                "is_advisory": True,
                "review_required": True,
                "advisory_disclaimer": "Advisory only for professor review. Never automatically penalizes or grades students.",
                "safe_metrics": {
                    "allowed_academic_application_active_seconds": round(float(total_app), 2),
                    "allowed_academic_website_active_seconds": round(float(total_web), 2),
                    "allowed_academic_active_seconds": round(float(total_acad), 2),
                    "academic_active_seconds": round(float(total_acad), 2),
                    "non_academic_active_seconds": round(float(total_non_acad), 2),
                    "idle_seconds": round(float(total_idle), 2),
                    "unknown_or_unavailable_seconds": round(float(total_unknown), 2),
                    "application_switch_count": int(total_switches),
                    "unauthorized_application_attempt_count": int(total_unauth),
                    "blocked_website_attempt_count": int(total_blocked),
                    "policy_violation_count": int(total_viol),
                    "session_elapsed_seconds": round(float(total_elapsed), 2),
                    "approved_apps_summary": merged_apps,
                    "approved_websites_summary": merged_websites,
                },
                "last_updated": now.isoformat(),
            },
            professor_id=session.created_by,
        )
    except Exception as e:
        logger.error(f"Failed to record EngagementSessionSummary for student {student_id}: {e}")

    return final_pred


def finalize_session_predictions(
    db: Session,
    session_id: str,
):
    """
    Called when a session ends. Generates a 'final' consolidated prediction for each participating student.
    """
    session = db.get(SessionModel, session_id)
    if not session:
        return

    # Find distinct students with valid windows
    stmt = (
        select(EngagementFeatureWindow.student_id)
        .where(
            EngagementFeatureWindow.session_id == session_id,
            EngagementFeatureWindow.validation_status == "valid",
        )
        .distinct()
    )
    student_ids = db.execute(stmt).scalars().all()

    for s_id in student_ids:
        try:
            generate_final_prediction_for_student(db, session, s_id)
        except Exception as e:
            logger.error(
                f"Failed to generate final engagement prediction for student {s_id} in session {session_id}: {e}"
            )


def broadcast_prediction_to_professor(
    session: SessionModel,
    student_id: str,
    window_id: str,
    prediction_payload: dict,
    window: Optional[EngagementFeatureWindow] = None,
):
    """Broadcasts engagement prediction to owning professor room only."""
    try:
        features = prediction_payload.get("feature_snapshot_json") or {}
        app_sec = features.get("allowed_academic_application_active_seconds")
        if app_sec is None and window:
            app_sec = getattr(window, "allowed_academic_application_active_seconds", 0.0)

        web_sec = features.get("allowed_academic_website_active_seconds")
        if web_sec is None and window:
            web_sec = getattr(window, "allowed_academic_website_active_seconds", 0.0)

        total_acad = features.get("allowed_academic_active_seconds")
        if total_acad is None:
            total_acad = (float(app_sec or 0.0) + float(web_sec or 0.0)) or features.get("academic_active_seconds", 0.0)

        breakdown = getattr(window, "approved_resources_breakdown", {}) if window else {}
        completeness = getattr(window, "feature_completeness_percent", 100.0) if window else 100.0

        payload = {
            "session_id": session.id,
            "student_id": student_id,
            "feature_window_id": window_id,
            "prediction": prediction_payload,
            "safe_metrics": {
                "allowed_academic_application_active_seconds": round(float(app_sec or 0.0), 2),
                "allowed_academic_website_active_seconds": round(float(web_sec or 0.0), 2),
                "allowed_academic_active_seconds": round(float(total_acad or 0.0), 2),
                "academic_active_seconds": round(float(total_acad or 0.0), 2),
                "non_academic_active_seconds": features.get("non_academic_active_seconds", 0.0),
                "idle_seconds": features.get("idle_seconds", 0.0),
                "unknown_or_unavailable_seconds": features.get("unknown_or_unavailable_seconds", 0.0),
                "application_switch_count": features.get("application_switch_count", 0),
                "blocked_website_attempt_count": features.get("blocked_website_attempt_count", 0),
                "unauthorized_application_attempt_count": features.get("unauthorized_application_attempt_count", 0),
                "policy_violation_count": features.get("policy_violation_count", 0),
                "feature_completeness_percent": completeness,
                "approved_resources_breakdown": breakdown,
            },
            "is_advisory": True,
            "review_required": True,
            "advisory_disclaimer": "Advisory only for professor review. Never automatically penalizes or grades students.",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        broadcast_engagement_prediction(payload, professor_id=session.created_by)
        broadcast_engagement_features(payload, professor_id=session.created_by)
    except Exception as e:
        logger.warning(f"Failed to broadcast engagement prediction to professor: {e}")

