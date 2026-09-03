"""
Academia Shield Agent — Communications package

Re-exports the HTTP polling/reporting helpers so callers can do:

    from comms import fetch_config_with_retry, report_to_server, send_heartbeat

`AgentSocketClient` is resolved lazily via module __getattr__ so that
importing this package does not pull in python-socketio (and does not log a
"not installed" warning) on agents running with SOCKET_ENABLED=false.
"""

from comms.http_client import (
    fetch_config_with_retry,
    fetch_remote_config_once,
    load_cached_config,
    normalize_config,
    report_to_server,
    save_cached_config,
    send_heartbeat,
)

__all__ = [
    "AgentSocketClient",
    "SOCKETIO_AVAILABLE",
    "fetch_config_with_retry",
    "fetch_remote_config_once",
    "load_cached_config",
    "normalize_config",
    "report_to_server",
    "save_cached_config",
    "send_heartbeat",
]

_LAZY_SOCKET_ATTRS = ("AgentSocketClient", "SOCKETIO_AVAILABLE")


def __getattr__(name):
    """Import the Socket.IO client only when it is actually requested."""
    if name in _LAZY_SOCKET_ATTRS:
        from comms import socket_client

        return getattr(socket_client, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
