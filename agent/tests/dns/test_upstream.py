"""
Tests for Upstream DNS Forwarding & Loop Prevention.
"""

from agent.dns.upstream import UpstreamResolver
from agent.dns.protocol import DNSPacket, DNSQuestion, RCODE_SERVFAIL

def test_loopback_prevention():
    resolver = UpstreamResolver(
        upstream_ip="127.0.0.1",
        upstream_port=5353,
        local_listen_host="127.0.0.1",
        local_listen_port=5353
    )
    assert resolver.is_loopback_to_self("127.0.0.1", 5353) is True
    assert resolver.is_loopback_to_self("8.8.8.8", 53) is False

    pkt = DNSPacket(tx_id=0x5555)
    pkt.questions.append(DNSQuestion("loop.com"))
    raw_query = pkt.build_nxdomain_response()

    resp_bytes, is_servfail = resolver.forward_query(raw_query)
    assert is_servfail is True
    parsed = DNSPacket.parse(resp_bytes)
    assert parsed.tx_id == 0x5555
    assert (parsed.flags & 0x000F) == RCODE_SERVFAIL

def test_upstream_timeout_servfail_fallback():
    # Point to an unreachable IP/port that times out
    resolver = UpstreamResolver(upstream_ip="192.0.2.1", upstream_port=59999, timeout_seconds=0.2, retry_attempts=1)
    
    pkt = DNSPacket(tx_id=0x7777)
    pkt.questions.append(DNSQuestion("unreachable.org"))
    raw_query = pkt.build_nxdomain_response()

    resp_bytes, is_servfail = resolver.forward_query(raw_query)
    assert is_servfail is True
    parsed = DNSPacket.parse(resp_bytes)
    assert parsed.tx_id == 0x7777
    assert (parsed.flags & 0x000F) == RCODE_SERVFAIL
