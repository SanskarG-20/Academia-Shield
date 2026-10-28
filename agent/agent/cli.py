"""
Academia Shield Local Agent CLI Interface.
Provides visible commands for status, diagnostics, student login, enrollment,
session joining/leaving, disabling enforcement, logout, and uninstallation.
"""

import sys
import os
import argparse
import json
import logging
from typing import Optional

from .platforms import get_platform_bundle
from .core.storage.database import LocalDatabase
from .core.auth.tokens import TokenManager
from .core.enrollment.enrollment_manager import EnrollmentManager
from .core.api.client import ApiClient, DEFAULT_API_URL
from .core.policy.engine import PolicyEngine
from .core.state_machine.machine import AgentStateMachine, AgentState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent.cli")

def get_context():
    platform = get_platform_bundle()
    db = LocalDatabase()
    tokens = TokenManager(platform.storage)
    enrollment = EnrollmentManager(platform.storage)
    
    dev_info = enrollment.get_enrollment_info()
    api = ApiClient(
        base_url=os.getenv("BACKEND_API_URL", DEFAULT_API_URL),
        token_manager=tokens,
        device_identifier=dev_info.get("device_identifier")
    )
    enrollment.api_client = api
    policy_engine = PolicyEngine(db)

    # Initialize state machine
    initial_state = AgentState.ENROLLED_IDLE if enrollment.is_enrolled() else AgentState.NOT_ENROLLED
    sm = AgentStateMachine(
        initial_state=initial_state,
        on_restore=lambda: platform.dns.restore_original_dns()
    )

    return {
        "platform": platform,
        "db": db,
        "tokens": tokens,
        "enrollment": enrollment,
        "api": api,
        "policy_engine": policy_engine,
        "sm": sm
    }

def cmd_status(args):
    ctx = get_context()
    enrolled = ctx["enrollment"].is_enrolled()
    info = ctx["enrollment"].get_enrollment_info()
    cached_policy = ctx["db"].get_cached_policy()

    status_data = {
        "state": ctx["sm"].current_state.value,
        "enrolled": enrolled,
        "device_id": info.get("device_id"),
        "device_identifier": info.get("device_identifier"),
        "has_public_key": bool(info.get("public_key")),
        "token_valid": not ctx["tokens"].is_token_expired(),
        "policy_active": bool(cached_policy),
        "policy_version": cached_policy.get("policy_version") if cached_policy else None,
        "session_id": cached_policy.get("session_id") if cached_policy else None,
        "platform": ctx["platform"].platform_name
    }
    print(json.dumps(status_data, indent=2))

def cmd_diagnostics(args):
    ctx = get_context()
    diag = ctx["platform"].get_diagnostics()
    diag["storage_accessible"] = True
    diag["local_db_path"] = ctx["db"].db_path
    diag["recent_audit_logs"] = ctx["db"].get_recent_audit_logs(limit=5)
    print(json.dumps(diag, indent=2))

def cmd_login(args):
    ctx = get_context()
    email = args.email
    password = args.password

    resp = ctx["api"].post("/api/v1/auth/login", json={"email": email, "password": password})
    if resp.get("status_code") == 200 and "access_token" in resp.get("data", {}):
        data = resp["data"]
        ctx["tokens"].save_tokens(
            data["access_token"],
            data.get("refresh_token"),
            data.get("expires_in", 3600)
        )
        ctx["db"].write_audit_log("AUTH", "STUDENT_LOGIN", {"email": email})
        print(json.dumps({"success": True, "message": f"Logged in as {email}"}, indent=2))
    else:
        err = resp.get("data", {}).get("detail") or resp.get("error", "Login failed")
        print(json.dumps({"success": False, "error": err}, indent=2))
        sys.exit(1)

def cmd_enroll(args):
    ctx = get_context()
    res = ctx["enrollment"].enroll_device()
    if res.get("success"):
        ctx["db"].write_audit_log("ENROLLMENT", "DEVICE_ENROLLED", res)
        print(json.dumps({"success": True, "details": res}, indent=2))
    else:
        print(json.dumps({"success": False, "error": res.get("error")}, indent=2))
        sys.exit(1)

