"""
Policy-Driven Domain Rule Matching Engine.

Supports exact domain rules, wildcard/subdomain matching, IDNA punycode normalization,
and deterministic rule priority resolution.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from .protocol import normalize_domain_name

LOGGER = logging.getLogger(__name__)

@dataclass
class PolicyDomainRule:
    rule_id: str
    domain_pattern: str
    rule_type: str  # exact, wildcard
    action: str  # block, allow, log
    priority: int = 10
    is_enabled: bool = True
    reason: Optional[str] = None

class DomainRuleMatcher:
    """Matches requested QNAME against backend domain policy rules using priority logic."""

    def __init__(self, rules: Optional[List[PolicyDomainRule]] = None):
        self.rules: List[PolicyDomainRule] = []
        if rules:
            self.set_rules(rules)

    def set_rules(self, rules: List[PolicyDomainRule]) -> None:
        """Set and normalize domain policy rules."""
        cleaned_rules = []
        for r in rules:
            if not r.is_enabled:
                continue
            normalized_pat = normalize_domain_name(r.domain_pattern)
            rule_type = r.rule_type.lower() if r.rule_type else ("wildcard" if r.domain_pattern.startswith("*.") else "exact")
            
            # If pattern starts with wildcard prefix *. or *, clean it
            if normalized_pat.startswith("*."):
                normalized_pat = normalized_pat[2:]
                rule_type = "wildcard"
            elif normalized_pat.startswith("*"):
                normalized_pat = normalized_pat[1:].lstrip(".")
                rule_type = "wildcard"

            cleaned_rules.append(PolicyDomainRule(
                rule_id=r.rule_id,
                domain_pattern=normalized_pat,
                rule_type=rule_type,
                action=r.action.lower(),
                priority=r.priority,
                is_enabled=r.is_enabled,
                reason=r.reason
            ))

        # Sort rules descending by priority
        self.rules = sorted(cleaned_rules, key=lambda item: item.priority, reverse=True)

    def evaluate_qname(self, qname: str) -> Tuple[str, Optional[PolicyDomainRule]]:
        """
        Evaluate domain request against active policy rules.
        Returns (action, matched_rule) where action is 'block', 'allow', or 'pass'.
        Higher priority rules evaluate first. An explicit allow overrides a broader block
        only when it has a higher priority.
        """
        clean_qname = normalize_domain_name(qname)
        if not clean_qname:
            return "pass", None

        for rule in self.rules:
            if self._matches_rule(clean_qname, rule):
                return rule.action, rule

        return "pass", None

    def _matches_rule(self, qname: str, rule: PolicyDomainRule) -> bool:
        pattern = rule.domain_pattern
        if not pattern:
            return False

        if rule.rule_type == "exact":
            return qname == pattern
        elif rule.rule_type == "wildcard":
            # Wildcard *.example.com matches sub.example.com AND example.com
            return qname == pattern or qname.endswith("." + pattern)

        return False
