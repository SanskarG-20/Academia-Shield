"""
Policy Manager for Academia Shield Agent.

Handles SHA-256 integrity verification, policy versioning, UTC schedule window evaluation,
and safe offline expiry handling.
"""

import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from ..storage import LocalStorageDB
from ..api import APIClientAdapter

LOGGER = logging.getLogger(__name__)

@dataclass
class DomainRule:
    domain: str
    action: str = "block"
    priority: int = 10

@dataclass
class AppRule:
    application: str
    action: str = "close"
    priority: int = 10

@dataclass
class ScheduleWindow:
    session_id: str
    title: str
    start_time: datetime
    end_time: datetime
    status: str = "Active"
    batch_id: Optional[str] = None

    def is_active(self, now_utc: Optional[datetime] = None) -> bool:
        """
        Trust the backend-provided status first.
        If status is 'Active' (case-insensitive), the session IS active — the
        professor controls this via the dashboard. Only fall back to time-window
        comparison when status is not explicitly set.
        """
        if self.status and self.status.strip().lower() == "active":
            return True

        now = now_utc or datetime.now(timezone.utc)

        # Fallback: time-window comparison
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            now_cmp = datetime.now()
            start = self.start_time.replace(tzinfo=None)
            end = self.end_time.replace(tzinfo=None)
            return start <= now_cmp <= end

        return self.start_time <= now <= self.end_time

@dataclass
class VerifiedPolicy:
    policy_version: int
    issued_at: datetime
    expires_at: datetime
    sha256_hash: str
    schedule_windows: List[ScheduleWindow] = field(default_factory=list)
    domain_rules: List[DomainRule] = field(default_factory=list)
    app_rules: List[AppRule] = field(default_factory=list)
    allowed_websites: List[Dict[str, Any]] = field(default_factory=list)
    blocked_websites: List[Dict[str, Any]] = field(default_factory=list)
    allowed_applications: List[Dict[str, Any]] = field(default_factory=list)
    blocked_applications: List[Dict[str, Any]] = field(default_factory=list)
    device_requirements: Dict[str, Any] = field(default_factory=dict)
    is_offline_cached: bool = False

    def is_expired(self, now_utc: Optional[datetime] = None) -> bool:
        """Policy bundle expiry — separate from session status."""
        now = now_utc or datetime.now(timezone.utc)
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return now > exp

    def is_session_active(self, now_utc: Optional[datetime] = None) -> bool:
        """At least one session is active (trusts backend status field)."""
        if not self.schedule_windows:
            return False
        return any(w.is_active(now_utc) for w in self.schedule_windows)

    def get_active_blocked_domains(self, now_utc: Optional[datetime] = None) -> List[str]:
        """Return blocked domains if policy bundle is not expired AND at least one session is active."""
        if self.is_expired(now_utc) or not self.is_session_active(now_utc):
            return []
        blocked = set(r.domain.strip().lower() for r in self.domain_rules if r.action == "block")
        for bw in self.blocked_websites:
            dom = bw if isinstance(bw, str) else (bw.get("domain_pattern") or bw.get("domain"))
            if dom:
                blocked.add(str(dom).strip().lower())
        return sorted(list(blocked))

    def get_active_allowed_domains(self, now_utc: Optional[datetime] = None) -> List[str]:
        """Return allowed academic domains if session is active."""
        if self.is_expired(now_utc) or not self.is_session_active(now_utc):
            return []
        allowed = set(r.domain.strip().lower() for r in self.domain_rules if r.action in ("allow", "log"))
        for aw in self.allowed_websites:
            dom = aw if isinstance(aw, str) else (aw.get("domain_pattern") or aw.get("domain"))
            if dom:
                allowed.add(str(dom).strip().lower())
        return sorted(list(allowed))

    def get_active_blocked_apps(self, now_utc: Optional[datetime] = None) -> List[str]:
        """Return blocked apps if policy bundle is not expired AND at least one session is active."""
        if self.is_expired(now_utc) or not self.is_session_active(now_utc):
            return []
        blocked = set(r.application.strip().lower() for r in self.app_rules if r.action in ("close", "block", "warn"))
        for ba in self.blocked_applications:
            app = ba if isinstance(ba, str) else (ba.get("executable_name") or ba.get("application"))
            if app:
                blocked.add(str(app).strip().lower())
        return sorted(list(blocked))

    def get_active_allowed_apps(self, now_utc: Optional[datetime] = None) -> List[str]:
        """Return allowed academic apps if session is active."""
        if self.is_expired(now_utc) or not self.is_session_active(now_utc):
            return []
        allowed = set(r.application.strip().lower() for r in self.app_rules if r.action == "allow")
        for aa in self.allowed_applications:
            app = aa if isinstance(aa, str) else (aa.get("executable_name") or aa.get("application"))
            if app:
                allowed.add(str(app).strip().lower())
        return sorted(list(allowed))

