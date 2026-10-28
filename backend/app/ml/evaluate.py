"""Model evaluation utilities for engagement classification.

Computes comprehensive metrics:
- Overall Accuracy
- Precision, Recall, F1 (Macro and Weighted)
- Confusion Matrix
- Per-class Metrics (High, Medium, Low)
- Feature Importances
"""
from typing import Dict, Any, List
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
)
from app.ml.features import CANONICAL_FEATURE_NAMES
from app.ml.dataset import REVERSE_LABEL_MAP


def evaluate_classifier(
    model: Any,
    X_test: Any,
    y_test: Any,
    feature_names: List[str] = CANONICAL_FEATURE_NAMES,
) -> Dict[str, Any]:
    """
    Evaluates a trained classifier on a test set.
    """
    y_pred = model.predict(X_test)

    # Accuracy
    acc = float(accuracy_score(y_test, y_pred))

    # Macro & Weighted metrics
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(
        y_test, y_pred, average="macro", zero_division=0
    )
    p_weight, r_weight, f1_weight, _ = precision_recall_fscore_support(
        y_test, y_pred, average="weighted", zero_division=0
    )

    # Per-class metrics
    classes = [0, 1, 2]  # Low, Medium, High
    p_class, r_class, f1_class, support = precision_recall_fscore_support(
        y_test, y_pred, labels=classes, zero_division=0
    )

    class_metrics = {}
    for idx, c in enumerate(classes):
        c_name = REVERSE_LABEL_MAP.get(c, str(c))
        class_metrics[c_name] = {
            "precision": float(p_class[idx]),
            "recall": float(r_class[idx]),
            "f1": float(f1_class[idx]),
            "support": int(support[idx]),
        }

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred, labels=classes).tolist()

    # Feature importances
    feature_importances = {}
    if hasattr(model, "feature_importances_"):
        for name, imp in zip(feature_names, model.feature_importances_):
            feature_importances[name] = round(float(imp), 4)

    return {
        "accuracy": round(acc, 4),
        "precision_macro": round(float(p_macro), 4),
        "recall_macro": round(float(r_macro), 4),
        "f1_macro": round(float(f1_macro), 4),
        "precision_weighted": round(float(p_weight), 4),
        "recall_weighted": round(float(r_weight), 4),
        "f1_weighted": round(float(f1_weight), 4),
        "confusion_matrix": cm,
        "class_metrics": class_metrics,
        "feature_importances": feature_importances,
        "test_sample_count": len(y_test),
    }
