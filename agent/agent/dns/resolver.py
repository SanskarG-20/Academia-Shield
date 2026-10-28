"""
Local UDP DNS Resolver Engine.

Processes incoming DNS UDP packets, validates binary structure, matches requests against
active backend policy rules, synthesizes NXDOMAIN for blocked domains, relays allowed queries to
upstream resolver with TTL caching, and rewrites client transaction IDs.
"""

import time
import socket
import select
import threading
import logging
from typing import Optional, Dict, Tuple, List, Any
from .protocol import DNSPacket, TYPE_A, RCODE_NXDOMAIN, RCODE_SERVFAIL
from .rules import DomainRuleMatcher, PolicyDomainRule
from .upstream import UpstreamResolver
from .cache import DNSCache
from ..config import get_config
from ..policy import VerifiedPolicy
from ..telemetry import TelemetryManager

LOGGER = logging.getLogger(__name__)

class LocalDNSResolver:
    """Production UDP DNS Resolver for policy enforcement."""

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
        
        self.upstream = UpstreamResolver(
            upstream_ip=upstream_ip or config.dns_upstream,
            upstream_port=upstream_port or config.dns_upstream_port,
            local_listen_host=self.host,
            local_listen_port=self.port
        )
        self.cache = DNSCache(max_entries=2000, default_ttl=config.dns_ttl)
        self.matcher = DomainRuleMatcher()
        self.telemetry_manager = telemetry_manager or TelemetryManager()

        self.socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_policy: Optional[VerifiedPolicy] = None
        self.healthy = False

    def set_policy(self, policy: Optional[VerifiedPolicy]) -> None:
        """Update active policy and load domain rules into priority matcher."""
        self._current_policy = policy
        if not policy:
            self.matcher.set_rules([])
            return

        now = time.time()
        # Convert policy domain rules to PolicyDomainRule instances
        policy_rules = []
        for index, r in enumerate(policy.domain_rules):
            policy_rules.append(PolicyDomainRule(
                rule_id=f"rule_dom_{index}_{r.domain}",
                domain_pattern=r.domain,
                rule_type="wildcard" if r.domain.startswith("*.") else "exact",
                action=r.action,
                priority=r.priority,
                is_enabled=True,
                reason="Policy rule"
            ))

        self.matcher.set_rules(policy_rules)

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

            self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="dns_udp_resolver")
            self._thread.start()
            LOGGER.info("Local DNS Resolver started listening on %s:%s", self.host, self.port)
            return True
        except Exception as err:
            LOGGER.error("Failed starting DNS resolver socket on %s:%s (%s)", self.host, self.port, err)
            self.healthy = False
            return False

    def stop(self) -> None:
        """Stop resolver loop and close UDP socket."""
        self._running = False
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        self.healthy = False
        LOGGER.info("Local DNS Resolver stopped.")

    def _listen_loop(self) -> None:
        while self._running:
            try:
                r, _, _ = select.select([self.socket], [], [], 0.5)
                if not r:
                    continue

                raw_data, addr = self.socket.recvfrom(4096)
                if not raw_data:
                    continue

                self.process_query(raw_data, addr)

            except OSError:
                break
            except Exception as err:
                LOGGER.debug("Error in DNS resolver loop: %s", err)

    def process_query(self, raw_data: bytes, client_addr: Tuple[str, int]) -> Optional[bytes]:
        """
        Process single DNS query packet from raw bytes.
        Sends response packet to client_addr via UDP socket if available.
        """
        try:
            # 1. Parse Packet & Reject Malformed Payload
            packet = DNSPacket.parse(raw_data)
            if not packet.questions:
                return None

            question = packet.questions[0]
            qname = question.qname
            qtype = question.qtype
            qclass = question.qclass

            # 2. Check Policy Validity & Session Active Window
            policy_valid = False
            if self._current_policy and not self._current_policy.is_expired():
                if self._current_policy.is_session_active():
                    policy_valid = True

            # 3. Policy Evaluation
            action, matched_rule = "pass", None
            if policy_valid:
                action, matched_rule = self.matcher.evaluate_qname(qname)

            if action == "block":
                LOGGER.info("DNS DENIED | Domain '%s' blocked by policy rule '%s'", qname, matched_rule.rule_id if matched_rule else "rule")
                
                # Synthesize NXDOMAIN response preserving client transaction ID
                resp_bytes = packet.build_nxdomain_response()
                if self.socket and client_addr:
                    self.socket.sendto(resp_bytes, client_addr)

                # Record privacy-minimized violation telemetry
                session_id = self._current_policy.schedule_windows[0].session_id if (self._current_policy and self._current_policy.schedule_windows) else None
                self.telemetry_manager.record_violation_event(
                    event_type="dns_block",
                    resource_name=qname,
                    action="blocked",
                    session_id=session_id,
                    rule_id=matched_rule.rule_id if matched_rule else None
                )
                return resp_bytes

            # 4. Lookup TTL Cache
            cached_resp = self.cache.get(qname, qtype, qclass, raw_data)
            if cached_resp:
                if self.socket and client_addr:
                    self.socket.sendto(cached_resp, client_addr)
                return cached_resp

            # 5. Upstream Forwarding
            upstream_resp, is_servfail = self.upstream.forward_query(raw_data)
            if upstream_resp:
                # Cache allowed non-SERVFAIL responses
                if not is_servfail and policy_valid:
                    self.cache.put(qname, qtype, qclass, upstream_resp, ttl=300)

                if self.socket and client_addr:
                    self.socket.sendto(upstream_resp, client_addr)
                return upstream_resp

        except ValueError as val_err:
            LOGGER.warning("Rejected malformed DNS packet from %s: %s", client_addr, val_err)
        except Exception as err:
            LOGGER.error("Unexpected error processing DNS query: %s", err)

        return None
