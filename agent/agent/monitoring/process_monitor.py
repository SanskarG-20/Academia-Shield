"""
Main Process Monitor Orchestrator for Academia Shield Local Agent.

Integrates process scanning, 4-tier rule matching, protected process safeguards,
enforcement action execution, and reliable privacy-minimized telemetry dispatch.
"""

import sys
import time
import logging
from typing import Optional, List, Dict, Any, Set
from ..config import get_config
from ..platform import get_platform_adapter, BasePlatformAdapter
from ..platform.windows_foreground import WindowsForegroundDetector
from ..telemetry.telemetry_manager import TelemetryManager
from ..telemetry.application_events import ApplicationTelemetryBuilder
from ..policy.policy_manager import VerifiedPolicy
from .process_snapshot import ProcessScanner, ProcessMetadata
from .protected_processes import ProtectedProcessManager
from .rule_matcher import ApplicationRuleMatcher, PolicyApplicationRule
from .enforcement import EnforcementEngine, EnforcementResult

LOGGER = logging.getLogger(__name__)

class ProcessMonitor:
    """Monitors running applications and applies active policy enforcement."""

    def __init__(
        self,
        platform_adapter: Optional[BasePlatformAdapter] = None,
        telemetry_manager: Optional[TelemetryManager] = None,
        scanner: Optional[ProcessScanner] = None,
        rule_matcher: Optional[ApplicationRuleMatcher] = None,
        enforcement_engine: Optional[EnforcementEngine] = None,
        protected_manager: Optional[ProtectedProcessManager] = None
    ):
        self.config = get_config()
        self.platform_adapter = platform_adapter or get_platform_adapter()
        self.telemetry_manager = telemetry_manager or TelemetryManager()
        
        is_win = (sys.platform == "win32")
        fg_detector = WindowsForegroundDetector() if is_win else None
        self.scanner = scanner or ProcessScanner(foreground_detector=fg_detector)
        
        self.protected_manager = protected_manager or ProtectedProcessManager()
        self.rule_matcher = rule_matcher or ApplicationRuleMatcher()
        self.enforcement_engine = enforcement_engine or EnforcementEngine(
            platform_adapter=self.platform_adapter,
            protected_manager=self.protected_manager
        )

        self._scan_count = 0
        self._last_scan_duration_ms = 0.0
        self._domain_violation_cooldowns: Dict[str, float] = {}
        self._app_violation_cooldowns: Dict[str, float] = {}

    def parse_app_rules_from_policy(self, policy: VerifiedPolicy) -> List[PolicyApplicationRule]:
        """Convert policy app_rules into PolicyApplicationRule list, excluding allowed applications."""
        parsed_rules = []
        raw_rules = list(getattr(policy, "app_rules", []) or [])
        if getattr(policy, "application_rules", None):
            raw_rules.extend(policy.application_rules)
        for ba in (getattr(policy, "blocked_applications", []) or []):
            if isinstance(ba, str):
                raw_rules.append({"executable_name": ba, "action": "close", "rule_mode": "blocked"})
            elif isinstance(ba, dict):
                raw_rules.append(ba)
        for app in (getattr(policy, "apps", []) or []):
            if isinstance(app, str):
                raw_rules.append({"executable_name": app, "action": "close", "rule_mode": "blocked"})
            elif isinstance(app, dict):
                raw_rules.append(app)

        # Collect allowed applications from policy
        allowed_apps = set()
        if hasattr(policy, "get_active_allowed_apps"):
            allowed_apps.update(a.strip().lower() for a in policy.get_active_allowed_apps() if a)
        for aa in getattr(policy, "allowed_applications", []) or []:
            name = aa if isinstance(aa, str) else (aa.get("executable_name") or aa.get("application") or "")
            if name:
                allowed_apps.add(str(name).strip().lower())

        for r in raw_rules:
            if isinstance(r, dict):
                name = r.get("executable_name") or r.get("application") or ""
                path_pat = r.get("executable_path_pattern")
                t_hash = r.get("trusted_hash")
                rule_mode = r.get("rule_mode")
                act = r.get("action", "close")
                prio = r.get("priority", 0)
                enabled = r.get("is_enabled", True)
                reason = r.get("reason")
                cd_sec = r.get("cooldown_seconds", 30)
                r_id = r.get("rule_id") or r.get("id") or f"rule_{name}"
            else:
                name = getattr(r, "executable_name", None) or getattr(r, "application", "")
                path_pat = getattr(r, "executable_path_pattern", None)
                t_hash = getattr(r, "trusted_hash", None)
                rule_mode = getattr(r, "rule_mode", None)
                act = getattr(r, "action", "close")
                prio = getattr(r, "priority", 0)
                enabled = getattr(r, "is_enabled", True)
                reason = getattr(r, "reason", None)
                cd_sec = getattr(r, "cooldown_seconds", 30)
                r_id = getattr(r, "rule_id", None) or getattr(r, "id", None) or f"rule_{name}"

            if not name:
                continue

            clean_name = str(name).strip().lower()

            # Skip allowed applications entirely from blocking/enforcement rules
            if rule_mode == "allowed" or clean_name in allowed_apps or str(act).lower() in ("allow", "allowed"):
                LOGGER.debug("Skipping enforcement for allowed application '%s'", name)
                continue

            # Skip close rules for system protected processes (e.g. web browsers, OS services)
            if str(act).lower() == "close" and self.protected_manager.is_protected(clean_name):
                LOGGER.debug("Skipping close rule for protected process '%s'", name)
                continue

            parsed_rules.append(PolicyApplicationRule(
                rule_id=str(r_id),
                executable_name=str(name),
                executable_path_pattern=path_pat,
                trusted_hash=t_hash,
                action=str(act),
                priority=int(prio),
                is_enabled=bool(enabled),
                reason=reason,
                cooldown_seconds=int(cd_sec),
                rule_set_version=getattr(policy, "policy_version", None),
                session_id=policy.schedule_windows[0].session_id if policy.schedule_windows else None
            ))

        return parsed_rules

    def scan_and_enforce(self, policy: VerifiedPolicy) -> List[Dict[str, Any]]:
        """
        Scan running processes and active foreground browser window against active policy rules.
        Returns list of matched violation event dictionaries.
        """
        start_time = time.time()
        self._scan_count += 1

        # Check if policy is active and unexpired
        if not policy or policy.is_expired() or not policy.is_session_active():
            LOGGER.debug("Process monitor enforcement inactive (policy expired or no active session)")
            return []

        # Update protected process allowlist from policy
        server_protected = getattr(policy, "protected_processes", []) or []
        self.protected_manager.update_from_policy(server_protected)

        # Collect allowed applications from policy
        allowed_apps = set()
        if hasattr(policy, "get_active_allowed_apps"):
            allowed_apps.update(a.strip().lower() for a in policy.get_active_allowed_apps() if a)
        for aa in getattr(policy, "allowed_applications", []) or []:
            name = aa if isinstance(aa, str) else (aa.get("executable_name") or aa.get("application") or "")
            if name:
                allowed_apps.add(str(name).strip().lower())

        violations: List[Dict[str, Any]] = []
        device_id = getattr(self.config, "device_id", "local_agent_device")
        active_win = next((w for w in policy.schedule_windows if w.is_active()), None) if policy.schedule_windows else None
        session_id = active_win.session_id if active_win else (policy.schedule_windows[0].session_id if policy.schedule_windows else None)

        # 1. Parse application rules and scan processes if rules are configured
        app_rules = self.parse_app_rules_from_policy(policy)
        if app_rules:
            self.rule_matcher.set_rules(app_rules)
            proc_snapshots = self.scanner.scan_processes()

            # Group matched processes by executable name so multi-process apps (e.g., code.exe with 20+ child processes)
            # are fully terminated, but emit exactly 1 violation event per launch incident
            enforced_apps_this_scan: Set[str] = set()

            for proc in proc_snapshots:
                exe_clean = (getattr(proc, "executable_name", None) or "").strip().lower()
                # If application is allowed or system protected, never match or terminate
                if exe_clean in allowed_apps or self.protected_manager.is_protected(exe_clean):
                    continue

                matched_rule = self.rule_matcher.match_process(proc)
                if not matched_rule:
                    continue

                result = self.enforcement_engine.enforce_rule(proc, matched_rule)
                if result.action_result in ("skipped", "allow", "protected"):
                    continue

                exe_clean = (getattr(proc, "executable_name", None) or getattr(result, "executable_name", None) or "").strip().lower()
                now_ts = time.time()
                last_app_viol = self._app_violation_cooldowns.get(exe_clean, 0.0)

                # Exactly 1 violation event per application within a 20-second cooldown window
                if exe_clean not in enforced_apps_this_scan and (now_ts - last_app_viol) >= 20.0:
                    enforced_apps_this_scan.add(exe_clean)
                    self._app_violation_cooldowns[exe_clean] = now_ts

                    event_dict = ApplicationTelemetryBuilder.build_violation_event(
                        result=result,
                        device_id=device_id,
                        session_id=session_id,
                        policy_version=policy.policy_version
                    )
                    violations.append(event_dict)

                    if self.telemetry_manager and hasattr(self.telemetry_manager, "record_violation_event"):
                        self.telemetry_manager.record_violation_event(
                            event_type="application_violation",
                            resource_name=exe_clean,
                            action=result.action_result or "blocked",
                            session_id=session_id,
                            rule_id=result.rule_id,
                            is_violation=True
                        )
                    elif self.telemetry_manager and hasattr(self.telemetry_manager, "db"):
                        self.telemetry_manager.db.enqueue_telemetry(
                            idempotency_key=event_dict["event_id"],
                            event_type=event_dict["event_type"],
                            payload=event_dict
                        )

        # 2. Check active foreground window for restricted websites (without terminating browser window)
        fg_detector = getattr(self.scanner, "foreground_detector", None)
        if fg_detector and hasattr(fg_detector, "get_foreground_window_title"):
            try:
                fg_title = fg_detector.get_foreground_window_title()
                if fg_title:
                    active_blocked_domains = policy.get_active_blocked_domains()
                    fg_title_lower = fg_title.lower()
                    for dom in active_blocked_domains:
                        dom_clean = dom.strip().lower()
                        base_keyword = dom_clean.split(".")[0]
                        matched = False
                        if dom_clean in fg_title_lower:
                            matched = True
                        elif len(base_keyword) >= 3 and base_keyword in fg_title_lower:
                            matched = True

                        if matched:
                            now_ts = time.time()
                            last_ts = self._domain_violation_cooldowns.get(dom_clean, 0.0)
                            # 20-second cooldown between duplicate violation telemetry dispatches for the same domain
                            if (now_ts - last_ts) >= 20.0:
                                self._domain_violation_cooldowns[dom_clean] = now_ts
                                LOGGER.info("Foreground browser active on restricted domain '%s' (title: '%s') - recording violation", dom_clean, fg_title)

                                if self.platform_adapter and hasattr(self.platform_adapter, "show_notification"):
                                    try:
                                        self.platform_adapter.show_notification(
                                            title="Academic Session Restriction",
                                            message=f"Access to '{dom_clean}' is restricted during this academic session."
                                        )
                                    except Exception:
                                        pass

                                # Record violation event in telemetry manager SQLite queue and flush immediately
                                if self.telemetry_manager and hasattr(self.telemetry_manager, "record_violation_event"):
                                    self.telemetry_manager.record_violation_event(
                                        event_type="dns_block",
                                        resource_name=dom_clean,
                                        action="blocked",
                                        session_id=session_id,
                                        rule_id=f"rule_domain_{dom_clean}"
                                    )

                                violations.append({
                                    "event_id": f"web-{int(now_ts)}-{dom_clean}",
                                    "event_type": "dns_block",
                                    "device_id": device_id,
                                    "session_id": session_id,
                                    "domain": dom_clean,
                                    "resource": dom_clean,
                                    "action": "blocked",
                                    "rule_id": f"rule_domain_{dom_clean}",
                                    "is_violation": True
                                })
                            # Handled this foreground match
                            break
            except Exception as err:
                LOGGER.debug("Foreground browser tab title check error: %s", err)

        # 3. Flush queued telemetry events to backend
        if violations:
            try:
                self.telemetry_manager.flush_queue()
            except Exception as err:
                LOGGER.debug("Telemetry queue flush error: %s", err)

        self._last_scan_duration_ms = (time.time() - start_time) * 1000.0
        return violations