def cmd_join_session(args):
    ctx = get_context()
    session_id = args.session_id

    # 1. Register presence / join session on backend
    resp = ctx["api"].post(f"/api/v1/sessions/{session_id}/join", json={})
    if resp.get("status_code") not in (200, 201) and not resp.get("ok"):
        # Fallback to direct presence ping or continue if already joined
        logger.warning(f"Join endpoint returned {resp.get('status_code')}. Checking active policy...")

    # 2. Fetch active policy
    pol_resp = ctx["api"].get("/api/v1/agent/policies/active")
    if pol_resp.get("status_code") == 200:
        policy_data = pol_resp.get("data", {})
        valid, msg = ctx["policy_engine"].load_and_verify_policy(policy_data)
        if valid:
            ctx["sm"].transition_to(AgentState.POLICY_RECEIVED, {"session_id": session_id})
            # Apply DNS enforcement
            dns_res = ctx["platform"].dns.apply_dns_redirect()
            ctx["sm"].transition_to(AgentState.ENFORCING)
            ctx["db"].write_audit_log("SESSION", "JOIN_AND_ENFORCE", {"session_id": session_id, "dns": dns_res.to_dict()})
            print(json.dumps({"success": True, "state": "ENFORCING", "session_id": session_id, "dns_result": dns_res.to_dict()}, indent=2))
            return
        else:
            print(json.dumps({"success": False, "error": f"Policy verification failed: {msg}"}, indent=2))
            sys.exit(1)
    else:
        print(json.dumps({"success": False, "error": "Failed to fetch policy from backend"}, indent=2))
        sys.exit(1)

def cmd_leave_session(args):
    ctx = get_context()
    ctx["sm"].student_leave()
    ctx["platform"].dns.restore_original_dns()
    ctx["db"].clear_cached_policy()
    ctx["db"].write_audit_log("SESSION", "STUDENT_LEAVE", {})
    print(json.dumps({"success": True, "state": ctx["sm"].current_state.value, "message": "Left session and restored settings"}, indent=2))

def cmd_disable_enforcement(args):
    ctx = get_context()
    ctx["platform"].dns.restore_original_dns()
    ctx["sm"].transition_to(AgentState.RESTORING)
    ctx["sm"].transition_to(AgentState.ENROLLED_IDLE)
    ctx["db"].clear_cached_policy()
    ctx["db"].write_audit_log("ENFORCEMENT", "MANUAL_DISABLE", {})
    print(json.dumps({"success": True, "message": "Enforcement disabled and network settings restored"}, indent=2))

def cmd_logout(args):
    ctx = get_context()
    ctx["platform"].dns.restore_original_dns()
    ctx["tokens"].clear_tokens()
    ctx["db"].clear_cached_policy()
    ctx["db"].write_audit_log("AUTH", "LOGOUT", {})
    print(json.dumps({"success": True, "message": "Logged out and tokens cleared"}, indent=2))

def cmd_uninstall(args):
    ctx = get_context()
    purge = getattr(args, "purge", False)
    res = ctx["platform"].uninstaller.uninstall(purge_data=purge)
    ctx["db"].write_audit_log("LIFECYCLE", "UNINSTALL", res.to_dict())
    print(json.dumps(res.to_dict(), indent=2))

def main():
    parser = argparse.ArgumentParser(description="Academia Shield Local Agent CLI")
    subparsers = parser.add_subparsers(dest="command", help="Agent commands")

    subparsers.add_parser("status", help="Show agent state and enrollment details")
    subparsers.add_parser("diagnostics", help="Run platform diagnostics")

    login_p = subparsers.add_parser("login", help="Authenticate student")
    login_p.add_argument("--email", required=True, help="Student email")
    login_p.add_argument("--password", required=True, help="Student password")

    subparsers.add_parser("enroll", help="Enroll this device")

    join_p = subparsers.add_parser("join-session", help="Join an academic session")
    join_p.add_argument("--session-id", required=True, help="Session UUID")

    subparsers.add_parser("leave-session", help="Leave active session and restore settings")
    subparsers.add_parser("disable-enforcement", help="Disable active enforcement and restore DNS")
    subparsers.add_parser("logout", help="Log out and clear cached credentials")

    uninst_p = subparsers.add_parser("uninstall", help="Uninstall agent and clean settings")
    uninst_p.add_argument("--purge", action="store_true", help="Purge local database and app data")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "status": cmd_status,
        "diagnostics": cmd_diagnostics,
        "login": cmd_login,
        "enroll": cmd_enroll,
        "join-session": cmd_join_session,
        "leave-session": cmd_leave_session,
        "disable-enforcement": cmd_disable_enforcement,
        "logout": cmd_logout,
        "uninstall": cmd_uninstall
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
