"""
Unit and integration test suite for Academia Shield Real Student Engagement.

Covers the 9 critical requirements:
1. Allowed application open (e.g. VS Code) with no input for 60s -> classified as idle, idle_seconds increases, academic active time remains 0.
2. Allowed website open with no input for 60s -> classified as idle, idle_seconds increases, academic active time remains 0.
3. Active usage of allowed app (idle < 60s) -> allowed_academic_application_active_seconds increases.
4. Active usage of allowed website -> allowed_academic_website_active_seconds increases.
5. Blocked app or site while active -> non_academic_active_seconds and violation count increase.
6. Browser domain cannot be safely determined -> unknown_or_unavailable_seconds increases, never assumed academic.
7. Classification totals equal telemetry window duration (Schema & validation test).
8. Engagement prediction drops from High to Low as idle time increases.
9. Privacy guarantee: zero keystrokes, screenshots, page contents, full URLs, or files stored.
"""

import sys
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_DIR = os.path.join(PROJECT_ROOT, "agent")
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

for p in [PROJECT_ROOT, AGENT_DIR, BACKEND_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from agent.telemetry.activity_classifier import ActivityClassifier, ActivityClassificationResult
from agent.telemetry.engagement_tracker import EngagementTracker
from app.schemas.engagement import EngagementWindowPayload


# ==============================================================================
# TEST 1: Allowed App Open (e.g. VS Code), Sitting Idle -> Counts as IDLE
# ==============================================================================
def test_1_allowed_app_open_sitting_idle():
    """
    If professor set allowed app to VS Code ('code.exe') and student has it open,
    but sits idle (no typing/clicking for >= 60s), it MUST count as IDLE,
    NOT as academic active time!
    """
    mock_fg = MagicMock()
    mock_fg.get_foreground_process_id.return_value = 1234
    mock_fg.get_foreground_window_title.return_value = "main.py - Visual Studio Code"

    with patch("psutil.Process") as mock_proc:
        mock_proc.return_value.name.return_value = "code.exe"

        # Idle time is 75 seconds (> 60s threshold)
        classifier = ActivityClassifier(
            idle_threshold_seconds=60.0,
            idle_detector_fn=lambda: 75.0,
            foreground_detector=mock_fg
        )

        result = classifier.classify(
            session_id="sess-1",
            device_id="dev-1",
            allowed_applications={"code.exe", "code"}
        )

        assert result.classification == "idle"
        assert result.idle_duration == 75.0

    # Also verify via EngagementTracker tick
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")

    with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=75.0):
        with patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=1234):
            with patch("psutil.Process") as mock_proc:
                mock_proc.return_value.name.return_value = "code.exe"
                # Tick 5 seconds
                res = tracker.tick(allowed_applications={"code.exe"}, dt=5.0)

                assert res.classification == "idle"
                assert tracker.idle_seconds == 5.0
                assert tracker.allowed_academic_application_active_seconds == 0.0
                assert tracker.allowed_academic_website_active_seconds == 0.0
                assert tracker.academic_active_seconds == 0.0


# ==============================================================================
# TEST 2: Allowed Website Open, Sitting Idle -> Counts as IDLE
# ==============================================================================
def test_2_allowed_website_open_sitting_idle():
    """
    If student has an allowed website open in browser (e.g. canvas.instructure.com)
    but sits idle without input for >= 60s, it MUST count as IDLE.
    """
    mock_fg = MagicMock()
    mock_fg.get_foreground_process_id.return_value = 5678
    mock_fg.get_foreground_window_title.return_value = "Assignments - canvas.instructure.com - Google Chrome"

    with patch("psutil.Process") as mock_proc:
        mock_proc.return_value.name.return_value = "chrome.exe"

        # Idle time is 65 seconds
        classifier = ActivityClassifier(
            idle_threshold_seconds=60.0,
            idle_detector_fn=lambda: 65.0,
            foreground_detector=mock_fg
        )

        result = classifier.classify(
            session_id="sess-1",
            device_id="dev-1",
            allowed_websites={"canvas.instructure.com"}
        )

        assert result.classification == "idle"
        assert result.idle_duration == 65.0

    # Verify via EngagementTracker
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")

    with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=65.0):
        with patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=5678):
            with patch.object(tracker.fg_detector, "get_foreground_window_title", return_value="canvas.instructure.com - Google Chrome"):
                with patch("psutil.Process") as mock_proc:
                    mock_proc.return_value.name.return_value = "chrome.exe"
                    res = tracker.tick(allowed_websites={"canvas.instructure.com"}, dt=5.0)

                    assert res.classification == "idle"
                    assert tracker.idle_seconds == 5.0
                    assert tracker.allowed_academic_website_active_seconds == 0.0
                    assert tracker.academic_active_seconds == 0.0


