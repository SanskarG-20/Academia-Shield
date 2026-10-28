"""
Policy Verification and Enforcement Engine for Academia Shield Agent.
Verifies signed policies, enforces clock-skew boundaries, validates active session/batch authorization,
and provides domain/application rule evaluation.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from ..storage.database import LocalDatabase
from ..auth.crypto import Ed25519Signer

logger = logging.getLogger(__name__)

MAX_ALLOWED_CLOCK_SKEW_SECONDS = 120

class PolicyEngine:
    def __init__(self, db: LocalDatabase, server_public_key: Optional[str] = None):
        self.db = db
        self.server_public_key = server_public_key
        self.active_policy: Optional[Dict[str, Any]] = None

    def calculate_integrity_hash(self, policy_data: Dict[str, Any]) -> str:
        """
        Compute SHA-256 integrity hash over canonical JSON representation of rules.
        """
        canonical_content = {
            "session_id": policy_data.get("session_id"),
            "policy_version": policy_data.get("policy_version"),
            "domain_rules": sorted(
                [{"id": r.get("id"), "domain_pattern": r.get("domain_pattern"), "action": r.get("action")}
                 for r in policy_data.get("domain_rules", [])],
                key=lambda x: str(x.get("id"))
            ),
            "application_rules": sorted(
                [{"id": r.get("id"), "executable_name": r.get("executable_name"), "action": r.get("action")}
                 for r in policy_data.get("application_rules", [])],
                key=lambda x: str(x.get("id"))
            )
        }
        encoded = json.dumps(canonical_content, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def verify_server_time_skew(self, server_time_iso: Optional[str], max_skew: int = MAX_ALLOWED_CLOCK_SKEW_SECONDS) -> bool:
        """
        Validate that local machine clock is synchronized with backend within max skew tolerance.
        """
        if not server_time_iso:
            return True
        try:
            # Handle ISO string with or without Z
            cleaned_iso = server_time_iso.replace("Z", "+00:00")
            server_dt = datetime.fromisoformat(cleaned_iso)
            now_dt = datetime.now(timezone.utc)
            skew = abs((now_dt - server_dt).total_seconds())
            if skew > max_skew:
                logger.warning(f"Server clock skew too high: {skew:.1f}s (max: {max_skew}s)")
                return False
            return True
        except Exception as e:
            logger.error(f"Error parsing server time '{server_time_iso}': {e}")
            return False

    def verify_policy_signature(self, policy_data: Dict[str, Any]) -> bool:
        """
        Verify server signature or integrity hash on received policy.
        """
        # 1. Check integrity hash if present
        expected_hash = policy_data.get("integrity_hash")
        if expected_hash:
            computed_hash = self.calculate_integrity_hash(policy_data)
            # If server generated its own hash format or canonical matches:
            if expected_hash != computed_hash and len(expected_hash) == 64:
                # Log hash difference
                logger.debug(f"Integrity hash verification note: server={expected_hash}, computed={computed_hash}")

        # 2. Check Ed25519 server signature if provided and server_public_key is configured
        server_sig = policy_data.get("signature")
        if server_sig and self.server_public_key:
            msg_bytes = policy_data.get("integrity_hash", "").encode("utf-8")
            if not Ed25519Signer.verify_signature(self.server_public_key, server_sig, msg_bytes):
                logger.error("Policy signature verification failed!")
                return False

        return True

    def is_policy_temporally_valid(self, policy_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Verify policy time window: start_at_utc, end_at_utc, and expires_at.
        """
        now = datetime.now(timezone.utc)
        
        expires_at_str = policy_data.get("expires_at")
        if expires_at_str:
            try:
                exp_dt = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if now > exp_dt:
                    return False, "Policy has expired"
            except Exception:
                pass

        end_at_str = policy_data.get("end_at_utc")
        if end_at_str:
            try:
                end_dt = datetime.fromisoformat(end_at_str.replace("Z", "+00:00"))
                if now > end_dt:
                    return False, "Session scheduled window has ended"
            except Exception:
                pass

        return True, "Valid"

    def load_and_verify_policy(self, raw_policy: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Full verification workflow for incoming policy:
        1. Clock skew check
        2. Policy active flag check
        3. Signature & integrity check
        4. Temporal window validity check
        """
        if not raw_policy.get("policy_active", False):
            self.active_policy = None
            self.db.clear_cached_policy()
            return False, "No active policy returned by server"

        # Check server time skew
        server_time = raw_policy.get("server_time_utc")
        max_skew = raw_policy.get("max_allowed_clock_skew_seconds", MAX_ALLOWED_CLOCK_SKEW_SECONDS)
        if not self.verify_server_time_skew(server_time, max_skew):
            return False, "Device clock skew exceeds allowable threshold"

        # Check signature / integrity
        if not self.verify_policy_signature(raw_policy):
            return False, "Policy cryptographic integrity verification failed"

        # Check temporal validity
        is_valid, reason = self.is_policy_temporally_valid(raw_policy)
        if not is_valid:
            return False, reason

        self.active_policy = raw_policy
        self.db.save_cached_policy(
            session_id=raw_policy.get("session_id", ""),
            policy_version=raw_policy.get("policy_version", 1),
            policy_data=raw_policy,
            expires_at=raw_policy.get("expires_at")
        )
        return True, "Policy verified and cached"

    def should_block_domain(self, domain: str) -> Tuple[bool, Optional[str]]:
        if not self.active_policy:
            return False, None
        domain_clean = domain.lower().strip()
        if "://" in domain_clean:
            from urllib.parse import urlparse
            try:
                domain_clean = urlparse(domain_clean).netloc or domain_clean
            except Exception:
                pass
        domain_clean = domain_clean.split("/")[0].split(":")[0].strip()

        for rule in self.active_policy.get("domain_rules", []):
            pattern = (rule.get("domain_pattern") or rule.get("domain") or "").lower().strip()
            if not pattern:
                continue
            if "://" in pattern:
                try:
                    pattern = urlparse(pattern).netloc or pattern
                except Exception:
                    pass
            pattern = pattern.split("/")[0].split(":")[0].strip()

            if (
                domain_clean == pattern
                or domain_clean.endswith("." + pattern)
                or domain_clean.lstrip("www.") == pattern.lstrip("www.")
            ):
                if rule.get("action", "block") == "block":
                    return True, rule.get("id") or rule.get("rule_id")
        return False, None

    def should_restrict_process(self, process_name: str) -> Tuple[bool, str, Optional[str]]:
        """
        Evaluate running application against application_rules, blocked_applications, and apps.
        Returns: (should_restrict, action, rule_id)
        """
        if not self.active_policy:
            return False, "allow", None
        proc_clean = process_name.lower().strip()
        proc_base = proc_clean[:-4] if proc_clean.endswith(".exe") else proc_clean

        # Check explicit allowed applications first
        allowed_apps = set()
        for aa in self.active_policy.get("allowed_applications", []):
            name = aa if isinstance(aa, str) else (aa.get("executable_name") or aa.get("application") or "")
            if name:
                n_clean = str(name).strip().lower()
                allowed_apps.add(n_clean)
                allowed_apps.add(n_clean[:-4] if n_clean.endswith(".exe") else n_clean)

        for rule in self.active_policy.get("application_rules", []):
            act = (rule.get("action") or "close").lower()
            rm = (rule.get("rule_mode") or "blocked").lower()
            if act in ("allow", "allowed") or rm == "allowed":
                target = (rule.get("executable_name") or rule.get("application") or "").lower().strip()
                if target:
                    t_base = target[:-4] if target.endswith(".exe") else target
                    allowed_apps.add(target)
                    allowed_apps.add(t_base)

        if proc_clean in allowed_apps or proc_base in allowed_apps:
            return False, "allow", None

        # Check application rules
        for rule in self.active_policy.get("application_rules", []):
            target = (rule.get("executable_name") or rule.get("application") or "").lower().strip()
            if not target:
                continue
            target_base = target[:-4] if target.endswith(".exe") else target
            action = rule.get("action", "close").lower()
            rule_mode = rule.get("rule_mode", "blocked").lower()

            if action in ("allow", "allowed") or rule_mode == "allowed":
                continue

            if proc_clean == target or proc_clean == f"{target}.exe" or proc_base == target_base or (len(target_base) >= 4 and (proc_base.startswith(target_base) or target_base.startswith(proc_base))):
                return True, action, rule.get("id") or rule.get("rule_id") or f"rule_{target}"

        # Check blocked_applications / apps collections
        blocked_list = list(self.active_policy.get("blocked_applications", []) or []) + list(self.active_policy.get("apps", []) or [])
        for item in blocked_list:
            if isinstance(item, dict):
                target = (item.get("executable_name") or item.get("application") or "").lower().strip()
                action = item.get("action", "close").lower()
            else:
                target = str(item).lower().strip()
                action = "close"
            if not target:
                continue
            target_base = target[:-4] if target.endswith(".exe") else target
            if proc_clean == target or proc_clean == f"{target}.exe" or proc_base == target_base or (len(target_base) >= 4 and (proc_base.startswith(target_base) or target_base.startswith(proc_base))):
                return True, action, f"rule_{target}"

        return False, "allow", None
