"""
API Client Adapter for Academia Shield Backend.

Implements TLS certificate validation, JWT token rotation, Ed25519 request signing,
exponential backoff, and circuit breaking.
"""

import sys
import time
import json
import ssl
import logging
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Dict, Any, List, Union
from ..config import get_config, redact_text
from ..auth import TokenManager, Ed25519KeyManager

LOGGER = logging.getLogger(__name__)

class CircuitBreakerOpenException(Exception):
    """Raised when request is attempted while circuit breaker is OPEN."""
    pass

class APIClientAdapter:
    """Production HTTP API Client adapter for Academia Shield agent."""

    def __init__(self, token_manager: Optional[TokenManager] = None, key_manager: Optional[Ed25519KeyManager] = None):
        self.config = get_config()
        self.token_manager = token_manager or TokenManager()
        self.key_manager = key_manager
        
        # Circuit breaker state
        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._failure_threshold = 5
        self._reset_timeout = 30.0

    def _check_circuit(self) -> None:
        now = time.time()
        if self._failure_count >= self._failure_threshold:
            if now < self._circuit_open_until:
                raise CircuitBreakerOpenException(f"Circuit breaker OPEN until {self._circuit_open_until}")
            else:
                # Reset to half-open
                self._failure_count = 0

    def _record_success(self) -> None:
        self._failure_count = 0

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._circuit_open_until = time.time() + self._reset_timeout
            LOGGER.warning("API Circuit Breaker TRIPPED. Pause requests for %ss", self._reset_timeout)

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        auth_required: bool = True,
        retry: bool = True
    ) -> Dict[str, Any]:
        # Do not block health, token refresh, or device enrollment with circuit breaker
        if endpoint not in ("/health", "/api/v1/auth/refresh", "/api/auth/refresh", "/api/v1/agent/devices/enroll", "/api/agent/devices/enroll"):
            self._check_circuit()
        url = f"{self.config.api_url}{endpoint}"
        
        # Auto refresh token if access token is expired
        if auth_required and self.token_manager.is_access_token_expired():
            self.refresh_session()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"AcademiaShieldAgent/{self.config.agent_version}",
            "X-Device-Identifier": self.config.device_id
        }

        if auth_required:
            token = self.token_manager.get_access_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"

        body_bytes = None
        if data is not None:
            body_bytes = json.dumps(data).encode("utf-8")
            if self.key_manager:
                try:
                    sig = self.key_manager.sign(body_bytes)
                    headers["X-Signature"] = sig
                    headers["X-Public-Key"] = self.key_manager.get_public_key_hex()
                except Exception as err:
                    LOGGER.debug("Could not sign request: %s", err)

        ctx = ssl.create_default_context()
        # Enforce TLS Certificate Validation
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        
        # Allow disabling SSL verification ONLY for local HTTP endpoints
        if url.startswith("http://127.0.0.1") or url.startswith("http://localhost"):
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)

        max_attempts = self.config.retry_attempts if retry else 1
        backoff = self.config.retry_backoff_seconds

        for attempt in range(1, max_attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.config.request_timeout, context=ctx) as resp:
                    resp_body = resp.read().decode("utf-8")
                    self._record_success()
                    if resp_body:
                        return json.loads(resp_body)
                    return {}
            except urllib.error.HTTPError as http_err:
                LOGGER.warning("HTTP %s from %s (attempt %s/%s)", http_err.code, endpoint, attempt, max_attempts)
                if http_err.code == 401 and auth_required and attempt == 1:
                    # Attempt refresh / re-enroll on 401
                    if self.refresh_session():
                        headers["Authorization"] = f"Bearer {self.token_manager.get_access_token()}"
                        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
                        continue
                # Do NOT trip circuit breaker on normal client/business status responses (e.g. 404 No Active Session)
                if http_err.code in (400, 403, 404, 422):
                    return {}
                if endpoint not in ("/api/v1/auth/refresh", "/api/auth/refresh", "/api/v1/agent/devices/enroll", "/api/agent/devices/enroll"):
                    self._record_failure()
                if attempt == max_attempts:
                    raise
            except Exception as err:
                LOGGER.warning("Connection error on %s (%s) attempt %s/%s", endpoint, redact_text(str(err)), attempt, max_attempts)
                if endpoint not in ("/api/v1/auth/refresh", "/api/auth/refresh", "/api/v1/agent/devices/enroll", "/api/agent/devices/enroll"):
                    self._record_failure()
                if attempt == max_attempts:
                    raise
            
            time.sleep(backoff)
            backoff *= 2

        return {}

    # -------------------------------------------------------------------------
    # Authentication & Enrollment Methods
    # -------------------------------------------------------------------------
    def login(self, email_or_id: str, password: str) -> Dict[str, Any]:
        """Authenticate user against backend login endpoint."""
        payload = {"email_or_id": email_or_id, "password": password}
        res = self._make_request("/api/auth/login", method="POST", data=payload, auth_required=False, retry=False)
        access_tok = res.get("access_token")
        refresh_tok = res.get("refresh_token")
        if access_tok and refresh_tok:
            self.token_manager.save_tokens(access_tok, refresh_tok)
        return res

    def is_backend_available(self) -> bool:
        """Return whether the configured backend is reachable without requiring login."""
        try:
            response = self._make_request(
                "/health",
                method="GET",
                auth_required=False,
                retry=False,
            )
            return response.get("status") in ("healthy", "degraded")
        except Exception as err:
            LOGGER.debug("Backend health check failed: %s", redact_text(str(err)))
            return False

    def _auto_reenroll(self) -> bool:
        """Seamlessly re-enroll device with backend if session tokens expired or were invalidated."""
        try:
            LOGGER.info("Attempting seamless device enrollment recovery with backend...")
            if not self.key_manager:
                from ..auth import Ed25519KeyManager
                priv_pem = self.token_manager.storage.get_credential("private_key")
                if priv_pem:
                    self.key_manager = Ed25519KeyManager(private_key_pem=priv_pem)
                else:
                    self.key_manager = Ed25519KeyManager()
                    new_pem, _ = self.key_manager.generate_keypair()
                    self.token_manager.storage.store_credential("private_key", new_pem)

            pub_hex = self.key_manager.get_public_key_hex() if self.key_manager else ""
            os_name = "windows" if sys.platform == "win32" else sys.platform
            os_version = "10.0"
            hostname = self.config.device_id

            try:
                from ..platform import get_platform_adapter
                adapter = get_platform_adapter()
                info = adapter.get_os_info()
                hostname = info.get("hostname", hostname)
                os_name = info.get("os_name", os_name)
                os_version = info.get("os_version", os_version)
            except Exception:
                pass

            payload = {
                "device_name": hostname,
                "device_identifier": self.config.device_id,
                "public_key": pub_hex or "default_ed25519_key",
                "platform": os_name.lower(),
                "platform_version": os_version,
                "agent_version": self.config.agent_version
            }
            res = self._make_request("/api/v1/agent/devices/enroll", method="POST", data=payload, auth_required=False, retry=False)
            access_tok = res.get("access_token")
            refresh_tok = res.get("refresh_token")
            if access_tok:
                self.token_manager.save_tokens(access_tok, refresh_tok or "", self.config.device_id)
                LOGGER.info("Successfully enrolled device '%s' and obtained fresh session tokens.", self.config.device_id)
                return True
        except Exception as err:
            LOGGER.warning("Device auto-enrollment recovery failed: %s", redact_text(str(err)))
        return False

    def refresh_session(self) -> bool:
        """Rotate tokens using stored refresh token, with auto-enrollment recovery on invalid session."""
        refresh_tok = self.token_manager.get_refresh_token()
        if not refresh_tok:
            return self._auto_reenroll()
        try:
            payload = {"refresh_token": refresh_tok}
            res = self._make_request("/api/v1/auth/refresh", method="POST", data=payload, auth_required=False, retry=False)
            access_tok = res.get("access_token")
            new_refresh_tok = res.get("refresh_token")
            if access_tok:
                self.token_manager.save_tokens(access_tok, new_refresh_tok or refresh_tok, self.config.device_id)
                LOGGER.info("Successfully refreshed session tokens")
                return True
            return self._auto_reenroll()
        except Exception as err:
            LOGGER.warning("Session token refresh failed: %s; attempting auto-enrollment recovery", redact_text(str(err)))
            return self._auto_reenroll()
        return False

    def enroll_with_token(self, enrollment_token: str, public_key_hex: str, hostname: str, os_name: str, os_version: str) -> Dict[str, Any]:
        """Register device with one-time student enrollment token (/api/v1/agent/devices/enroll)."""
        payload = {
            "enrollment_token": enrollment_token.strip().upper(),
            "device_name": hostname,
            "device_identifier": self.config.device_id,
            "public_key": public_key_hex,
            "platform": os_name.lower(),
            "platform_version": os_version,
            "agent_version": self.config.agent_version
        }
        res = self._make_request("/api/v1/agent/devices/enroll", method="POST", data=payload, auth_required=False)
        access_tok = res.get("access_token")
        refresh_tok = res.get("refresh_token")
        if access_tok:
            self.token_manager.save_tokens(access_tok, refresh_tok or "")
        self.token_manager.storage.store_credential("device_id", self.config.device_id)
        return {"status": "enrolled", **res}

    def enroll_device(self, public_key_hex: str, hostname: str, os_name: str, os_version: str) -> Dict[str, Any]:
        """Register student device with backend (/api/v1/agent/devices/register)."""
        payload = {
            "device_name": hostname,
            "device_identifier": self.config.device_id,
            "public_key": public_key_hex,
            "platform": os_name,
            "agent_version": self.config.agent_version
        }
        try:
            res = self._make_request("/api/v1/agent/devices/register", method="POST", data=payload, auth_required=True)
            self.token_manager.storage.store_credential("device_id", self.config.device_id)
            return {"status": "enrolled", **res}
        except Exception as err:
            LOGGER.debug("v1 register endpoint fallback: %s", err)
            # Legacy fallback
            fallback_payload = {
                "device_id": self.config.device_id,
                "public_key": public_key_hex,
                "hostname": hostname,
                "os_name": os_name,
                "os_version": os_version,
                "agent_version": self.config.agent_version
            }
            res = self._make_request("/api/agent/enroll", method="POST", data=fallback_payload, auth_required=True)
            if res.get("status") == "enrolled":
                self.token_manager.storage.store_credential("device_id", self.config.device_id)
            return res


    def logout(self) -> bool:
        """Revoke server session and clear local credentials."""
        try:
            refresh_tok = self.token_manager.get_refresh_token()
            payload = {"refresh_token": refresh_tok} if refresh_tok else None
            self._make_request("/api/auth/logout", method="POST", data=payload, auth_required=True, retry=False)
        except Exception as err:
            LOGGER.warning("Server logout call failed (%s); proceeding with local wipe", redact_text(str(err)))
        
        self.token_manager.clear_session()
        return True

    # -------------------------------------------------------------------------
    # Policy & Telemetry Methods
    # -------------------------------------------------------------------------
    def fetch_policy(self) -> Dict[str, Any]:
        """Fetch latest verified policy structure from backend (/api/v1/agent/policies/active)."""
        try:
            return self._make_request("/api/v1/agent/policies/active", method="GET", auth_required=True)
        except Exception as err:
            LOGGER.debug("v1 active policies fallback: %s", err)
            endpoint = f"/api/agent/policies/active?deviceId={urllib.parse.quote(self.config.device_id)}"
            return self._make_request(endpoint, method="GET", auth_required=True)

    def fetch_config(self) -> Dict[str, Any]:
        """Fetch legacy agent config for backwards compatibility."""
        endpoint = f"/api/agent/config?deviceId={urllib.parse.quote(self.config.device_id)}"
        return self._make_request(endpoint, method="GET", auth_required=False)

    def send_telemetry_report(self, events: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """Post policy enforcement violations or activity logs (/api/v1/agent/telemetry/events)."""
        try:
            return self._make_request("/api/v1/agent/telemetry/events", method="POST", data=events, auth_required=True)
        except Exception as err:
            LOGGER.debug("v1 telemetry endpoint fallback: %s", err)
            return self._make_request("/api/agent/report", method="POST", data=events, auth_required=False)

    def send_heartbeat(
        self,
        active_app: str = "Unknown",
        status_str: str = "online",
        agent_installed: bool = True,
        agent_service_running: bool = True,
        application_control_status: Optional[str] = None,
        dns_enforcement_status: Optional[str] = None,
        usb_storage_restricted: bool = False,
        usb_storage_restriction_status: Optional[str] = None,
        policy_version: Optional[int] = None
    ) -> Dict[str, Any]:
        """Post active window, device status, and compliance metrics (/api/v1/agent/heartbeat)."""
        payload = {
            "device_id": self.config.device_id,
            "device_identifier": self.config.device_id,
            "agent_installed": agent_installed,
            "agent_version": self.config.agent_version,
            "agent_service_running": agent_service_running,
            "application_control_status": application_control_status or "active",
            "dns_enforcement_status": dns_enforcement_status or "normal",
            "usb_storage_restricted": usb_storage_restricted,
            "usb_storage_restriction_status": usb_storage_restriction_status,
            "policy_version": policy_version,
            "health_state": status_str,
            "active_session_state": status_str
        }
        try:
            return self._make_request("/api/v1/agent/heartbeat", method="POST", data=payload, auth_required=True, retry=False)
        except Exception as err:
            LOGGER.debug("v1 heartbeat fallback: %s", err)
            fallback_payload = {
                "agent_id": self.config.device_id,
                "student_id": self.token_manager.get_device_id() or self.config.device_id,
                "activeApp": active_app,
                "status": status_str
            }
            return self._make_request("/api/agent/heartbeat", method="POST", data=fallback_payload, auth_required=False, retry=False)

    def post(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        auth_required: bool = True,
        retry: bool = True
    ) -> Dict[str, Any]:
        """Perform a POST request against the backend."""
        payload = json if json is not None else data
        return self._make_request(endpoint, method="POST", data=payload, auth_required=auth_required, retry=retry)

    def get(
        self,
        endpoint: str,
        auth_required: bool = True,
        retry: bool = True
    ) -> Dict[str, Any]:
        """Perform a GET request against the backend."""
        return self._make_request(endpoint, method="GET", data=None, auth_required=auth_required, retry=retry)

    def send_engagement_window(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Post a 5-minute engagement feature window to backend."""
        return self.post("/api/v1/agent/telemetry/engagement-windows", json=payload, auth_required=True, retry=True)