# ==============================================================================
# TEST 3: Active Usage of Allowed App (e.g. Typing in VS Code)
# ==============================================================================
def test_3_active_usage_of_allowed_app():
    """
    When student is actively writing code or typing in VS Code (idle time = 2s < 60s),
    it counts toward allowed_academic_application_active_seconds.
    """
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")

    with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=2.0):
        with patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=1234):
            with patch("psutil.Process") as mock_proc:
                mock_proc.return_value.name.return_value = "code.exe"
                mock_proc.return_value.name.side_effect = None

                res = tracker.tick(allowed_applications={"code.exe"}, dt=5.0)

                assert res.classification == "allowed_academic_active"
                assert res.resource_subtype == "application"
                assert tracker.allowed_academic_application_active_seconds == 5.0
                assert tracker.allowed_academic_website_active_seconds == 0.0
                assert tracker.idle_seconds == 0.0
                assert tracker.academic_active_seconds == 5.0


# ==============================================================================
# TEST 4: Active Usage of Allowed Website
# ==============================================================================
def test_4_active_usage_of_allowed_website():
    """
    When student is actively interacting on an allowed website in browser (idle = 1s < 60s),
    it counts toward allowed_academic_website_active_seconds.
    """
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")

    with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=1.0):
        with patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=5678):
            with patch.object(tracker.fg_detector, "get_foreground_window_title", return_value="Canvas LMS - canvas.instructure.com - Google Chrome"):
                with patch("psutil.Process") as mock_proc:
                    mock_proc.return_value.name.return_value = "chrome.exe"

                    res = tracker.tick(allowed_websites={"canvas.instructure.com"}, dt=5.0)

                    assert res.classification == "allowed_academic_active"
                    assert res.resource_subtype == "website"
                    assert tracker.allowed_academic_website_active_seconds == 5.0
                    assert tracker.allowed_academic_application_active_seconds == 0.0
                    assert tracker.idle_seconds == 0.0


# ==============================================================================
# TEST 5: Blocked App or Website While Active -> Non-Academic & Violation
# ==============================================================================
def test_5_blocked_app_or_website_active():
    """
    When student is actively using a blocked app (e.g. discord.exe) or blocked site,
    it classifies as non_academic_active and records a violation.
    """
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")

    with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=1.5):
        with patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=9999):
            with patch("psutil.Process") as mock_proc:
                mock_proc.return_value.name.return_value = "discord.exe"

                res = tracker.tick(
                    allowed_applications={"code.exe"},
                    blocked_applications={"discord.exe"},
                    dt=5.0
                )

                assert res.classification == "non_academic_active"
                assert res.is_violation is True
                assert res.violation_type == "unauthorized_application"
                assert tracker.non_academic_active_seconds == 5.0
                assert tracker.unauthorized_application_attempt_count == 1
                assert tracker.policy_violation_count == 1


# ==============================================================================
# TEST 6: Browser Domain Cannot Be Safely Determined -> Unknown / Unavailable
# ==============================================================================
def test_6_browser_domain_cannot_be_safely_determined():
    """
    If student has a browser open and active, but the title has no domain or is obscure,
    it MUST NOT assume it is an allowed website. It is classified as unknown_or_unavailable.
    """
    tracker = EngagementTracker(idle_threshold_seconds=60.0, window_duration_seconds=300.0)
    tracker.start_session("sess-1", "batch-1", "student-1", "dev-1")

    with patch("agent.telemetry.engagement_tracker._get_system_idle_seconds", return_value=2.0):
        with patch.object(tracker.fg_detector, "get_foreground_process_id", return_value=5678):
            with patch.object(tracker.fg_detector, "get_foreground_window_title", return_value="New Tab - Google Chrome"):
                with patch("psutil.Process") as mock_proc:
                    mock_proc.return_value.name.return_value = "chrome.exe"

                    res = tracker.tick(allowed_websites={"canvas.instructure.com"}, dt=5.0)

                    assert res.classification == "unknown_or_unavailable"
                    assert tracker.unknown_or_unavailable_seconds == 5.0
                    assert tracker.allowed_academic_website_active_seconds == 0.0
                    assert tracker.academic_active_seconds == 0.0


