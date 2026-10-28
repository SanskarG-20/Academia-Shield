"""
Tests for 8-State Lifecycle State Machine and Policy Restoration.
"""

import pytest
from agent.core.state_machine.machine import AgentStateMachine, AgentState

def test_initial_state_and_valid_transitions():
    restored_called = False
    def on_restore():
        nonlocal restored_called
        restored_called = True

    sm = AgentStateMachine(initial_state=AgentState.NOT_ENROLLED, on_restore=on_restore)
    assert sm.current_state == AgentState.NOT_ENROLLED

    # NOT_ENROLLED -> ENROLLED_IDLE
    assert sm.transition_to(AgentState.ENROLLED_IDLE) is True
    assert sm.current_state == AgentState.ENROLLED_IDLE

    # ENROLLED_IDLE -> WAITING_FOR_SESSION
    assert sm.transition_to(AgentState.WAITING_FOR_SESSION) is True
    assert sm.current_state == AgentState.WAITING_FOR_SESSION

    # WAITING_FOR_SESSION -> WAITING_FOR_STUDENT_JOIN
    assert sm.transition_to(AgentState.WAITING_FOR_STUDENT_JOIN) is True
    assert sm.current_state == AgentState.WAITING_FOR_STUDENT_JOIN

    # Student joins session -> POLICY_RECEIVED
    assert sm.student_join("sess_abc123") is True
    assert sm.current_state == AgentState.POLICY_RECEIVED
    assert sm.context.get("student_joined") is True

    # POLICY_RECEIVED -> ENFORCING
    assert sm.transition_to(AgentState.ENFORCING) is True
    assert sm.current_state == AgentState.ENFORCING

    # Student leaves or session ends -> RESTORING
    assert sm.student_leave() is True
    assert sm.current_state == AgentState.RESTORING
    assert restored_called is True

    # RESTORING -> ENROLLED_IDLE
    assert sm.transition_to(AgentState.ENROLLED_IDLE) is True
    assert sm.current_state == AgentState.ENROLLED_IDLE

def test_illegal_state_transition_prevented():
    sm = AgentStateMachine(initial_state=AgentState.NOT_ENROLLED)
    # Direct jump from NOT_ENROLLED to ENFORCING is prohibited
    assert sm.transition_to(AgentState.ENFORCING) is False
    assert sm.current_state == AgentState.NOT_ENROLLED

def test_emergency_restoration_from_error():
    restored_count = 0
    def on_restore():
        nonlocal restored_count
        restored_count += 1

    sm = AgentStateMachine(initial_state=AgentState.ENFORCING, on_restore=on_restore)
    sm.trigger_error("Fatal network disconnect")
    assert sm.current_state == AgentState.ERROR
    assert sm.context.get("last_error") == "Fatal network disconnect"

    # From ERROR can transition to RESTORING
    sm.transition_to(AgentState.RESTORING)
    assert sm.current_state == AgentState.RESTORING
    assert restored_count == 1

def test_offline_enforcing_and_recovery():
    sm = AgentStateMachine(initial_state=AgentState.ENROLLED_IDLE)
    sm.student_join("sess_offline_001")
    sm.transition_to(AgentState.ENFORCING)
    assert sm.current_state == AgentState.ENFORCING

    # Network drops -> OFFLINE_ENFORCING (Enforcement persists)
    assert sm.enter_offline_enforcing() is True
    assert sm.current_state == AgentState.OFFLINE_ENFORCING

    # Network recovers -> ENFORCING
    assert sm.return_to_online_enforcing() is True
    assert sm.current_state == AgentState.ENFORCING

    # Emergency stop or session end from OFFLINE_ENFORCING
    sm.enter_offline_enforcing()
    assert sm.end_session_and_restore() is True
    assert sm.current_state == AgentState.RESTORING
