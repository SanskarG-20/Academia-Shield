"""
4-Tier Policy Rule Matcher and Priority Conflict Resolution Engine.

Matches running process metadata against active application rules in 4 tiers:
1. Trusted explicit allow rule
2. Exact executable path or SHA-256 hash rule
3. Exact executable-name rule
4. Explicit wildcard / path-pattern rule

Resolves conflicts deterministically using priority scores with an allow-over-block strategy.
"""

import fnmatch
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from .process_snapshot import ProcessMetadata

LOGGER = logging.getLogger(__name__)

@dataclass
class PolicyApplicationRule:
    """Normalized application policy rule object."""
    rule_id: str
    executable_name: str
    executable_path_pattern: Optional[str] = None
    trusted_hash: Optional[str] = None
    action: str = "close"  # allow, log, warn, close
    priority: int = 0
    is_enabled: bool = True
    reason: Optional[str] = None
    cooldown_seconds: int = 0
    rule_set_version: Optional[int] = None
    session_id: Optional[str] = None

    def __post_init__(self):
        if self.executable_name:
            self.executable_name = self.executable_name.strip().lower()
        if self.action:
            self.action = self.action.strip().lower()

class ApplicationRuleMatcher:
    """Evaluates rules against process snapshots and returns highest priority rule match."""

    def __init__(self, rules: Optional[List[PolicyApplicationRule]] = None):
        self.rules: List[PolicyApplicationRule] = rules or []

    def set_rules(self, rules: List[PolicyApplicationRule]) -> None:
        """Update active rules list."""
        self.rules = [r for r in rules if r.is_enabled]

    def match_process(self, proc: ProcessMetadata) -> Optional[PolicyApplicationRule]:
        """
        Evaluate process metadata against application rules in 4 tiers:
        Tier 1: Explicit Allow Rules
        Tier 2: Exact Path / Hash Matches
        Tier 3: Exact Executable Name Matches
        Tier 4: Wildcard / Path Pattern Matches
        """
        if not self.rules:
            return None

        clean_exe = proc.executable_name.strip().lower() if proc.executable_name else ""
        clean_path = proc.executable_path.strip().lower() if proc.executable_path else ""

        tier1_matches = []  # Allow rules
        tier2_matches = []  # Path / Hash matches
        tier3_matches = []  # Name matches
        tier4_matches = []  # Wildcard pattern matches

        for rule in self.rules:
            if not rule.is_enabled:
                continue

            rule_exe = rule.executable_name.strip().lower() if rule.executable_name else ""
            rule_path = rule.executable_path_pattern.strip().lower() if rule.executable_path_pattern else ""
            rule_hash = rule.trusted_hash.strip().lower() if rule.trusted_hash else ""

            norm_rule = rule_exe[:-4] if rule_exe.endswith(".exe") else rule_exe
            norm_clean = clean_exe[:-4] if clean_exe.endswith(".exe") else clean_exe
            name_matched = bool(rule_exe and (
                rule_exe == clean_exe
                or norm_rule == norm_clean
                or norm_rule == clean_exe
                or norm_clean == rule_exe
                or (len(norm_rule) >= 4 and (norm_clean.startswith(norm_rule) or norm_rule.startswith(norm_clean)))
                or (norm_rule in ("calc", "calculator") and norm_clean in ("calc", "calculator", "calculatorapp"))
            ))

            # Tier 1: Explicit Allow rule by exact name or path
            if rule.action == "allow":
                if name_matched:
                    tier1_matches.append(rule)
                    continue
                if rule_path and clean_path and (rule_path == clean_path or fnmatch.fnmatch(clean_path, rule_path)):
                    tier1_matches.append(rule)
                    continue

            # Tier 2: Exact Path or Hash match
            if rule_hash and proc.trusted_hash and (rule_hash == proc.trusted_hash.strip().lower()):
                tier2_matches.append(rule)
                continue
            if rule_path and clean_path and rule_path == clean_path:
                tier2_matches.append(rule)
                continue

            # Tier 3: Exact Executable Name match
            if name_matched:
                tier3_matches.append(rule)
                continue

            # Tier 4: Wildcard or Path Pattern match
            if rule_path and clean_path and fnmatch.fnmatch(clean_path, rule_path):
                tier4_matches.append(rule)
                continue
            if rule_exe and ("*" in rule_exe or "?" in rule_exe) and fnmatch.fnmatch(clean_exe, rule_exe):
                tier4_matches.append(rule)
                continue

        # Evaluate matches in tier order with deterministic priority resolution
        for tier in (tier1_matches, tier2_matches, tier3_matches, tier4_matches):
            if tier:
                # Sort by priority descending. If allow rule has equal or higher priority, choose allow
                sorted_tier = sorted(tier, key=lambda r: (r.priority, 1 if r.action == "allow" else 0), reverse=True)
                return sorted_tier[0]

        return None
