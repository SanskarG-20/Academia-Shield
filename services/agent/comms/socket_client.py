"""
Academia Shield Agent — Socket.IO Communication Module

Connects to the Express backend via Socket.IO for instant
session lifecycle events (session_started / session_ended).

Falls back gracefully if the connection fails — the HTTP polling
loop in agent.py will continue to work independently.

Requires: python-socketio[client] (listed in requirements.txt)
"""

import logging
import threading
from credentials import load_credential
from typing import Callable, Optional

LOGGER = logging.getLogger("academia_shield_agent")

# python-socketio is an optional dependency.
# If not installed, the socket client degrades gracefully.
try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    LOGGER.warning(
        "[Socket] python-socketio is not installed. "
        "Socket.IO push communication is disabled. "
        "Install with: pip install python-socketio[client]"
    )


class AgentSocketClient:
    """
    Socket.IO client that listens for session lifecycle events.

    Usage:
        client = AgentSocketClient(url, agent_id, on_started, on_ended)
        client.connect()    # non-blocking (runs in background thread)
        ...
        client.disconnect()
    """

    def __init__(
        self,
        server_url: str,
        agent_id: str,
        on_session_started: Optional[Callable] = None,
        on_session_ended: Optional[Callable] = None,
    ):
        self._server_url = server_url
        self._agent_id = agent_id
        self._on_session_started = on_session_started
        self._on_session_ended = on_session_ended
        self._sio: Optional[object] = None
        self._connected = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self):
        """Start the Socket.IO connection in a background thread."""
        if not SOCKETIO_AVAILABLE:
            LOGGER.warning("[Socket] Cannot connect — python-socketio not installed")
            return

        if self._connected:
            return

        self._thread = threading.Thread(target=self._run, daemon=True, name="SocketIO")
        self._thread.start()

    def disconnect(self):
        """Disconnect from the server."""
        if self._sio and self._connected:
            try:
                self._sio.disconnect()
            except Exception:
                pass
        self._connected = False

    def _run(self):
        """Background thread: connect and listen for events."""
        sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,  # unlimited
            reconnection_delay=5,
            reconnection_delay_max=30,
            logger=False,
            engineio_logger=False,
        )
        self._sio = sio

        @sio.event
        def connect():
            self._connected = True
            LOGGER.info("[Socket] Connected to %s", self._server_url)
            sio.emit("join_agent")

        @sio.event
        def disconnect():
            self._connected = False
            LOGGER.warning("[Socket] Disconnected from server")

        @sio.event
        def connect_error(data):
            LOGGER.warning("[Socket] Connection error: %s", data)

        @sio.on("session_started")
        def on_session_started(data):
            LOGGER.info(
                "[Socket] SESSION_STARTED received: %s (domains=%s)",
                data.get("title", "?"),
                len(data.get("blockedDomains", [])),
            )
            if self._on_session_started:
                try:
                    self._on_session_started(data)
                except Exception as err:
                    LOGGER.error("[Socket] Error in session_started handler: %s", err)

        @sio.on("session_ended")
        def on_session_ended(data):
            LOGGER.info(
                "[Socket] SESSION_ENDED received: %s (%s)",
                data.get("title", "?"),
                data.get("newStatus", "?"),
            )
            if self._on_session_ended:
                try:
                    self._on_session_ended(data)
                except Exception as err:
                    LOGGER.error("[Socket] Error in session_ended handler: %s", err)

        # Connect (blocking — runs in background thread)
        try:
            credential = load_credential()
            if not credential:
                return
            sio.connect(self._server_url, auth={"token": f"Device {credential}"}, transports=["websocket", "polling"])
            sio.wait()  # blocks until disconnected
        except Exception as err:
            LOGGER.warning("[Socket] Failed to connect to %s: %s", self._server_url, err)
            self._connected = False
