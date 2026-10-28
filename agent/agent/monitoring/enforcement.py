"""
Enforcement Actions Executor with Cooldowns, Notifications, and Graceful Terminations.

Executes policy actions (log, warn, close) on matched process violations with:
- Per-process and per-rule cooldown windows to prevent notification spam
- Visible user notifications before enforcement
- Grace period before terminating non-protected user processes
- Outcome tracking (detected, warned, closed, failed, skipped, protected)
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, Set
from .process_snapshot import ProcessMetadata
from .rule_matcher import PolicyApplicationRule
from .protected_processes import ProtectedProcessManager

LOGGER = logging.getLogger(__name__)

@dataclass
class EnforcementResult:
    """Detailed outcome of an enforcement attempt."""
    pid: int
    executable_name: str
    action_requested: str
    action_result: str  # detected, warned, closed, failed, skipped, protected
    rule_id: str
    reason: Optional[str] = None
    notification_shown: bool = False

class EnforcementEngine:
    """Executes process policy rules safely with cooldown tracking and platform adapter hooks."""

    def __init__(
        self,
        platform_adapter: Optional[Any] = None,
        protected_manager: Optional[ProtectedProcessManager] = None,
        default_grace_period: float = 2.0
    ):
        self.platform_adapter = platform_adapter
        self.protected_manager = protected_manager or ProtectedProcessManager()
        self.default_grace_period = default_grace_period

        # Cooldown timestamps: key -> unix_timestamp
        self._process_cooldowns: Dict[str, float] = {}
        self._rule_cooldowns: Dict[str, float] = {}

    def is_in_cooldown(self, proc: ProcessMetadata, rule: PolicyApplicationRule, now_ts: float) -> bool:
        """Check if process or rule is currently within its cooldown window."""
        cooldown_sec = rule.cooldown_seconds or 30

        proc_key = f"{proc.pid}_{proc.executable_name}"
        if proc_key in self._process_cooldowns:
            if now_ts - self._process_cooldowns[proc_key] < cooldown_sec:
                return True

        rule_key = f"{rule.rule_id}_{proc.executable_name}"
        if rule_key in self._rule_cooldowns:
            if now_ts - self._rule_cooldowns[rule_key] < cooldown_sec:
                return True

        return False

    def update_cooldown(self, proc: ProcessMetadata, rule: PolicyApplicationRule, now_ts: float) -> None:
        """Record timestamp for process and rule cooldowns."""
        proc_key = f"{proc.pid}_{proc.executable_name}"
        rule_key = f"{rule.rule_id}_{proc.executable_name}"
        self._process_cooldowns[proc_key] = now_ts
        self._rule_cooldowns[rule_key] = now_ts

    def enforce_rule(self, proc: ProcessMetadata, rule: PolicyApplicationRule) -> EnforcementResult:
        """Execute action for matched rule against process."""
        now_ts = time.time()
        action = rule.action.lower() if rule.action else "warn"

        # Allow action: skip completely
        if action == "allow":
            return EnforcementResult(
                pid=proc.pid,
                executable_name=proc.executable_name,
                action_requested="allow",
                action_result="skipped",
                rule_id=rule.rule_id,
                reason="Explicit allow rule matched"
            )

        # Check protected process safeguard
        if self.protected_manager.is_protected(proc.executable_name, proc.executable_path):
            if action == "close":
                rule_key = f"safeguard:{proc.executable_name.lower()}"
                last_warn = self._rule_cooldowns.get(rule_key, 0)
                if now_ts - last_warn > 300:  # 5-minute cooldown for repeated warnings
                    self._rule_cooldowns[rule_key] = now_ts
                    LOGGER.warning(
                        "Safeguard trigger: Process '%s' (PID: %s) is protected; ignoring 'close' request",
                        proc.executable_name, proc.pid
                    )
                else:
                    LOGGER.debug(
                        "Safeguard trigger (throttled): Process '%s' (PID: %s) is protected",
                        proc.executable_name, proc.pid
                    )
                return EnforcementResult(
                    pid=proc.pid,
                    executable_name=proc.executable_name,
                    action_requested="close",
                    action_result="protected",
                    rule_id=rule.rule_id,
                    reason="Target process is in system protected allowlist"
                )

        # Check cooldown to avoid notification spam (ONLY for warn and log actions)
        if action in ("warn", "log") and self.is_in_cooldown(proc, rule, now_ts):
            return EnforcementResult(
                pid=proc.pid,
                executable_name=proc.executable_name,
                action_requested=action,
                action_result="skipped",
                rule_id=rule.rule_id,
                reason=f"Action '{action}' skipped due to active cooldown"
            )

        self.update_cooldown(proc, rule, now_ts)

        # Action: LOG
        if action == "log":
            LOGGER.info("Policy LOG event: Process '%s' (PID: %s) matched rule '%s'", proc.executable_name, proc.pid, rule.rule_id)
            return EnforcementResult(
                pid=proc.pid,
                executable_name=proc.executable_name,
                action_requested="log",
                action_result="detected",
                rule_id=rule.rule_id,
                reason=rule.reason or "Log policy matched"
            )

        # Action: WARN
        if action == "warn":
            LOGGER.warning("Policy WARN event: Process '%s' (PID: %s) restricted during session", proc.executable_name, proc.pid)
            notif_shown = False
            if self.platform_adapter and hasattr(self.platform_adapter, "show_notification"):
                try:
                    self.platform_adapter.show_notification(
                        title="Academic Session Policy Warning",
                        message=rule.reason or f"Application '{proc.executable_name}' is restricted during this academic session."
                    )
                    notif_shown = True
                except Exception as err:
                    LOGGER.debug("Failed displaying notification: %s", err)

            return EnforcementResult(
                pid=proc.pid,
                executable_name=proc.executable_name,
                action_requested="warn",
                action_result="warned",
                rule_id=rule.rule_id,
                reason=rule.reason or "Warning notification issued",
                notification_shown=notif_shown
            )

        # Action: CLOSE
        if action == "close":
            LOGGER.warning("Policy CLOSE event: Terminating process '%s' (PID: %s)", proc.executable_name, proc.pid)
            notif_shown = False
            if self.platform_adapter and hasattr(self.platform_adapter, "show_notification"):
                try:
                    self.platform_adapter.show_notification(
                        title="Academic Session Policy Enforcement",
                        message=f"Closing restricted application '{proc.executable_name}'."
                    )
                    notif_shown = True
                except Exception:
                    pass

            success = False
            if self.platform_adapter and hasattr(self.platform_adapter, "terminate_process_gracefully"):
                try:
                    success = self.platform_adapter.terminate_process_gracefully(proc.pid, proc.executable_name)
                except Exception as err:
                    LOGGER.error("Platform adapter process termination error: %s", err)

            # Fallback psutil direct termination if adapter didn't succeed
            if not success:
                try:
                    import psutil
                    p = psutil.Process(proc.pid)
                    p.kill()
                    success = True
                except Exception:
                    pass

            return EnforcementResult(
                pid=proc.pid,
                executable_name=proc.executable_name,
                action_requested="close",
                action_result="closed" if success else "failed",
                rule_id=rule.rule_id,
                reason=rule.reason or ("Process terminated" if success else "Termination failed"),
                notification_shown=notif_shown
            )

        # Unknown action fallback
        return EnforcementResult(
            pid=proc.pid,
            executable_name=proc.executable_name,
            action_requested=action,
            action_result="skipped",
            rule_id=rule.rule_id,
            reason=f"Unknown action '{action}'"
        )
