"""
Unit tests for DNS binary packet parser, NXDOMAIN synthesis, domain matching, and TTL caching.
"""

from agent.dns.packet import DNSPacket, DNSQuestion, RCODE_NXDOMAIN
from agent.dns.server import LocalDNSServer, DNSCacheEntry
from agent.policy.policy_manager import VerifiedPolicy, DomainRule

def test_dns_packet_parse_and_nxdomain():
    # Build a DNS Question for "example.com"
    pkt = DNSPacket(tx_id=0x1234)
    pkt.questions.append(DNSQuestion("example.com"))
    
    # Generate NXDOMAIN binary response
    nx_bytes = pkt.build_nxdomain_response()
    assert len(nx_bytes) >= 12
    
    # Parse back the binary packet
    parsed = DNSPacket.parse(nx_bytes)
    assert parsed.tx_id == 0x1234
    assert len(parsed.questions) == 1
    assert parsed.questions[0].qname == "example.com"

def test_dns_server_domain_matching():
    server = LocalDNSServer()
    blocked_list = ["facebook.com", "instagram.com", "gaming.org"]
    
    assert server._match_domain("facebook.com", blocked_list) is True
    assert server._match_domain("m.facebook.com", blocked_list) is True
    assert server._match_domain("wikipedia.org", blocked_list) is False

def test_dns_cache_entry():
    entry = DNSCacheEntry(raw_response=b"test_payload", ttl=10)
    assert entry.is_expired() is False
