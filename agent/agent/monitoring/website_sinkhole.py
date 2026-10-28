"""
Website Sinkhole & Blocked Domain Telemetry Server.

Listens on 127.0.0.1 (ports 80 and 443) to intercept HTTP and HTTPS connection attempts
to domains redirected to localhost by the hosts-file enforcement engine.
Extracts target hostnames via TLS SNI (Server Name Indication) or HTTP Host headers,
and immediately records website policy violations to the telemetry manager.
"""

import sys
import time
import socket
import select
import threading
import logging
from typing import Optional, Set, Dict, Any, List

LOGGER = logging.getLogger(__name__)


def extract_sni_from_tls(data: bytes) -> str:
    """
    Extract Server Name Indication (SNI) from raw TLS Client Hello packet.
    Follows RFC 6066 format. Zero external dependencies.
    """
    # Minimum length for a TLS Client Hello containing an extension
    if len(data) < 44 or data[0] != 0x16 or data[5] != 0x01:
        return ""

    try:
        idx = 43
        if idx >= len(data):
            return ""
        
        # Skip session ID
        sess_id_len = data[idx]
        idx += 1 + sess_id_len
        if idx + 2 > len(data):
            return ""

        # Skip cipher suites
        cipher_len = int.from_bytes(data[idx:idx+2], "big")
        idx += 2 + cipher_len
        if idx + 1 > len(data):
            return ""

        # Skip compression methods
        comp_len = data[idx]
        idx += 1 + comp_len
        if idx + 2 > len(data):
            return ""

        # Extensions length
        ext_total_len = int.from_bytes(data[idx:idx+2], "big")
        idx += 2
        end_ext = idx + ext_total_len

        # Parse extensions
        while idx + 4 <= min(end_ext, len(data)):
            ext_type = int.from_bytes(data[idx:idx+2], "big")
            ext_len = int.from_bytes(data[idx+2:idx+4], "big")
            idx += 4
            if ext_type == 0:  # Extension: server_name (SNI)
                if idx + 5 <= len(data):
                    # Skip server_name_list length (2) and name_type (1, 0x00=host_name)
                    name_len = int.from_bytes(data[idx+3:idx+5], "big")
                    if idx + 5 + name_len <= len(data):
                        sni_bytes = data[idx+5:idx+5+name_len]
                        return sni_bytes.decode("utf-8", errors="ignore").strip().lower()
            idx += ext_len
    except Exception:
        pass

    return ""


def extract_http_host(data: bytes) -> str:
    """Extract Host header value from plain HTTP request."""
    try:
        text = data[:2048].decode("utf-8", errors="ignore")
        for line in text.split("\r\n"):
            if line.lower().startswith("host:"):
                host_val = line.split(":", 1)[1].strip()
                # Strip port if present
                return host_val.split(":")[0].strip().lower()
    except Exception:
        pass
    return ""