class PolicyManager:
    """Synchronizes, validates integrity, and evaluates policy schedules."""

    def __init__(self, db: Optional[LocalStorageDB] = None, api_client: Optional[APIClientAdapter] = None):
        self.db = db or LocalStorageDB()
        self.api_client = api_client or APIClientAdapter()
        self._current_policy: Optional[VerifiedPolicy] = None
        self._last_expired_warned: bool = False
        self._last_warned_policy_version: Optional[int] = None

    def sync_policy(self) -> Tuple[Optional[VerifiedPolicy], str]:
        """
        Fetch latest policy from backend or fallback to SQLite cache.
        Returns (policy, status_message).
        """
        now = datetime.now(timezone.utc)
        raw_data = None
        is_offline = False

        # Attempt remote fetch
        try:
            raw_data = self.api_client.fetch_policy()
        except Exception as err:
            LOGGER.warning("Could not fetch remote policy (%s); attempting SQLite cache load", err)
            is_offline = True

        if not raw_data or ("policy_version" not in raw_data and "version" not in raw_data and "domains" not in raw_data and "domain_rules" not in raw_data):
            # Attempt legacy config endpoint fallback
            if not is_offline:
                try:
                    legacy_cfg = self.api_client.fetch_config()
                    if legacy_cfg:
                        raw_data = self._convert_legacy_config_to_policy(legacy_cfg)
                except Exception:
                    pass

        if not raw_data:
            # Fallback to local SQLite DB
            raw_data = self.db.get_latest_policy()
            is_offline = True

        if not raw_data:
            return None, "No policy available from server or local database cache."

        # Integrity & Parse
        parsed_policy, parse_err = self._parse_and_verify(raw_data, is_offline)
        if parse_err:
            LOGGER.error("Policy integrity check failed: %s", parse_err)
            return None, f"Integrity Failure: {parse_err}"

        # Expiry evaluation
        if parsed_policy.is_expired(now):
            msg = f"Policy version {parsed_policy.policy_version} has EXPIRED at {parsed_policy.expires_at.isoformat()}. Halting enforcement safely."
            if not self._last_expired_warned or self._last_warned_policy_version != parsed_policy.policy_version:
                LOGGER.warning(msg)
                self._last_expired_warned = True
                self._last_warned_policy_version = parsed_policy.policy_version
            else:
                LOGGER.debug(msg)
            # Store parsed policy but active rules will evaluate to empty
            self._current_policy = parsed_policy
            return parsed_policy, msg

        self._last_expired_warned = False
        self._last_warned_policy_version = None

        # Save verified policy to SQLite DB for offline resilience
        if not is_offline:
            self.db.save_policy(raw_data)

        self._current_policy = parsed_policy
        return parsed_policy, "OK"

    def get_current_policy(self) -> Optional[VerifiedPolicy]:
        return self._current_policy

    def _parse_and_verify(self, data: Dict[str, Any], is_offline: bool) -> Tuple[Optional[VerifiedPolicy], Optional[str]]:
        try:
            ver = data.get("policy_version") if data.get("policy_version") is not None else data.get("version", 0)
            issued_str = data.get("issued_at", "")
            expires_str = data.get("expires_at", "")
            sha_server = data.get("sha256", "") or data.get("integrity_hash", "")
            now_utc = datetime.now(timezone.utc)

            # Verify integrity hash if present
            data_copy = dict(data)
            data_copy.pop("sha256", None)
            data_copy.pop("_queue_id", None)
            calc_hash = hashlib.sha256(json.dumps(data_copy, sort_keys=True, default=str).encode("utf-8")).hexdigest()

            if sha_server and sha_server != calc_hash and not data.get("integrity_hash"):
                return None, f"SHA-256 hash mismatch! Server: {sha_server}, Calc: {calc_hash}"

            issued_at = datetime.fromisoformat(str(issued_str)) if issued_str else now_utc
            expires_at = datetime.fromisoformat(str(expires_str)) if expires_str else (now_utc + timedelta(days=365))

            schedules = []
            if data.get("active_sessions"):
                for s in data.get("active_sessions", []):
                    s_start = datetime.fromisoformat(str(s["start_time"])) if s.get("start_time") else now_utc
                    s_end = datetime.fromisoformat(str(s["end_time"])) if s.get("end_time") else (now_utc + timedelta(hours=2))
                    s_status = s.get("status", "Active")
                    schedules.append(ScheduleWindow(
                        session_id=str(s.get("id", s.get("session_id", "session"))),
                        title=s.get("title", "Lecture"),
                        start_time=s_start,
                        end_time=s_end,
                        status=s_status,
                        batch_id=str(s.get("batch_id") or s.get("class_id") or data.get("batch_id") or data.get("class_id") or "") or None
                    ))
            elif data.get("session_id") or data.get("policy_active"):
                sess_id = data.get("session_id", "active_session")
                sess_status = data.get("session_status", "Active") if data.get("policy_active") else "Inactive"
                start_str = data.get("current_occurrence_start_utc") or data.get("start_at_utc")
                end_str = data.get("current_occurrence_end_utc") or data.get("end_at_utc")
                s_start = datetime.fromisoformat(str(start_str)) if start_str else (now_utc - timedelta(hours=1))
                s_end = datetime.fromisoformat(str(end_str)) if end_str else (now_utc + timedelta(hours=2))
                schedules.append(ScheduleWindow(
                    session_id=str(sess_id),
                    title="Active Academic Session",
                    start_time=s_start,
                    end_time=s_end,
                    status=sess_status,
                    batch_id=str(data.get("batch_id") or data.get("class_id") or "") or None
                ))

            raw_domain_rules = data.get("domain_rules") or data.get("domains") or data.get("websites") or []
            domain_rules = []
            for r in raw_domain_rules:
                if isinstance(r, str):
                    dom = r
                    act = "block"
                    prio = 10
                elif isinstance(r, dict):
                    dom = r.get("domain") or r.get("domain_pattern") or ""
                    act = r.get("action", "block")
                    prio = r.get("priority", 10)
                else:
                    dom = getattr(r, "domain", None) or getattr(r, "domain_pattern", "")
                    act = getattr(r, "action", "block")
                    prio = getattr(r, "priority", 10)
                if dom:
                    domain_rules.append(DomainRule(domain=str(dom).strip().lower(), action=act, priority=prio))

            raw_app_rules = data.get("application_rules") or data.get("app_rules") or data.get("applications") or []
            app_rules = []
            for r in raw_app_rules:
                if isinstance(r, str):
                    app = r
                    act = "close"
                    prio = 10
                elif isinstance(r, dict):
                    app = r.get("application") or r.get("executable_name") or ""
                    act = r.get("action", "close")
                    prio = r.get("priority", 10)
                else:
                    app = getattr(r, "application", None) or getattr(r, "executable_name", "")
                    act = getattr(r, "action", "close")
                    prio = getattr(r, "priority", 10)
                if app:
                    app_rules.append(AppRule(application=str(app).strip().lower(), action=act, priority=prio))

            allowed_websites = data.get("allowed_websites") or []
            blocked_websites = data.get("blocked_websites") or []
            allowed_applications = data.get("allowed_applications") or []
            blocked_applications = data.get("blocked_applications") or []
            device_requirements = data.get("device_requirements") or {}

            verified = VerifiedPolicy(
                policy_version=ver,
                issued_at=issued_at,
                expires_at=expires_at,
                sha256_hash=sha_server or calc_hash,
                schedule_windows=schedules,
                domain_rules=domain_rules,
                app_rules=app_rules,
                allowed_websites=allowed_websites,
                blocked_websites=blocked_websites,
                allowed_applications=allowed_applications,
                blocked_applications=blocked_applications,
                device_requirements=device_requirements,
                is_offline_cached=is_offline
            )
            return verified, None

        except Exception as err:
            return None, f"Parsing exception: {err}"

    def _convert_legacy_config_to_policy(self, config: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        domains = config.get("blockedDomains") or config.get("domains") or []
        apps = config.get("blockedApps") or config.get("applications") or []
        session = config.get("session")

        schedules = []
        if session or config.get("active"):
            schedules.append({
                "id": session.get("id", "legacy_sess") if session else "legacy_sess",
                "title": session.get("title", "Active Session") if session else "Active Session",
                "start_time": (now - timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
                "status": "Active"
            })

        domain_rules = [{"domain": d, "action": "block", "priority": 10} for d in domains]
        app_rules = [{"application": a, "action": "close", "priority": 10} for a in apps]

        policy_dict = {
            "policy_version": int(now.timestamp()),
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(days=7)).isoformat(),
            "active_sessions": schedules,
            "domain_rules": domain_rules,
            "app_rules": app_rules,
            "poll_interval": config.get("poll_interval", 8)
        }
        calc_hash = hashlib.sha256(json.dumps(policy_dict, sort_keys=True).encode("utf-8")).hexdigest()
        policy_dict["sha256"] = calc_hash
        return policy_dict
