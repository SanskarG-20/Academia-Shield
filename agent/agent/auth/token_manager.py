"""
Token Lifecycle & Session Manager.

Handles access token expiration, refresh token rotation, secure credential storage,
and session validation.
"""

import time
import json
import base64
import logging
from typing import Optional, Dict, Any
from .keyring_store import SecureStorageManager

LOGGER = logging.getLogger(__name__)

class TokenManager:
    """Manages JWT tokens and device registration credentials."""

    def __init__(self, storage: Optional[SecureStorageManager] = None):
        self.storage = storage or SecureStorageManager()
        self._access_token: Optional[str] = self.storage.get_credential("access_token")
        self._refresh_token: Optional[str] = self.storage.get_credential("refresh_token")
        self._device_id: Optional[str] = self.storage.get_credential("device_id")

    def save_tokens(self, access_token: str, refresh_token: str, device_id: Optional[str] = None) -> bool:
        """Store access token, refresh token, and device_id securely."""
        self._access_token = access_token
        self._refresh_token = refresh_token
        
        ok1 = self.storage.store_credential("access_token", access_token)
        ok2 = self.storage.store_credential("refresh_token", refresh_token)
        
        if device_id:
            self._device_id = device_id
            self.storage.store_credential("device_id", device_id)
            
        return ok1 and ok2

    def get_access_token(self) -> Optional[str]:
        """Return cached access token if present and valid."""
        if not self._access_token:
            self._access_token = self.storage.get_credential("access_token")
        return self._access_token

    def get_refresh_token(self) -> Optional[str]:
        """Return cached refresh token."""
        if not self._refresh_token:
            self._refresh_token = self.storage.get_credential("refresh_token")
        return self._refresh_token

    def get_device_id(self) -> Optional[str]:
        """Return cached device ID."""
        if not self._device_id:
            self._device_id = self.storage.get_credential("device_id")
        return self._device_id

    def is_access_token_expired(self, buffer_seconds: int = 30) -> bool:
        """Check if JWT access token is expired or about to expire."""
        token = self.get_access_token()
        if not token:
            return True
        payload = self._decode_jwt_payload_unverified(token)
        if not payload:
            return True
        exp = payload.get("exp")
        if not exp:
            return False
        now = time.time()
        return (exp - buffer_seconds) < now

    def clear_session(self) -> bool:
        """Revoke and delete all stored local tokens and device credentials."""
        self._access_token = None
        self._refresh_token = None
        self._device_id = None
        return self.storage.clear_all()

    def _decode_jwt_payload_unverified(self, token: str) -> Optional[Dict[str, Any]]:
        """Safely parse JWT payload JSON without verification (for local expiry checking)."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            payload_b64 = parts[1]
            # Add padding
            rem = len(payload_b64) % 4
            if rem > 0:
                payload_b64 += "=" * (4 - rem)
            decoded_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
            return json.loads(decoded_bytes.decode("utf-8"))
        except Exception:
            return None
