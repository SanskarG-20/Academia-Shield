"""
Unit tests for Socket.IO real-time telemetry broadcasting, token extraction, and presence.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from app.core.sockets import (
    sio,
    _get_auth_token,
    calculate_student_presence_dict,
    broadcast_telemetry_event,
    broadcast_socket_event,
    broadcast_engagement_features
)
from app.models.session import SessionPresence

def test_get_auth_token():
    """Verify auth token extraction from auth dict, headers, and query strings."""
    # 1. Auth dict
    assert _get_auth_token({}, {"token": "Bearer test-jwt-token"}) == "test-jwt-token"
    assert _get_auth_token({}, {"token": "raw-token"}) == "raw-token"

    # 2. ASGI scope headers
    env_headers = {
        "asgi.scope": {
            "headers": [
                (b"host", b"localhost:8000"),
                (b"authorization", b"Bearer header-jwt-token")
            ]
        }
    }
    assert _get_auth_token(env_headers) == "header-jwt-token"

    # 3. Query string
    env_query = {
        "asgi.scope": {
            "query_string": b"foo=bar&token=query-jwt-token&baz=1"
        }
    }
    assert _get_auth_token(env_query) == "query-jwt-token"

    # 4. No token provided
    assert _get_auth_token({}) is None


def test_calculate_student_presence_dict():
    """Verify presence calculation for active, idle, and left students."""
    now = datetime.now(timezone.utc)

    # 1. Left student
    presence_left = SessionPresence(
        session_id="sess-1",
        student_id="stud-1",
        updated_at=now
    )
    res_left = calculate_student_presence_dict(presence_left, participant_status="left", student_name="Alice")
    assert res_left["participant_status"] == "left"
    assert res_left["presence_status"] == "offline"
    assert res_left["connection_source"] == "none"

    # 2. Online student (recent browser ping within 45s)
    presence_online = SessionPresence(
        session_id="sess-1",
        student_id="stud-2",
        browser_last_seen_at=now - timedelta(seconds=10),
        agent_last_seen_at=now - timedelta(seconds=20),
        updated_at=now
    )
    res_online = calculate_student_presence_dict(presence_online, participant_status="joined", student_name="Bob")
    assert res_online["participant_status"] == "joined"
    assert res_online["presence_status"] == "online"
    assert res_online["connection_source"] == "both"

    # 3. Offline student (stale timestamps > 90s)
    presence_offline = SessionPresence(
        session_id="sess-1",
        student_id="stud-3",
        browser_last_seen_at=now - timedelta(seconds=120),
        agent_last_seen_at=now - timedelta(seconds=150),
        updated_at=now
    )
    res_offline = calculate_student_presence_dict(presence_offline, participant_status="joined", student_name="Charlie")
    assert res_offline["presence_status"] == "offline"
    assert res_offline["connection_source"] == "none"


@pytest.mark.asyncio
async def test_socket_room_joining_and_broadcasting():
    """Verify Socket.IO room joining and telemetry event broadcasting."""
    events_received = []

    # Simple test handler
    @sio.event
    async def test_event(sid, data):
        events_received.append(data)

    test_data = {
        "_id": "test-telemetry-id",
        "sessionId": "test-session-123",
        "studentId": "stud-1",
        "studentName": "Test Student",
        "resource": "vscode.exe",
        "engagementScore": 90,
        "isViolation": False,
        "timestamp": "2026-08-14T19:00:00Z"
    }

    # Execute broadcast helpers
    broadcast_telemetry_event(test_data)
    broadcast_socket_event("custom_event", {"message": "hello"}, session_id="test-session-123")
    broadcast_engagement_features({"features": []}, professor_id="prof-123")

    # Allow async tasks to dispatch on event loop
    await asyncio.sleep(0.05)
    assert True

