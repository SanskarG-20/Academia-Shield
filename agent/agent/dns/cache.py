"""
Bounded In-Memory DNS TTL Cache.

Caches allowed upstream DNS responses using normalized (qname, qtype, qclass) keys.
Rewrites transaction ID on cache hits and tracks hits, misses, and evictions.
Never caches SERVFAIL responses, malformed packets, or temporary error states.
"""

import time
import threading
import logging
from typing import Optional, Dict, Tuple, Any
from .protocol import normalize_domain_name

LOGGER = logging.getLogger(__name__)

class CacheEntry:
    def __init__(self, raw_response: bytes, ttl: int = 300):
        self.raw_response = raw_response
        self.ttl = max(1, ttl)
        self.created_at = time.time()
        self.expires_at = self.created_at + self.ttl

    def is_expired(self, now: Optional[float] = None) -> bool:
        current_time = now or time.time()
        return current_time >= self.expires_at

class DNSCache:
    """Bounded in-memory TTL DNS cache with thread-safe transaction ID rewriting."""

    def __init__(self, max_entries: int = 2000, default_ttl: int = 300):
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self._entries: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

        # Metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, qname: str, qtype: int, qclass: int, raw_query_bytes: bytes) -> Optional[bytes]:
        """
        Lookup cached response. On hit, rewrites client transaction ID from raw_query_bytes.
        Returns None on cache miss or expired entry.
        """
        key = self._make_key(qname, qtype, qclass)
        now = time.time()

        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                self.misses += 1
                return None

            if entry.is_expired(now):
                del self._entries[key]
                self.misses += 1
                return None

            self.hits += 1
            # Rewrite client transaction ID (first 2 bytes)
            if len(raw_query_bytes) >= 2 and len(entry.raw_response) >= 2:
                resp_data = bytearray(entry.raw_response)
                resp_data[0:2] = raw_query_bytes[0:2]
                return bytes(resp_data)
            
            return entry.raw_response

    def put(self, qname: str, qtype: int, qclass: int, raw_response_bytes: bytes, ttl: Optional[int] = None) -> bool:
        """
        Store response in cache if valid (not SERVFAIL, non-empty, and under max size limits).
        """
        if not raw_response_bytes or len(raw_response_bytes) < 12:
            return False

        # Reject SERVFAIL (RCODE = 2) or FORMERR (RCODE = 1) caching
        flags = (raw_response_bytes[2] << 8) | raw_response_bytes[3]
        rcode = flags & 0x000F
        if rcode in (1, 2, 4, 5):  # FORMERR, SERVFAIL, NOTIMP, REFUSED
            return False

        key = self._make_key(qname, qtype, qclass)
        entry_ttl = ttl if ttl is not None else self.default_ttl
        entry = CacheEntry(raw_response=raw_response_bytes, ttl=entry_ttl)

        with self._lock:
            # Enforce max capacity eviction (LRU / cleanup)
            if len(self._entries) >= self.max_entries and key not in self._entries:
                self._evict_expired_or_oldest(now=time.time())

            self._entries[key] = entry
            return True

    def clear(self) -> None:
        """Flush all cache entries."""
        with self._lock:
            self._entries.clear()

    def get_metrics(self) -> Dict[str, Any]:
        """Return cache hit/miss/eviction metrics."""
        with self._lock:
            return {
                "size": len(self._entries),
                "max_entries": self.max_entries,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions
            }

    def _make_key(self, qname: str, qtype: int, qclass: int) -> str:
        clean = normalize_domain_name(qname)
        return f"{clean}:{qtype}:{qclass}"

    def _evict_expired_or_oldest(self, now: float) -> None:
        # First remove expired items
        expired_keys = [k for k, v in self._entries.items() if v.is_expired(now)]
        for k in expired_keys:
            del self._entries[k]
            self.evictions += 1

        # If still at max size, evict oldest
        if len(self._entries) >= self.max_entries:
            oldest_key = min(self._entries.keys(), key=lambda k: self._entries[k].created_at)
            del self._entries[oldest_key]
            self.evictions += 1
