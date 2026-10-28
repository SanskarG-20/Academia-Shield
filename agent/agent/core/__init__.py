"""
Academia Shield Agent Core Package.
"""

from .auth import Ed25519Signer, TokenManager
from .enrollment import DeviceInfo, EnrollmentManager, AGENT_VERSION
from .api import ApiClient, DEFAULT_API_URL
from .storage import LocalDatabase
from .telemetry import TelemetryManager
from .policy import PolicyEngine
from .updater import UpdateManifestVerifier
from .state_machine import AgentState, AgentStateMachine

__all__ = [
    "Ed25519Signer",
    "TokenManager",
    "DeviceInfo",
    "EnrollmentManager",
    "AGENT_VERSION",
    "ApiClient",
    "DEFAULT_API_URL",
    "LocalDatabase",
    "TelemetryManager",
    "PolicyEngine",
    "UpdateManifestVerifier",
    "AgentState",
    "AgentStateMachine"
]
