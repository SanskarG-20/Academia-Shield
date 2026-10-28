"""
Tests for Policy Domain Rule Matching & Priority Engine.
"""

from agent.dns.rules import DomainRuleMatcher, PolicyDomainRule

def test_exact_and_wildcard_matching():
    matcher = DomainRuleMatcher()
    rules = [
        PolicyDomainRule(rule_id="r1", domain_pattern="facebook.com", rule_type="exact", action="block", priority=10),
        PolicyDomainRule(rule_id="r2", domain_pattern="*.youtube.com", rule_type="wildcard", action="block", priority=10),
    ]
    matcher.set_rules(rules)

    # 1. Exact match
    act1, rule1 = matcher.evaluate_qname("facebook.com")
    assert act1 == "block"
    assert rule1.rule_id == "r1"

    # 2. Subdomain wildcard match
    act2, rule2 = matcher.evaluate_qname("music.youtube.com")
    assert act2 == "block"
    assert rule2.rule_id == "r2"

    # Base domain of wildcard match
    act3, rule3 = matcher.evaluate_qname("youtube.com")
    assert act3 == "block"

    # Unmatched domain
    act4, rule4 = matcher.evaluate_qname("wikipedia.org")
    assert act4 == "pass"
    assert rule4 is None

def test_rule_priority_and_explicit_allow_override():
    matcher = DomainRuleMatcher()
    rules = [
        # Broader block rule (Priority 10)
        PolicyDomainRule(rule_id="r_block", domain_pattern="*.example.com", rule_type="wildcard", action="block", priority=10),
        # Specific allow override (Priority 20)
        PolicyDomainRule(rule_id="r_allow", domain_pattern="api.example.com", rule_type="exact", action="allow", priority=20),
    ]
    matcher.set_rules(rules)

    # Specific sub-domain with higher priority explicit allow
    act1, rule1 = matcher.evaluate_qname("api.example.com")
    assert act1 == "allow"
    assert rule1.rule_id == "r_allow"

    # Other sub-domain hit by broader lower priority block
    act2, rule2 = matcher.evaluate_qname("games.example.com")
    assert act2 == "block"
    assert rule2.rule_id == "r_block"
