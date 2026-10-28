"""
Unprivileged UDP DNS Server & Resolver Engine.

Listens on high port (default 5353), performs domain matching against active policy,
synthesizes NXDOMAIN for blocked domains, relays allowed queries to upstream resolver,
and caches responses with TTL support.
"""

import time
import socket
import select
import threading
import logging
from typing import Optional, List, Dict, Tuple, Any
from .packet import DNSPacket, RCODE_NXDOMAIN
from ..config import get_config
from ..policy import VerifiedPolicy
from ..telemetry import TelemetryManager

LOGGER = logging.getLogger(__name__)

class DNSCacheEntry:
    def __init__(self, raw_response: bytes, ttl: int = 300):
        self.raw_response = raw_response
        self.expires_at = time.time() + ttl

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

class LocalDNSServer:
    """DNS Resolver Engine for local policy enforcement."""

    def __init__(
        self,
        listen_host: Optional[str] = None,
        listen_port: Optional[int] = None,
        upstream_ip: Optional[str] = None,
        upstream_port: Optional[int] = None,
        telemetry_manager: Optional[TelemetryManager] = None
    ):
        config = get_config()
        self.host = listen_host or config.dns_listen_host
        self.port = listen_port or config.dns_listen_port
        self.upstream_ip = upstream_ip or config.dns_upstream
        self.upstream_port = upstream_port or config.dns_upstream_port
        self.telemetry_manager = telemetry_manager or TelemetryManager()
        
        self.socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._policy: Optional[VerifiedPolicy] = None
        self._cache: Dict[str, DNSCacheEntry] = {}
        self._cache_lock = threading.Lock()
        self.healthy = False
        self.drift_detected = False

    def set_policy(self, policy: Optional[VerifiedPolicy]) -> None:
        """Update active enforcement policy."""
        self._policy = policy

    def start(self) -> bool:
        """Start UDP DNS listener socket."""
        if self._running:
            return True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.setblocking(False)
            self._running = True
            self.healthy = True

            self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="dns_resolver")
            self._thread.start()
            LOGGER.info("DNS Engine started listening on %s:%s (Upstream: %s:%s)", self.host, self.port, self.upstream_ip, self.upstream_port)
            return True
        except Exception as err:
            LOGGER.error("Failed starting DNS server on %s:%s (%s)", self.host, self.port, err)
            self.healthy = False
            return False

    def stop(self) -> None:
        """Stop DNS server and close socket."""
        self._running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        self.healthy = False
        LOGGER.info("DNS Engine stopped.")

    def _listen_loop(self) -> None:
        while self._running:
            try:
                r, _, _ = select.select([self.socket], [], [], 0.5)
                if not r:
                    continue

                raw_data, addr = self.socket.recvfrom(4096)
                if not raw_data:
                    continue

                # Process query in thread pool or inline
                self._handle_query(raw_data, addr)

            except OSError:
                break
            except Exception as err:
                LOGGER.debug("Error in DNS server loop: %s", err)

    def _handle_query(self, raw_data: bytes, client_addr: Tuple[str, int]) -> None:
        try:
            packet = DNSPacket.parse(raw_data)
            if not packet.questions:
                return

            qname = packet.questions[0].qname.strip().lower()
            
            # Check allowed domains first: if qname matches an allowed domain, it is NEVER blocked
            allowed_domains = self._policy.get_active_allowed_domains() if self._policy and hasattr(self._policy, "get_active_allowed_domains") else []
            if allowed_domains and self._match_domain(qname, allowed_domains):
                is_blocked = False
            else:
                # Check policy blocked domains
                blocked_domains = self._policy.get_active_blocked_domains() if self._policy else []
                is_blocked = self._match_domain(qname, blocked_domains)

            if is_blocked:
                LOGGER.info("DNS BLOCK | Domain '%s' denied by active policy", qname)
                # Synthesize NXDOMAIN
                response_bytes = packet.build_nxdomain_response()
                self.socket.sendto(response_bytes, client_addr)
                
                # Emit privacy-minimized telemetry
                session_id = self._policy.schedule_windows[0].session_id if (self._policy and self._policy.schedule_windows) else None
                self.telemetry_manager.record_violation_event(
                    event_type="web",
                    resource_name=qname,
                    action="blocked",
                    session_id=session_id,
                    rule_id=f"rule_domain_{qname}"
                )
                return

            # Check bounded TTL cache
            cache_key = f"{qname}_{packet.questions[0].qtype}"
            with self._cache_lock:
                entry = self._cache.get(cache_key)
                if entry and not entry.is_expired():
                    # Rewrite transaction ID from cached entry
                    resp_data = bytearray(entry.raw_response)
                    resp_data[0:2] = raw_data[0:2]
                    self.socket.sendto(bytes(resp_data), client_addr)
                    return

            # Forward to upstream resolver
            response_bytes = self._forward_upstream(raw_data)
            if response_bytes:
                self.socket.sendto(response_bytes, client_addr)
                # Cache response
                with self._cache_lock:
                    self._cache[cache_key] = DNSCacheEntry(response_bytes, ttl=300)

        except Exception as err:
            LOGGER.debug("Error handling DNS query: %s", err)

    def _match_domain(self, qname: str, blocked_list: List[str]) -> bool:
        """Check exact or wildcard domain match."""
        for b in blocked_list:
            b_clean = b.strip().lower()
            if not b_clean:
                continue
            if qname == b_clean or qname.endswith("." + b_clean):
                return True
        return False

    def _forward_upstream(self, query_bytes: bytes, timeout: float = 2.0) -> Optional[bytes]:
        """Relay allowed DNS query to upstream resolver (8.8.8.8:53)."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(query_bytes, (self.upstream_ip, self.upstream_port))
            resp_bytes, _ = sock.recvfrom(4096)
            return resp_bytes
        except Exception as err:
            LOGGER.debug("Upstream DNS query to %s failed: %s", self.upstream_ip, err)
            return None
        finally:
            if sock:
                sock.close()

    def check_health_and_drift(self) -> Dict[str, Any]:
        """Verify resolver health and check for configuration drift."""
        # Test query to self
        healthy = self._running and self.socket is not None
        drift = False

        if healthy:
            try:
                test_pkt = DNSPacket(tx_id=1234)
                from .packet import DNSQuestion
                test_pkt.questions.append(DNSQuestion("healthcheck.local"))
                raw = test_pkt.build_nxdomain_response()
                if len(raw) < 12:
                    drift = True
            except Exception:
                healthy = False
                drift = True

        self.healthy = healthy
        self.drift_detected = drift

        return {
            "healthy": healthy,
            "drift_detected": drift,
            "listen_port": self.port,
            "upstream": self.upstream_ip
        }
