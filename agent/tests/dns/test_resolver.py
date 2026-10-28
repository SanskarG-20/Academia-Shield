"""
Tests for Local UDP DNS Resolver Processing & NXDOMAIN Synthesis.
"""

from datetime import datetime, timezone
from agent.dns.resolver import LocalDNSResolver
from agent.dns.protocol import DNSPacket, DNSQuestion, RCODE_NXDOMAIN
from agent.policy import VerifiedPolicy, DomainRule, ScheduleWindow

def test_resolver_nxdomain_for_blocked_domain():
    resolver = LocalDNSResolver(listen_port=5354)
    
    # Create active policy with blocked domain
    active_window = ScheduleWindow(
        session_id="s1",
        title="Active Exam Session",
        start_time=datetime(2000, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2099, 1, 1, tzinfo=timezone.utc)
    )
    block_rule = DomainRule(domain="blocked-site.com", action="block", priority=10)
    policy = VerifiedPolicy(
        policy_version=1,
        issued_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        sha256_hash="dummy_hash",
        schedule_windows=[active_window],
        domain_rules=[block_rule]
    )
    
    resolver.set_policy(policy)

    # Client query for blocked-site.com
    client_pkt = DNSPacket(tx_id=0x8888)
    client_pkt.questions.append(DNSQuestion("blocked-site.com"))
    raw_query = client_pkt.build_nxdomain_response()

    # Process query directly
    resp_bytes = resolver.process_query(raw_query, ("127.0.0.1", 12345))
    assert resp_bytes is not None

    parsed_resp = DNSPacket.parse(resp_bytes)
    assert parsed_resp.tx_id == 0x8888
    assert (parsed_resp.flags & 0x000F) == RCODE_NXDOMAIN