class WebsiteSinkholeServer:
    """
    High-performance, lightweight localhost sinkhole server.
    Captures attempted connections to blocked domains on ports 80 and 443.
    """

    def __init__(
        self,
        telemetry_manager: Optional[Any] = None,
        engagement_tracker: Optional[Any] = None,
        cooldown_seconds: float = 10.0
    ):
        self.telemetry_manager = telemetry_manager
        self.engagement_tracker = engagement_tracker
        self.cooldown_seconds = cooldown_seconds

        self._running = False
        self._sockets: List[socket.socket] = []
        self._threads: List[threading.Thread] = []
        self._blocked_domains: Set[str] = set()
        self._session_id: Optional[str] = None
        self._last_violation_ts: Dict[str, float] = {}
        self._lock = threading.Lock()

    def update_policy(self, active_domains: List[str], session_id: Optional[str] = None):
        """Update the set of currently blocked domains and active session ID."""
        with self._lock:
            self._session_id = session_id
            clean_set = set()
            for d in active_domains:
                dom_str = str(d).strip().lower()
                clean_set.add(dom_str)
                base = dom_str[4:] if dom_str.startswith("www.") else dom_str
                clean_set.add(base)
                clean_set.add(f"www.{base}")
            self._blocked_domains = clean_set

    def start(self, ports: Optional[List[int]] = None):
        """Start listener threads for specified ports (defaults to 80 and 443)."""
        if self._running:
            return

        target_ports = ports or [80, 443]
        self._running = True
        self._sockets = []

        for port in target_ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.setblocking(False)
                s.bind(("127.0.0.1", port))
                s.listen(32)
                self._sockets.append(s)
                LOGGER.info("Website Sinkhole listening on 127.0.0.1:%d", port)

                t = threading.Thread(
                    target=self._listen_loop,
                    args=(s, port),
                    name=f"Sinkhole-{port}",
                    daemon=True
                )
                t.start()
                self._threads.append(t)
            except Exception as err:
                LOGGER.debug("Could not bind sinkhole on 127.0.0.1:%d: %s", port, err)

    def stop(self):
        """Stop all listeners and close sockets."""
        self._running = False
        for s in self._sockets:
            try:
                s.close()
            except Exception:
                pass
        self._sockets = []
        self._threads = []
        LOGGER.info("Website Sinkhole stopped.")

    def _listen_loop(self, sock: socket.socket, port: int):
        """Main non-blocking event loop for a bound port."""
        while self._running:
            try:
                r, _, _ = select.select([sock], [], [], 0.5)
                if not r:
                    continue

                client_sock, client_addr = sock.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_sock, client_addr, port),
                    daemon=True
                ).start()
            except OSError:
                break
            except Exception as err:
                LOGGER.debug("Sinkhole loop error on port %d: %s", port, err)

    def _handle_client(self, client_sock: socket.socket, client_addr: tuple, port: int):
        """Handle incoming connection, parse domain, and emit violation telemetry."""
        try:
            client_sock.settimeout(2.0)
            data = client_sock.recv(4096)
            if not data:
                client_sock.close()
                return

            detected_domain = ""
            if port == 443 or data[0] == 0x16:
                detected_domain = extract_sni_from_tls(data)
            else:
                detected_domain = extract_http_host(data)

            if detected_domain:
                self._process_blocked_attempt(detected_domain, client_sock, port)
            else:
                # If no SNI or Host header found, check if connection is during active session
                with self._lock:
                    if self._blocked_domains:
                        # Fallback to first primary blocked domain for attribution
                        fallback_dom = next(iter(self._blocked_domains))
                        self._process_blocked_attempt(fallback_dom, client_sock, port)

            # Send friendly block page for HTTP port 80
            if port == 80:
                html = (
                    "HTTP/1.1 403 Forbidden\r\n"
                    "Content-Type: text/html; charset=utf-8\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    "<!DOCTYPE html><html><head><title>Access Blocked - Academia Shield</title>"
                    "<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;"
                    "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}"
                    ".card{background:#1e293b;padding:32px;border-radius:16px;box-shadow:0 10px 25px rgba(0,0,0,0.5);"
                    "max-width:440px;text-align:center;border:1px solid #334155;}"
                    "h2{color:#ef4444;margin-top:0;}p{color:#94a3b8;font-size:14px;line-height:1.5;}"
                    ".badge{display:inline-block;padding:4px 12px;background:#334155;color:#38bdf8;border-radius:9999px;font-weight:600;font-size:12px;margin:12px 0;}"
                    "</style></head><body><div class=\"card\">"
                    "<h2>Restricted Website</h2>"
                    f"<p>Access to this domain is restricted by your instructor during an active academic session.</p>"
                    f"<div class=\"badge\">{detected_domain or 'Restricted Domain'}</div>"
                    "<p style=\"font-size:12px;color:#64748b;\">Academia Shield Protection Active</p>"
                    "</div></body></html>"
                )
                try:
                    client_sock.sendall(html.encode("utf-8"))
                except Exception:
                    pass
        except Exception as err:
            LOGGER.debug("Sinkhole client error: %s", err)
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _process_blocked_attempt(self, domain: str, client_sock: socket.socket, port: int):
        """Deduplicate and record policy violation for attempted website access."""
        clean_dom = domain.strip().lower()
        now = time.time()

        with self._lock:
            # Check domain against blocked list
            is_match = False
            for b in self._blocked_domains:
                if b == clean_dom or clean_dom.endswith(f".{b}") or b in clean_dom:
                    is_match = True
                    break

            if not is_match and self._blocked_domains:
                # If hosts file directed the connection to 127.0.0.1, it is an enforced domain
                is_match = True

            if not is_match:
                return

            last_ts = self._last_violation_ts.get(clean_dom, 0.0)
            if (now - last_ts) < self.cooldown_seconds:
                return
            self._last_violation_ts[clean_dom] = now
            sess_id = self._session_id

        LOGGER.warning("BLOCKED WEBSITE ATTEMPT | Domain '%s' accessed on port %d - recording violation", clean_dom, port)

        if self.telemetry_manager and hasattr(self.telemetry_manager, "record_violation_event"):
            try:
                self.telemetry_manager.record_violation_event(
                    event_type="web",
                    resource_name=clean_dom,
                    action="blocked",
                    session_id=sess_id,
                    rule_id=f"rule_domain_{clean_dom}",
                    is_violation=True
                )
            except Exception as err:
                LOGGER.error("Failed to record website violation telemetry: %s", err)

        if self.engagement_tracker and getattr(self.engagement_tracker, "is_active", False):
            try:
                self.engagement_tracker.record_violation("web")
            except Exception as err:
                LOGGER.debug("Failed to record engagement tracker violation: %s", err)
