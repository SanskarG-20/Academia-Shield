"""
Socket.IO Server & Real-time Event Broadcaster for Academia Shield.
Handles authenticated real-time presence, session room joining, and live telemetry streaming.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union
import socketio
from sqlalchemy.orm import Session

from .database import SessionLocal
from .security import decode_token
from ..models.session import SessionModel, SessionParticipant, SessionPresence
from ..models.batch import Batch
from ..models.user import User

logger = logging.getLogger(__name__)

# Create Socket.IO AsyncServer supporting ASGI
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False
)

# Socket.IO ASGI application wrapper
sio_app = socketio.ASGIApp(sio, socketio_path="socket.io")

def _get_auth_token(environ: dict, auth: dict = None) -> Optional[str]:
    """Extract JWT token from socket handshake auth object, headers, or query parameters."""
    if auth and isinstance(auth, dict) and auth.get("token"):
        return auth.get("token").replace("Bearer ", "").strip()
    
    # Check headers in environ
    headers = environ.get("asgi.scope", {}).get("headers", [])
    for key, val in headers:
        key_str = key.decode("utf-8", errors="ignore") if isinstance(key, bytes) else str(key)
        if key_str.lower() == "authorization":
            val_str = val.decode("utf-8", errors="ignore") if isinstance(val, bytes) else str(val)
            if val_str.startswith("Bearer "):
                return val_str.replace("Bearer ", "").strip()

    # Check query string
    query_raw = environ.get("asgi.scope", {}).get("query_string", b"")
    if isinstance(query_raw, bytes):
        query_string = query_raw.decode("utf-8", errors="ignore")
    else:
        query_string = str(query_raw or "")

    for param in query_string.split("&"):
        if param.startswith("token="):
            return param.split("=")[1].strip()
            
    return None

@sio.event
async def connect(sid, environ, auth=None):
    token = _get_auth_token(environ, auth)
    if not token:
        logger.warning(f"[socket] Connection rejected for {sid}: Missing authentication token.")
        # We allow connection for legacy unauthenticated listeners or reject if strict
        await sio.save_session(sid, {"authenticated": False})
        return

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        role = payload.get("role")
        email = payload.get("email")
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            user_name = user.full_name if user else (email or "User")
        finally:
            db.close()

        await sio.save_session(sid, {
            "authenticated": True,
            "user_id": user_id,
            "role": role,
            "email": email,
            "name": user_name
        })
        await sio.enter_room(sid, f"user_{user_id}")
        logger.info(f"[socket] Authenticated client connected: {sid} (user: {user_id}, role: {role})")
    except Exception as e:
        logger.warning(f"[socket] Invalid token on connect for {sid}: {e}")
        await sio.save_session(sid, {"authenticated": False})

@sio.event
async def disconnect(sid):
    session_data = await sio.get_session(sid) or {}
    user_id = session_data.get("user_id")
    current_session_id = session_data.get("active_session_id")
    user_name = session_data.get("name", "Student")

    if user_id and current_session_id:
        db = SessionLocal()
        try:
            presence = db.query(SessionPresence).filter(
                SessionPresence.session_id == current_session_id,
                SessionPresence.student_id == user_id
            ).first()

            if presence:
                now = datetime.now(timezone.utc)
                presence.browser_last_seen_at = now
                presence.connected_socket_count = max(0, presence.connected_socket_count - 1)
                presence.updated_at = now
                db.commit()

                # Calculate updated status & broadcast to session room
                presence_info = calculate_student_presence_dict(presence, "joined", user_name)
                presence_info["latest_activity"] = "PRESENCE_UPDATED"

                clean_id = str(current_session_id).strip()
                await sio.emit("presence_updated", presence_info, room=clean_id)
                await sio.emit("presence_updated", presence_info, room=f"session_{clean_id}")
        except Exception as e:
            logger.warning(f"[socket] Error processing disconnect presence for {sid}: {e}")
        finally:
            db.close()

    logger.info(f"[socket] Client disconnected: {sid}")

@sio.event
async def join_session(sid, data):
    if not data:
        return
        
    session_id = data if isinstance(data, str) else data.get("session_id")
    if not session_id:
        return
        
    clean_id = str(session_id).strip()
    session_data = await sio.get_session(sid) or {}
    user_id = session_data.get("user_id")
    role = session_data.get("role")
    user_name = session_data.get("name", "User")

    db = SessionLocal()
    try:
        session_obj = db.query(SessionModel).filter(SessionModel.id == clean_id).first()
        if not session_obj:
            await sio.emit("error", {"message": "Session not found."}, room=sid)
            return

        if session_obj.status != "active" and role == "student":
            await sio.emit("error", {"message": "Session is not active."}, room=sid)
            return

        if role == "student":
            participant = db.query(SessionParticipant).filter(
                SessionParticipant.session_id == clean_id,
                SessionParticipant.student_id == user_id,
                SessionParticipant.status == "joined"
            ).first()

            if not participant:
                await sio.emit("error", {"message": "Access denied. You have not joined this session."}, room=sid)
                return

            now = datetime.now(timezone.utc)
            presence = db.query(SessionPresence).filter(
                SessionPresence.session_id == clean_id,
                SessionPresence.student_id == user_id
            ).first()

            if not presence:
                presence = SessionPresence(
                    session_id=clean_id,
                    student_id=user_id,
                    browser_last_seen_at=now,
                    connected_socket_count=1,
                    joined_at=now,
                    updated_at=now
                )
                db.add(presence)
            else:
                presence.browser_last_seen_at = now
                presence.connected_socket_count += 1
                presence.updated_at = now

            db.commit()
            db.refresh(presence)

            session_data["active_session_id"] = clean_id
            await sio.save_session(sid, session_data)

            # Broadcast presence update
            presence_info = calculate_student_presence_dict(presence, "joined", user_name)
            presence_info["latest_activity"] = "STUDENT_JOINED"

            await sio.emit("presence_updated", presence_info, room=clean_id)
            await sio.emit("presence_updated", presence_info, room=f"session_{clean_id}")

        await sio.enter_room(sid, clean_id)
        await sio.enter_room(sid, f"session_{clean_id}")
        logger.info(f"[socket] {sid} (user: {user_id}) joined session room: {clean_id}")
    except Exception as e:
        logger.error(f"[socket] Error in join_session: {e}")
    finally:
        db.close()

@sio.event
async def session_presence_heartbeat(sid, data=None):
    session_data = await sio.get_session(sid) or {}
    user_id = session_data.get("user_id")
    user_name = session_data.get("name", "Student")
    session_id = (data.get("session_id") if isinstance(data, dict) else data) or session_data.get("active_session_id")

    if not user_id or not session_id:
        return

    clean_id = str(session_id).strip()
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        participant = db.query(SessionParticipant).filter(
            SessionParticipant.session_id == clean_id,
            SessionParticipant.student_id == user_id
        ).first()
        p_status = participant.status if participant else "joined"

        presence = db.query(SessionPresence).filter(
            SessionPresence.session_id == clean_id,
            SessionPresence.student_id == user_id
        ).first()

        was_online = False
        if not presence:
            presence = SessionPresence(
                session_id=clean_id,
                student_id=user_id,
                browser_last_seen_at=now,
                connected_socket_count=1,
                joined_at=now,
                updated_at=now
            )
            db.add(presence)
        else:
            prev_b = presence.browser_last_seen_at
            if prev_b:
                if prev_b.tzinfo is None:
                    prev_b = prev_b.replace(tzinfo=timezone.utc)
                was_online = (now - prev_b).total_seconds() <= 45
            presence.browser_last_seen_at = now
            presence.updated_at = now

        db.commit()
        db.refresh(presence)

        if not was_online:
            presence_info = calculate_student_presence_dict(presence, p_status, user_name)
            presence_info["latest_activity"] = "PRESENCE_UPDATED"
            await sio.emit("presence_updated", presence_info, room=clean_id)
    except Exception as e:
        logger.warning(f"[socket] Error in presence heartbeat: {e}")
    finally:
        db.close()

@sio.event
async def session_leave(sid, data=None):
    session_data = await sio.get_session(sid) or {}
    user_id = session_data.get("user_id")
    user_name = session_data.get("name", "Student")
    session_id = (data.get("session_id") if isinstance(data, dict) else data) or session_data.get("active_session_id")

    if not user_id or not session_id:
        return

    clean_id = str(session_id).strip()
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        participant = db.query(SessionParticipant).filter(
            SessionParticipant.session_id == clean_id,
            SessionParticipant.student_id == user_id
        ).first()

        if participant:
            participant.status = "left"
            participant.left_at = now
            p_status = "left"
        else:
            p_status = "left"

        presence = db.query(SessionPresence).filter(
            SessionPresence.session_id == clean_id,
            SessionPresence.student_id == user_id
        ).first()

        if presence:
            presence.connected_socket_count = 0
            presence.updated_at = now

        db.commit()

        presence_info = calculate_student_presence_dict(presence, "left", user_name)
        presence_info["latest_activity"] = "STUDENT_LEFT"

        await sio.emit("student_left", presence_info, room=clean_id)
        await sio.emit("student_left", presence_info, room=f"session_{clean_id}")
        await sio.emit("presence_updated", presence_info, room=clean_id)
        await sio.emit("presence_updated", presence_info, room=f"session_{clean_id}")

        await sio.leave_room(sid, clean_id)
        await sio.leave_room(sid, f"session_{clean_id}")
    except Exception as e:
        logger.error(f"[socket] Error in session_leave: {e}")
    finally:
        db.close()

@sio.event
async def join_live_logs(sid, data=None):
    await sio.enter_room(sid, "live_logs")
    logger.info(f"[socket] {sid} joined live_logs room")

def calculate_student_presence_dict(presence_rec: SessionPresence, participant_status: str = "joined", student_name: str = "Student") -> dict:
    """Utility function to calculate real-time online/offline presence based on 45s/90s threshold."""
    now = datetime.now(timezone.utc)
    
    if participant_status == "left":
        last_seen = presence_rec.updated_at if presence_rec and presence_rec.updated_at else now
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return {
            "session_id": presence_rec.session_id if presence_rec else "",
            "student_id": presence_rec.student_id if presence_rec else "",
            "name": student_name,
            "participant_status": "left",
            "presence_status": "offline",
            "last_seen_at": last_seen.isoformat(),
            "connection_source": "none",
            "engagement_score": None,
            "latest_activity": "STUDENT_LEFT"
        }

    browser_last = presence_rec.browser_last_seen_at if presence_rec else None
    agent_last = presence_rec.agent_last_seen_at if presence_rec else None

    if browser_last and browser_last.tzinfo is None:
        browser_last = browser_last.replace(tzinfo=timezone.utc)
    if agent_last and agent_last.tzinfo is None:
        agent_last = agent_last.replace(tzinfo=timezone.utc)

    browser_online = browser_last is not None and (now - browser_last).total_seconds() <= 45
    agent_online = agent_last is not None and (now - agent_last).total_seconds() <= 90

    is_online = browser_online or agent_online
    presence_status = "online" if is_online else "offline"

    if browser_online and agent_online:
        connection_source = "both"
    elif browser_online:
        connection_source = "browser"
    elif agent_online:
        connection_source = "agent"
    else:
        connection_source = "none"

    timestamps = [ts for ts in [browser_last, agent_last] if ts is not None]
    last_seen = max(timestamps) if timestamps else (presence_rec.updated_at if presence_rec else now)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)

    return {
        "session_id": presence_rec.session_id if presence_rec else "",
        "student_id": presence_rec.student_id if presence_rec else "",
        "name": student_name,
        "participant_status": participant_status,
        "presence_status": presence_status,
        "last_seen_at": last_seen.isoformat(),
        "connection_source": connection_source,
        "engagement_score": None,
        "latest_activity": "PRESENCE_UPDATED"
    }

async def _emit_event_async(event_name: str, payload: dict, room: Optional[str] = None):
    # Emit global broadcast for general listeners (e.g. Navbar notifications, real-time toasts)
    await sio.emit(event_name, payload)

    if room:
        clean_room = str(room).strip()
        await sio.emit(event_name, payload, room=clean_room)
        await sio.emit(event_name, payload, room=f"session_{clean_room}")

    target_user = payload.get("student_id") or payload.get("user_id")
    if target_user:
        await sio.emit(event_name, payload, room=f"user_{target_user}")

    await sio.emit(event_name, payload, room="live_logs")

def broadcast_socket_event(event_name: str, payload: dict, session_id: Optional[str] = None):
    """Thread-safe synchronous wrapper to broadcast socket events."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            asyncio.create_task(_emit_event_async(event_name, payload, session_id))
        else:
            asyncio.run(_emit_event_async(event_name, payload, session_id))
    except Exception as e:
        logger.warning(f"[socket] Failed to broadcast event {event_name}: {e}")

