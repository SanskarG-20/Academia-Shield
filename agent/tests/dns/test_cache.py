"""
Tests for Bounded In-Memory DNS TTL Cache.
"""

import time
from agent.dns.cache import DNSCache
from agent.dns.protocol import DNSPacket, DNSQuestion, TYPE_A, CLASS_IN

def test_dns_cache_hit_and_transaction_id_rewriting():
    cache = DNSCache(default_ttl=60)
    
    # Fake upstream response with TX_ID = 0x9999
    upstream_pkt = DNSPacket(tx_id=0x9999)
    upstream_pkt.questions.append(DNSQuestion("cached.com"))
    raw_upstream = upstream_pkt.build_nxdomain_response()

    # Store in cache
    stored = cache.put("cached.com", TYPE_A, CLASS_IN, raw_upstream, ttl=60)
    assert stored is True

    # Client query with TX_ID = 0x1111
    client_query = DNSPacket(tx_id=0x1111)
    client_query.questions.append(DNSQuestion("cached.com"))
    raw_client = client_query.build_nxdomain_response()

    # Get from cache
    cached_resp = cache.get("cached.com", TYPE_A, CLASS_IN, raw_client)
    assert cached_resp is not None
    
    # Verify transaction ID was rewritten to client's 0x1111
    parsed_resp = DNSPacket.parse(cached_resp)
    assert parsed_resp.tx_id == 0x1111
    assert cache.hits == 1

def test_servfail_caching_rejection():
    cache = DNSCache()
    sf_pkt = DNSPacket(tx_id=0x2222)
    sf_pkt.questions.append(DNSQuestion("error.com"))
    raw_sf = sf_pkt.build_servfail_response()

    # Attempt to put SERVFAIL into cache -> Must return False
    stored = cache.put("error.com", TYPE_A, CLASS_IN, raw_sf)
    assert stored is False
    assert cache.get("error.com", TYPE_A, CLASS_IN, raw_sf) is None

def test_cache_ttl_expiration():
    cache = DNSCache()
    pkt = DNSPacket(tx_id=0x3333)
    pkt.questions.append(DNSQuestion("short-ttl.com"))
    raw_resp = pkt.build_nxdomain_response()

    # Store with TTL = 1 second
    cache.put("short-ttl.com", TYPE_A, CLASS_IN, raw_resp, ttl=1)
    
    # Immediate hit
    assert cache.get("short-ttl.com", TYPE_A, CLASS_IN, raw_resp) is not None
    
    # Sleep 1.1s -> Must expire
    time.sleep(1.1)
    assert cache.get("short-ttl.com", TYPE_A, CLASS_IN, raw_resp) is None