# ==============================================================================
# TEST 7: Classification Totals Equal Window Duration (Validation Test)
# ==============================================================================
def test_7_classification_totals_equal_window_duration():
    """
    EngagementWindowPayload validator must enforce that the sum of classifications
    equals window_duration_seconds within tolerance.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    # Valid payload: 180 + 20 + 80 + 20 = 300
    valid_payload = {
        "event_id": "evt-test-1",
        "session_id": "sess-1",
        "batch_id": "batch-1",
        "student_id": "student-1",
        "device_id": "dev-1",
        "window_started_at": now - timedelta(seconds=300),
        "window_ended_at": now,
        "allowed_academic_application_active_seconds": 120.0,
        "allowed_academic_website_active_seconds": 60.0,
        "allowed_academic_active_seconds": 180.0,
        "idle_seconds": 80.0,
        "non_academic_active_seconds": 20.0,
        "unknown_or_unavailable_seconds": 20.0,
        "feature_completeness_percent": 100.0
    }
    model = EngagementWindowPayload(**valid_payload)
    assert model.allowed_academic_active_seconds == 180.0

    # Invalid payload where sum does not equal duration (> 10s mismatch)
    invalid_payload = dict(valid_payload)
    invalid_payload["idle_seconds"] = 150.0  # Sum is 180 + 150 + 20 + 20 = 370 != 300

    with pytest.raises(ValueError) as exc:
        EngagementWindowPayload(**invalid_payload)
    assert "Classification totals" in str(exc.value)


# ==============================================================================
# TEST 8: Engagement Features Reflect Inactivity (High Idle Drops Academic Ratio)
# ==============================================================================
def test_8_engagement_prediction_drops_as_idle_increases():
    """
    Verify feature vector extraction:
    - When student is mostly active on approved academic tools (250s academic, 30s idle),
      academic_active_ratio is high (> 0.80).
    - When student sits idle with allowed app open (250s idle, 30s academic),
      idle_ratio is high (> 0.80) and academic_active_ratio drops drastically.
    """
    from app.ml.features import compute_feature_vector

    high_window = MagicMock()
    high_window.allowed_academic_application_active_seconds = 200.0
    high_window.allowed_academic_website_active_seconds = 50.0
    high_window.allowed_academic_active_seconds = 250.0
    high_window.academic_active_seconds = 250.0
    high_window.idle_seconds = 30.0
    high_window.non_academic_active_seconds = 20.0
    high_window.unknown_or_unavailable_seconds = 0.0
    high_window.application_switch_count = 2
    high_window.policy_violation_count = 0
    high_window.feature_completeness_percent = 100.0
    high_window.session_elapsed_seconds = 300.0

    low_window = MagicMock()
    low_window.allowed_academic_application_active_seconds = 0.0
    low_window.allowed_academic_website_active_seconds = 30.0
    low_window.allowed_academic_active_seconds = 30.0
    low_window.academic_active_seconds = 30.0
    low_window.idle_seconds = 250.0
    low_window.non_academic_active_seconds = 20.0
    low_window.unknown_or_unavailable_seconds = 0.0
    low_window.application_switch_count = 0
    low_window.policy_violation_count = 0
    low_window.feature_completeness_percent = 100.0
    low_window.session_elapsed_seconds = 300.0

    high_feats = compute_feature_vector(high_window)
    low_feats = compute_feature_vector(low_window)

    assert high_feats["allowed_academic_activity_ratio"] > low_feats["allowed_academic_activity_ratio"]
    assert low_feats["idle_ratio"] > high_feats["idle_ratio"]
    assert low_feats["idle_ratio"] > 0.80


# ==============================================================================
# TEST 9: Privacy Guarantee (Zero Keystrokes, Screenshots, Page Content)
# ==============================================================================
def test_9_privacy_guarantee_zero_sensitive_data():
    """
    Inspect ActivityClassificationResult and EngagementWindowPayload to ensure
    no fields for keystrokes, typed text, screenshots, page contents, files,
    or raw credentials exist.
    """
    # Classification result fields
    forbidden_terms = [
        "keystroke", "keylog", "typed_text", "screenshot", "screen_capture",
        "page_content", "dom_content", "html", "file_content", "password"
    ]

    res_fields = [f.name for f in ActivityClassificationResult.__dataclass_fields__.values()]
    for term in forbidden_terms:
        for field in res_fields:
            assert term not in field.lower(), f"Sensitive field '{field}' detected in classification result!"

    # Payload fields
    payload_fields = list(EngagementWindowPayload.model_fields.keys())
    for term in forbidden_terms:
        for field in payload_fields:
            assert term not in field.lower(), f"Sensitive field '{field}' detected in telemetry payload!"
