"""
Feature Extraction and Engineering for Student Engagement Prediction.
Transforms raw telemetry aggregates into canonical 17-dimensional feature representations.
Strictly privacy-minimized: zero sensitive data, zero personal contents.
Focuses strictly on real live active use of professor-approved applications and websites.
"""

from typing import Dict, List, Any
import numpy as np

SCHEMA_VERSION = "2.0.0"

FEATURE_NAMES: List[str] = [
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

CANONICAL_FEATURE_NAMES = FEATURE_NAMES


def compute_feature_vector(obj: Any) -> Dict[str, float]:
    """Computes all 17 canonical features from an EngagementFeatureWindow object or dict."""
    if isinstance(obj, dict):
        raw = obj
    else:
        raw = {
            "allowed_academic_application_active_seconds": getattr(obj, "allowed_academic_application_active_seconds", 0.0),
            "allowed_academic_website_active_seconds": getattr(obj, "allowed_academic_website_active_seconds", 0.0),
            "academic_active_seconds": getattr(obj, "academic_active_seconds", 0.0),
            "non_academic_active_seconds": getattr(obj, "non_academic_active_seconds", 0.0),
            "idle_seconds": getattr(obj, "idle_seconds", 0.0),
            "unknown_or_unavailable_seconds": getattr(obj, "unknown_or_unavailable_seconds", 0.0),
            "application_switch_count": getattr(obj, "application_switch_count", 0),
            "unauthorized_application_attempt_count": getattr(obj, "unauthorized_application_attempt_count", 0),
            "blocked_website_attempt_count": getattr(obj, "blocked_website_attempt_count", 0),
            "policy_violation_count": getattr(obj, "policy_violation_count", 0),
            "session_elapsed_seconds": getattr(obj, "session_elapsed_seconds", 0.0),
        }
    return compute_feature_dict(raw)


def compute_feature_dict(raw: Dict[str, Any], include_all: bool = True) -> Dict[str, float]:
    """
    Computes all 17 canonical features from raw aggregated student metrics.
    Handles division-by-zero safely and returns floats.
    """
    app_sec = float(raw.get("allowed_academic_application_active_seconds", 0.0) or 0.0)
    web_sec = float(raw.get("allowed_academic_website_active_seconds", 0.0) or 0.0)
    legacy_acad = float(raw.get("academic_active_seconds", 0.0) or 0.0)

    # If app_sec and web_sec are 0 but legacy academic_active_seconds is set, preserve it
    if app_sec == 0.0 and web_sec == 0.0 and legacy_acad > 0.0:
        total_acad = legacy_acad
    else:
        total_acad = app_sec + web_sec

    non_acad = float(raw.get("non_academic_active_seconds", 0.0) or 0.0)
    idle = float(raw.get("idle_seconds", 0.0) or 0.0)
    unknown = float(raw.get("unknown_or_unavailable_seconds", 0.0) or 0.0)

    switches = int(raw.get("application_switch_count", 0) or 0)
    unauth = int(raw.get("unauthorized_application_attempt_count", 0) or 0)
    blocked = int(raw.get("blocked_website_attempt_count", 0) or 0)
    violations = int(raw.get("policy_violation_count", 0) or 0)
    elapsed = float(raw.get("session_elapsed_seconds", 0.0) or 0.0)

    # Ensure non-negative
    app_sec = max(0.0, app_sec)
    web_sec = max(0.0, web_sec)
    total_acad = max(0.0, total_acad)
    non_acad = max(0.0, non_acad)
    idle = max(0.0, idle)
    unknown = max(0.0, unknown)
    switches = max(0, switches)
    unauth = max(0, unauth)
    blocked = max(0, blocked)
    violations = max(0, violations)
    elapsed = max(0.0, elapsed)

    # Total active time across verified categories (academic + non-academic + unknown)
    total_active = total_acad + non_acad + unknown
    total_time = total_active + idle

    # Ratios
    allowed_acad_ratio = round(total_acad / max(total_active, 1.0), 4) if total_active > 0 else 0.0
    allowed_app_ratio = round(app_sec / max(total_active, 1.0), 4) if total_active > 0 else 0.0
    allowed_web_ratio = round(web_sec / max(total_active, 1.0), 4) if total_active > 0 else 0.0
    non_acad_ratio = round(non_acad / max(total_active, 1.0), 4) if total_active > 0 else 0.0
    unknown_ratio = round(unknown / max(total_active, 1.0), 4) if total_active > 0 else 0.0
    idle_ratio = round(idle / max(total_time, 1.0), 4) if total_time > 0 else 0.0

    # Rates per minute
    elapsed_minutes = max(elapsed / 60.0, 1.0)
    switches_per_min = round(float(switches) / elapsed_minutes, 4)
    unauth_per_min = round(float(unauth) / elapsed_minutes, 4)
    blocked_per_min = round(float(blocked) / elapsed_minutes, 4)
    violation_rate = round(float(violations) / elapsed_minutes, 4)

    res = {
        # 1-6 Primary Positive Features
        "allowed_academic_application_active_seconds": round(app_sec, 2),
        "allowed_academic_website_active_seconds": round(web_sec, 2),
        "allowed_academic_active_seconds": round(total_acad, 2),
        "allowed_academic_activity_ratio": allowed_acad_ratio,
        "allowed_app_activity_ratio": allowed_app_ratio,
        "allowed_website_activity_ratio": allowed_web_ratio,
        # 7-17 Negative / Context Features
        "idle_seconds": round(idle, 2),
        "idle_ratio": idle_ratio,
        "non_academic_active_seconds": round(non_acad, 2),
        "non_academic_activity_ratio": non_acad_ratio,
        "unknown_or_unavailable_seconds": round(unknown, 2),
        "unknown_activity_ratio": unknown_ratio,
        "application_switches_per_minute": switches_per_min,
        "blocked_attempts_per_minute": blocked_per_min,
        "unauthorized_application_attempts_per_minute": unauth_per_min,
        "violation_rate": violation_rate,
        "session_elapsed_seconds": round(elapsed, 2),
    }

    # Backward compatibility / raw aliases
    res["academic_active_seconds"] = round(total_acad, 2)
    res["academic_activity_ratio"] = allowed_acad_ratio
    res["application_switch_count"] = switches
    res["unauthorized_application_attempt_count"] = unauth
    res["blocked_website_attempt_count"] = blocked
    res["policy_violation_count"] = violations

    return res


def compute_extended_feature_dict(raw: Dict[str, Any]) -> Dict[str, float]:
    """Computes full feature dictionary."""
    return compute_feature_dict(raw, include_all=True)


def extract_feature_vector(feature_dict: Dict[str, Any], feature_names: List[str] | None = None) -> np.ndarray:
    """Extract ordered 1D NumPy float array matching given or default feature names."""
    names = feature_names or FEATURE_NAMES
    return np.array([float(feature_dict.get(k, 0.0)) for k in names], dtype=np.float64)

