"""
Agent State Machine for Academia Shield.
Implements the 9 standard states with strict transition guards and guaranteed policy restoration hooks.

States:
- NOT_INSTALLED
- NOT_ENROLLED
- ENROLLED_IDLE
- WAITING_FOR_SESSION
- WAITING_FOR_STUDENT_JOIN
- POLICY_RECEIVED
- ENFORCING
- RESTORING
- ERROR
"""

import logging
from enum import Enum
from typing import Optional, Dict, Any, Callable, List

logger = logging.getLogger(__name__)

class AgentState(str, Enum):
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_ENROLLED = "NOT_ENROLLED"
    ENROLLED_IDLE = "ENROLLED_IDLE"
    WAITING_FOR_SESSION = "WAITING_FOR_SESSION"
    WAITING_FOR_STUDENT_JOIN = "WAITING_FOR_STUDENT_JOIN"
    POLICY_RECEIVED = "POLICY_RECEIVED"
    ENFORCING = "ENFORCING"
    OFFLINE_ENFORCING = "OFFLINE_ENFORCING"
    RESTORING = "RESTORING"
    ERROR = "ERROR"

class AgentStateMachine:
    """
    Finite State Machine governing agent lifecycle, session joining, policy activation, and restoration.
    """

    def __init__(
        self,
        initial_state: AgentState = AgentState.NOT_ENROLLED,
        on_state_change: Optional[Callable[[AgentState, AgentState, Dict[str, Any]], None]] = None,
        on_restore: Optional[Callable[[], None]] = None
    ):
        self.current_state = initial_state
        self.on_state_change = on_state_change
        self.on_restore = on_restore
        self.context: Dict[str, Any] = {
            "session_id": None,
            "policy_version": None,
            "student_joined": False,
            "last_error": None
        }

    # Valid transitions mapping
    VALID_TRANSITIONS = {
        AgentState.NOT_INSTALLED: {AgentState.NOT_ENROLLED, AgentState.ENROLLED_IDLE, AgentState.ERROR},
        AgentState.NOT_ENROLLED: {AgentState.ENROLLED_IDLE, AgentState.NOT_INSTALLED, AgentState.ERROR},
        AgentState.ENROLLED_IDLE: {AgentState.WAITING_FOR_SESSION, AgentState.WAITING_FOR_STUDENT_JOIN, AgentState.POLICY_RECEIVED, AgentState.NOT_ENROLLED, AgentState.NOT_INSTALLED, AgentState.ERROR},
        AgentState.WAITING_FOR_SESSION: {AgentState.WAITING_FOR_STUDENT_JOIN, AgentState.ENROLLED_IDLE, AgentState.ERROR},
        AgentState.WAITING_FOR_STUDENT_JOIN: {AgentState.POLICY_RECEIVED, AgentState.ENROLLED_IDLE, AgentState.RESTORING, AgentState.ERROR},
        AgentState.POLICY_RECEIVED: {AgentState.ENFORCING, AgentState.OFFLINE_ENFORCING, AgentState.RESTORING, AgentState.ERROR},
        AgentState.ENFORCING: {AgentState.OFFLINE_ENFORCING, AgentState.RESTORING, AgentState.ENROLLED_IDLE, AgentState.ERROR},
        AgentState.OFFLINE_ENFORCING: {AgentState.ENFORCING, AgentState.RESTORING, AgentState.ENROLLED_IDLE, AgentState.ERROR},
        AgentState.RESTORING: {AgentState.ENROLLED_IDLE, AgentState.WAITING_FOR_SESSION, AgentState.ERROR},
        AgentState.ERROR: {AgentState.RESTORING, AgentState.ENROLLED_IDLE, AgentState.NOT_ENROLLED, AgentState.NOT_INSTALLED}
    }

    def transition_to(self, new_state: AgentState, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Transition to a new state if valid.
        """
        old_state = self.current_state

        if new_state not in self.VALID_TRANSITIONS.get(old_state, set()):
            # Allow emergency transition to RESTORING or ERROR from any state
            if new_state not in (AgentState.RESTORING, AgentState.ERROR):
                logger.warning(f"Illegal state transition attempted: {old_state} -> {new_state}")
                return False

        logger.info(f"Agent state transition: {old_state.value} -> {new_state.value}")
        self.current_state = new_state

        meta = metadata or {}
        for k, v in meta.items():
            self.context[k] = v

        # Trigger restoration hook whenever entering RESTORING state
        if new_state == AgentState.RESTORING and self.on_restore:
            try:
                self.on_restore()
            except Exception as e:
                logger.error(f"Error during state machine restoration callback: {e}")

        if self.on_state_change:
            try:
                self.on_state_change(old_state, new_state, self.context)
            except Exception as e:
                logger.error(f"Error in on_state_change callback: {e}")

        return True

    def student_join(self, session_id: str) -> bool:
        """
        Manual student join action. Required before enforcement can activate.
        """
        self.context["session_id"] = session_id
        self.context["student_joined"] = True
        if self.current_state in (AgentState.ENROLLED_IDLE, AgentState.WAITING_FOR_SESSION, AgentState.WAITING_FOR_STUDENT_JOIN):
            return self.transition_to(AgentState.POLICY_RECEIVED, {"session_id": session_id})
        return False

    def enter_offline_enforcing(self) -> bool:
        """
        Transitions to OFFLINE_ENFORCING if network is lost while blocking.
        Enforcement continues locally via cached policy.
        """
        if self.current_state == AgentState.ENFORCING:
            return self.transition_to(AgentState.OFFLINE_ENFORCING)
        return False

    def return_to_online_enforcing(self) -> bool:
        """
        Returns from OFFLINE_ENFORCING back to ENFORCING when network connectivity resumes.
        """
        if self.current_state == AgentState.OFFLINE_ENFORCING:
            return self.transition_to(AgentState.ENFORCING)
        return False

    def end_session_and_restore(self) -> bool:
        """
        Revokes enforcement and restores settings when professor ends session, policy expires, or emergency stop triggers.
        """
        self.context["student_joined"] = False
        return self.transition_to(AgentState.RESTORING, {"session_id": None})

    def student_leave(self) -> bool:
        """
        Alias for end_session_and_restore for backward compatibility.
        """
        return self.end_session_and_restore()

    def trigger_error(self, error_message: str) -> bool:
        self.context["last_error"] = error_message
        return self.transition_to(AgentState.ERROR, {"last_error": error_message})