async def _emit_telemetry(data: dict):
    """Internal async emitter for telemetry and live log updates."""
    session_id = data.get("sessionId") or data.get("session_id")
    is_violation = bool(
        data.get("isViolation")
        or data.get("is_violation")
        or data.get("type") == "VIOLATION"
        or str(data.get("action", "")).lower() in ("blocked", "closed", "violation")
    )

    data["isViolation"] = is_violation
    data["is_violation"] = is_violation
    if is_violation and data.get("type") != "VIOLATION":
        data["type"] = "VIOLATION"

    # 1. Global broadcast for live dashboards, logs views, and monitors (emitted once)
    await sio.emit("live_log_update", data)

    # 2. Session and global room alerts for policy violations
    if is_violation:
        await sio.emit("policy_violation", data)
        if session_id:
            clean_id = str(session_id).strip()
            await sio.emit("policy_violation", data, room=clean_id)
            await sio.emit("policy_violation", data, room=f"session_{clean_id}")
            await sio.emit("policy_violation", data, room=f"engagement_{clean_id}")

def broadcast_telemetry_event(data: dict):
    """Thread-safe synchronous wrapper to broadcast telemetry data via Socket.IO."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            asyncio.create_task(_emit_telemetry(data))
        else:
            asyncio.run(_emit_telemetry(data))
    except Exception as e:
        logger.warning(f"[socket] Failed to broadcast telemetry event: {e}")

async def _emit_engagement_features(payload: dict, professor_id: str):
    """Emit engagement features strictly to the owning professor's authenticated room."""
    clean_id = str(professor_id).strip()
    await sio.emit("engagement_features_updated", payload, room=f"user_{clean_id}")

