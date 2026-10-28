"""Dataset extraction and preparation for engagement model training.

Extracts validated feature windows from completed lab sessions that possess
verified professor engagement labels ('High', 'Medium', 'Low').
Computes canonical 14-dimensional feature vectors and formats them into
Pandas DataFrames for model training.
"""
from typing import Tuple, List, Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.engagement import EngagementFeatureWindow, SessionEngagementLabel
from app.models.session import SessionModel
from app.ml.features import compute_feature_vector, CANONICAL_FEATURE_NAMES

LABEL_MAP = {
    "High": 2,
    "Medium": 1,
    "Low": 0,
}

REVERSE_LABEL_MAP = {v: k for k, v in LABEL_MAP.items()}


def extract_labeled_dataset(
    db: Session,
    min_windows_per_session: int = 1,
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, Any]]:
    """
    Extracts features and target labels from completed sessions with human labels.

    Returns:
        X (pd.DataFrame): 14 canonical features per sample.
        y (pd.Series): Target integer labels (0=Low, 1=Medium, 2=High).
        metadata (Dict[str, Any]): Sample counts, session counts, class distribution.
    """
    # Query completed sessions that have a professor label
    stmt = (
        select(EngagementFeatureWindow, SessionEngagementLabel.label)
        .join(
            SessionEngagementLabel,
            (EngagementFeatureWindow.session_id == SessionEngagementLabel.session_id)
            & (EngagementFeatureWindow.student_id == SessionEngagementLabel.student_id),
        )
        .join(
            SessionModel,
            EngagementFeatureWindow.session_id == SessionModel.id,
        )
        .where(
            EngagementFeatureWindow.validation_status == "valid",
            EngagementFeatureWindow.validation_error == None,
            SessionEngagementLabel.label.in_(["High", "Medium", "Low"]),
        )
    )

    results = db.execute(stmt).all()

    if not results:
        return pd.DataFrame(columns=CANONICAL_FEATURE_NAMES), pd.Series(dtype=int), {
            "total_samples": 0,
            "session_count": 0,
            "class_distribution": {"High": 0, "Medium": 0, "Low": 0},
        }

    records: List[Dict[str, float]] = []
    labels: List[int] = []
    seen_sessions = set()

    for window, label_str in results:
        seen_sessions.add(window.session_id)
        feat_dict = compute_feature_vector(window)
        records.append(feat_dict)
        labels.append(LABEL_MAP[label_str])

    df_X = pd.DataFrame(records)[CANONICAL_FEATURE_NAMES]
    s_y = pd.Series(labels, name="engagement_label")

    counts = s_y.value_counts().to_dict()
    class_dist = {
        "High": counts.get(2, 0),
        "Medium": counts.get(1, 0),
        "Low": counts.get(0, 0),
    }

    metadata = {
        "total_samples": len(df_X),
        "session_count": len(seen_sessions),
        "class_distribution": class_dist,
    }

    return df_X, s_y, metadata
