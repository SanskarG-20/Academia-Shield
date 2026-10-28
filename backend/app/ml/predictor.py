"""Live engagement inference engine.

Predicts student engagement (High, Medium, Low) using the currently approved ML model.
Computes class probabilities and confidence scores.
Handles model unavailability gracefully and ensures inference never throws uncaught exceptions.
"""
import logging
from typing import Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session

from app.ml.features import CANONICAL_FEATURE_NAMES
from app.ml.dataset import REVERSE_LABEL_MAP
from app.ml.model_registry import load_cached_active_model

logger = logging.getLogger(__name__)


def predict_engagement_from_features(
    db: Session,
    features: Dict[str, float],
) -> Dict[str, Any]:
    """
    Executes inference for a single 14-dimensional feature vector.

    Returns:
        dict containing:
            - prediction_available (bool)
            - model_version_id (Optional[str])
            - model_version_tag (Optional[str])
            - prediction (Optional[str]: 'High' | 'Medium' | 'Low')
            - confidence (Optional[float]: 0.0 to 1.0)
            - probability_high (Optional[float])
            - probability_medium (Optional[float])
            - probability_low (Optional[float])
            - feature_snapshot_json (dict)
            - reason (Optional[str] if unavailable)
    """
    active_model_record, artifact = load_cached_active_model(db)

    if not active_model_record or not artifact:
        return {
            "prediction_available": False,
            "reason": "No approved ML model is currently active",
            "model_version_id": None,
            "model_version_tag": None,
            "prediction": None,
            "confidence": None,
            "probability_high": None,
            "probability_medium": None,
            "probability_low": None,
            "feature_snapshot_json": features,
        }

    clf = artifact.get("model")
    if not clf:
        return {
            "prediction_available": False,
            "reason": "Corrupted model artifact",
            "model_version_id": active_model_record.id,
            "model_version_tag": active_model_record.version_tag,
            "prediction": None,
            "confidence": None,
            "probability_high": None,
            "probability_medium": None,
            "probability_low": None,
            "feature_snapshot_json": features,
        }

    # Format into DataFrame with model-aligned feature columns
    feature_cols = None
    if hasattr(clf, "feature_names_in_"):
        feature_cols = list(clf.feature_names_in_)
    elif artifact.get("feature_names"):
        feature_cols = artifact.get("feature_names")
    elif artifact.get("features"):
        feature_cols = artifact.get("features")
    else:
        feature_cols = CANONICAL_FEATURE_NAMES

    if len(feature_cols) != len(CANONICAL_FEATURE_NAMES):
        return {
            "prediction_available": False,
            "reason": f"Model schema mismatch: active model has {len(feature_cols)} features, expected {len(CANONICAL_FEATURE_NAMES)} (Schema 2.0.0). Retraining or activating an approved v2.0.0 model is required.",
            "model_version_id": active_model_record.id,
            "model_version_tag": active_model_record.version_tag,
            "prediction": None,
            "confidence": None,
            "probability_high": None,
            "probability_medium": None,
            "probability_low": None,
            "feature_snapshot_json": features,
        }

    df_row = pd.DataFrame([{col: features.get(col, 0.0) for col in feature_cols}])[feature_cols]

    try:
        pred_int = int(clf.predict(df_row)[0])
        pred_label = REVERSE_LABEL_MAP.get(pred_int, "Medium")

        # Class probabilities
        # Check clf.classes_ to map accurately
        proba = clf.predict_proba(df_row)[0]
        class_to_prob = {}
        for cls_idx, cls_label_int in enumerate(clf.classes_):
            cls_name = REVERSE_LABEL_MAP.get(int(cls_label_int), str(cls_label_int))
            class_to_prob[cls_name] = float(proba[cls_idx])

        prob_high = round(class_to_prob.get("High", 0.0), 4)
        prob_med = round(class_to_prob.get("Medium", 0.0), 4)
        prob_low = round(class_to_prob.get("Low", 0.0), 4)

        # Confidence is the probability of the predicted class
        confidence = round(class_to_prob.get(pred_label, float(max(proba))), 4)

        return {
            "prediction_available": True,
            "model_version_id": active_model_record.id,
            "model_version_tag": active_model_record.version_tag,
            "prediction": pred_label,
            "confidence": confidence,
            "probability_high": prob_high,
            "probability_medium": prob_med,
            "probability_low": prob_low,
            "feature_snapshot_json": features,
            "reason": None,
        }
    except Exception as e:
        logger.error(f"Inference error on engagement prediction: {e}", exc_info=True)
        return {
            "prediction_available": False,
            "reason": f"Inference execution failed: {str(e)}",
            "model_version_id": active_model_record.id,
            "model_version_tag": active_model_record.version_tag,
            "prediction": None,
            "confidence": None,
            "probability_high": None,
            "probability_medium": None,
            "probability_low": None,
            "feature_snapshot_json": features,
        }