def broadcast_engagement_features(payload: dict, professor_id: str):
    """Thread-safe synchronous wrapper to broadcast engagement features to owning professor only."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            asyncio.create_task(_emit_engagement_features(payload, professor_id))
        else:
            asyncio.run(_emit_engagement_features(payload, professor_id))
    except Exception as e:
        logger.warning(f"[socket] Failed to broadcast engagement features: {e}")

async def _emit_engagement_prediction(payload: dict, professor_id: str):
    """Emit engagement prediction strictly to the owning professor's authenticated room and engagement session room."""
    clean_id = str(professor_id).strip()
    await sio.emit("engagement_prediction_updated", payload, room=f"user_{clean_id}")
    session_id = payload.get("session_id")
    if session_id:
        await sio.emit("engagement_prediction_updated", payload, room=f"engagement_{str(session_id).strip()}")

def broadcast_engagement_prediction(payload: dict, professor_id: str):
    """Thread-safe synchronous wrapper to broadcast engagement prediction to owning professor only."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            asyncio.create_task(_emit_engagement_prediction(payload, professor_id))
        else:
            asyncio.run(_emit_engagement_prediction(payload, professor_id))
    except Exception as e:
        logger.warning(f"[socket] Failed to broadcast engagement prediction: {e}")

async def _emit_engagement_collection_started(payload: dict, professor_id: str):
    clean_id = str(professor_id).strip()
    await sio.emit("engagement_collection_started", payload, room=f"user_{clean_id}")
    session_id = payload.get("session_id")
    if session_id:
        await sio.emit("engagement_collection_started", payload, room=f"engagement_{str(session_id).strip()}")

def broadcast_engagement_collection_started(payload: dict, professor_id: str):
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            asyncio.create_task(_emit_engagement_collection_started(payload, professor_id))
        else:
            asyncio.run(_emit_engagement_collection_started(payload, professor_id))
    except Exception as e:
        logger.warning(f"[socket] Failed to broadcast engagement_collection_started: {e}")

async def _emit_engagement_data_insufficient(payload: dict, professor_id: str):
    clean_id = str(professor_id).strip()
    await sio.emit("engagement_data_insufficient", payload, room=f"user_{clean_id}")
    session_id = payload.get("session_id")
    if session_id:
        await sio.emit("engagement_data_insufficient", payload, room=f"engagement_{str(session_id).strip()}")

def broadcast_engagement_data_insufficient(payload: dict, professor_id: str):
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            asyncio.create_task(_emit_engagement_data_insufficient(payload, professor_id))
        else:
            asyncio.run(_emit_engagement_data_insufficient(payload, professor_id))
    except Exception as e:
        logger.warning(f"[socket] Failed to broadcast engagement_data_insufficient: {e}")

async def _emit_engagement_prediction_finalized(payload: dict, professor_id: str):
    clean_id = str(professor_id).strip()
    await sio.emit("engagement_prediction_finalized", payload, room=f"user_{clean_id}")
    session_id = payload.get("session_id")
    if session_id:
        await sio.emit("engagement_prediction_finalized", payload, room=f"engagement_{str(session_id).strip()}")

def broadcast_engagement_prediction_finalized(payload: dict, professor_id: str):
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            asyncio.create_task(_emit_engagement_prediction_finalized(payload, professor_id))
        else:
            asyncio.run(_emit_engagement_prediction_finalized(payload, professor_id))
    except Exception as e:
        logger.warning(f"[socket] Failed to broadcast engagement_prediction_finalized: {e}")

async def _emit_engagement_model_status_changed(payload: dict):
    # Model status updates broadcast to all professor sessions and live_logs
    await sio.emit("engagement_model_status_changed", payload)

def broadcast_engagement_model_status_changed(payload: dict):
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            asyncio.create_task(_emit_engagement_model_status_changed(payload))
        else:
            asyncio.run(_emit_engagement_model_status_changed(payload))
    except Exception as e:
        logger.warning(f"[socket] Failed to broadcast engagement_model_status_changed: {e}")

@sio.event
async def subscribe_engagement_session(sid, data):
    """Allow only the verified owning professor or administrator to subscribe to engagement live updates."""
    session_data = await sio.get_session(sid) or {}
    user_id = session_data.get("user_id")
    role = session_data.get("role")
    session_id = data.get("session_id") if isinstance(data, dict) else data

    if not user_id or not session_id or role == "student":
        await sio.emit("error", {"message": "Access denied. Only professors can subscribe to engagement updates."}, room=sid)
        return

    clean_id = str(session_id).strip()
    db = SessionLocal()
    try:
        session_obj = db.query(SessionModel).filter(SessionModel.id == clean_id).first()
        if not session_obj:
            await sio.emit("error", {"message": "Session not found."}, room=sid)
            return

        batch_obj = db.query(Batch).filter(Batch.id == session_obj.batch_id).first()
        is_owner = (session_obj.created_by == user_id) or (batch_obj and batch_obj.professor_id == user_id)
        if role != "admin" and not is_owner:
            await sio.emit("error", {"message": "Access denied. You do not own this batch or session."}, room=sid)
            return

        await sio.enter_room(sid, f"engagement_{clean_id}")
        await sio.enter_room(sid, clean_id)
        await sio.enter_room(sid, f"session_{clean_id}")
        logger.info(f"[socket] Professor {user_id} subscribed to engagement for session {clean_id}")
    except Exception as e:
        logger.error(f"[socket] Error in subscribe_engagement_session: {e}")
    finally:
        db.close()
