"""
Tests for DNS Binary Packet Parser & Encoder (RFC 1035).
"""

import pytest
from agent.dns.protocol import (
    DNSPacket,
    DNSQuestion,
    normalize_domain_name,
    RCODE_NXDOMAIN,
    RCODE_SERVFAIL
)

def test_normalize_domain_name():
    assert normalize_domain_name("EXAMPLE.COM.") == "example.com"
    assert normalize_domain_name("  Sub.Domain.Org  ") == "sub.domain.org"
    # IDNA Punycode normalization
    assert normalize_domain_name("münchen.de") == "xn--mnchen-3ya.de"

def test_dns_packet_encoding_and_parsing():
    pkt = DNSPacket(tx_id=0x1234)
    pkt.questions.append(DNSQuestion("test.university.edu"))
    
    encoded = pkt.build_nxdomain_response()
    assert len(encoded) >= 12
    
    parsed = DNSPacket.parse(encoded)
    assert parsed.tx_id == 0x1234
    assert len(parsed.questions) == 1
    assert parsed.questions[0].qname == "test.university.edu"

def test_malformed_packet_rejection():
    # 1. Payload less than 12-byte header
    with pytest.raises(ValueError, match="Malformed packet"):
        DNSPacket.parse(b"\x00\x01\x00")

    # 2. Out of bounds truncated domain label
    bad_data = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x05test"  # missing null term / length error
    with pytest.raises(ValueError, match="Malformed packet"):
        DNSPacket.parse(bad_data)

def test_nxdomain_and_servfail_response_building():
    pkt = DNSPacket(tx_id=0xABCD)
    pkt.questions.append(DNSQuestion("blocked.com"))

    nx_bytes = pkt.build_nxdomain_response()
    nx_parsed = DNSPacket.parse(nx_bytes)
    assert nx_parsed.tx_id == 0xABCD
    # Check RCODE in flags (bottom 4 bits)
    rcode = nx_parsed.flags & 0x000F
    assert rcode == RCODE_NXDOMAIN

    sf_bytes = pkt.build_servfail_response()
    sf_parsed = DNSPacket.parse(sf_bytes)
    assert sf_parsed.tx_id == 0xABCD
    assert (sf_parsed.flags & 0x000F) == RCODE_SERVFAIL
