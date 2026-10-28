"""
Upstream DNS Request Forwarder & Health Monitor.

Relays allowed queries to backend-configured upstream resolvers, prevents resolver loops,
handles timeouts & retries, and synthesizes SERVFAIL when upstream resolution fails.
"""

import time
import socket
import logging
from typing import Optional, List, Tuple, Dict, Any
from .protocol import DNSPacket

LOGGER = logging.getLogger(__name__)

class UpstreamResolver:
    """Relays queries to configured upstream DNS server and monitors health."""

    def __init__(
        self,
        upstream_ip: str = "8.8.8.8",
        upstream_port: int = 53,
        timeout_seconds: float = 2.0,
        retry_attempts: int = 2,
        local_listen_host: str = "127.0.0.1",
        local_listen_port: int = 5353
    ):
        self.upstream_ip = upstream_ip
        self.upstream_port = upstream_port
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.local_listen_host = local_listen_host
        self.local_listen_port = local_listen_port
        
        self.healthy = True
        self.last_health_check = 0.0
        self.health_check_interval = 30.0

    def update_config(self, upstream_ip: str, upstream_port: int = 53) -> None:
        """Update upstream configuration."""
        if upstream_ip and upstream_ip != self.upstream_ip:
            self.upstream_ip = upstream_ip
            self.upstream_port = upstream_port
            self.healthy = True
            LOGGER.info("Upstream DNS configuration updated: %s:%s", self.upstream_ip, self.upstream_port)

    def is_loopback_to_self(self, ip: str, port: int) -> bool:
        """Prevent resolver loopback to self."""
        if port == self.local_listen_port:
            if ip in ("127.0.0.1", "localhost", "::1", self.local_listen_host):
                return True
        return False

    def forward_query(self, raw_query_bytes: bytes) -> Tuple[Optional[bytes], bool]:
        """
        Forward query packet to upstream resolver.
        Returns (response_bytes, is_servfail).
        If upstream fails or times out, synthesizes SERVFAIL response to fail safely.
        """
        if self.is_loopback_to_self(self.upstream_ip, self.upstream_port):
            LOGGER.error("Resolver Loop Prevention: Upstream IP %s:%s matches local listener!", self.upstream_ip, self.upstream_port)
            return self._build_servfail(raw_query_bytes), True

        for attempt in range(1, self.retry_attempts + 1):
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(self.timeout_seconds)
                sock.sendto(raw_query_bytes, (self.upstream_ip, self.upstream_port))
                
                resp_bytes, _ = sock.recvfrom(4096)
                if len(resp_bytes) >= 12:
                    self.healthy = True
                    return resp_bytes, False
            except socket.timeout:
                LOGGER.warning("Upstream DNS timeout (%s:%s) attempt %s/%s", self.upstream_ip, self.upstream_port, attempt, self.retry_attempts)
            except Exception as err:
                LOGGER.warning("Upstream DNS error (%s:%s) attempt %s/%s: %s", self.upstream_ip, self.upstream_port, attempt, self.retry_attempts, err)
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

        # Upstream failed on all attempts: fail safely with SERVFAIL
        self.healthy = False
        LOGGER.error("Upstream DNS failed completely (%s:%s); returning SERVFAIL safely", self.upstream_ip, self.upstream_port)
        return self._build_servfail(raw_query_bytes), True

    def check_health(self) -> Dict[str, Any]:
        """Verify upstream resolver reachability."""
        now = time.time()
        if now - self.last_health_check < self.health_check_interval:
            return {"healthy": self.healthy, "upstream": f"{self.upstream_ip}:{self.upstream_port}"}

        self.last_health_check = now
        # Test A-record query for google.com
        test_pkt = DNSPacket(tx_id=0x9999)
        from .protocol import DNSQuestion
        test_pkt.questions.append(DNSQuestion("google.com"))
        test_raw = test_pkt.build_nxdomain_response()  # simple binary query payload structure

        resp_bytes, is_servfail = self.forward_query(test_raw)
        self.healthy = (resp_bytes is not None and not is_servfail)
        return {"healthy": self.healthy, "upstream": f"{self.upstream_ip}:{self.upstream_port}"}

    def _build_servfail(self, raw_query_bytes: bytes) -> bytes:
        try:
            pkt = DNSPacket.parse(raw_query_bytes)
            return pkt.build_servfail_response()
        except Exception:
            # Basic 12-byte header with SERVFAIL flags
            if len(raw_query_bytes) >= 2:
                tx_id = raw_query_bytes[0:2]
            else:
                tx_id = b"\x00\x00"
            # Flags: 0x8182 (QR, RD, RA, SERVFAIL)
            return tx_id + b"\x81\x82\x00\x00\x00\x00\x00\x00\x00\x00"
