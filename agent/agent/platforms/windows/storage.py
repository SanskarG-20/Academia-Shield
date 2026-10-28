"""
Windows Secure Storage Adapter.
Uses Windows Credential Manager / DPAPI for encrypted key and token storage.
"""

import sys
import json
import logging
from typing import Optional, Dict, Any

from ..base import PlatformSecureStorage, PlatformCapabilityStatus, PlatformStatusResult

logger = logging.getLogger(__name__)

SERVICE_NAME = "AcademiaShield"

class WindowsSecureStorage(PlatformSecureStorage):
    """
    Secure storage backed by Windows Credential Manager / DPAPI.
    Uses keyring (Windows Credential Locker) with DPAPI fallback.
    """

    def __init__(self, service_name: str = SERVICE_NAME):
        self.service_name = service_name
        self._in_memory_fallback: Dict[str, str] = {}

    def _is_windows(self) -> bool:
        return sys.platform.startswith("win")

    def store_secret(self, key: str, value: str) -> PlatformStatusResult:
        if not self._is_windows():
            self._in_memory_fallback[key] = value
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="Windows secure storage unavailable on non-Windows OS (using fallback cache)"
            )
        try:
            import keyring
            keyring.set_password(self.service_name, key, value)
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"Secret '{key}' stored securely via Windows Credential Manager"
            )
        except Exception as e:
            logger.warning(f"Keyring store failed: {e}. Falling back to DPAPI / memory.")
            try:
                import win32crypt
                import base64
                encrypted = win32crypt.CryptProtectData(value.encode("utf-8"), "AcademiaShieldKey", None, None, None, 0)
                self._in_memory_fallback[key] = base64.b64encode(encrypted).decode("ascii")
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.ACTIVE,
                    message=f"Secret '{key}' stored via Windows DPAPI"
                )
            except Exception as dpapi_err:
                self._in_memory_fallback[key] = value
                return PlatformStatusResult(
                    status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL,
                    message=f"DPAPI fallback used due to error: {dpapi_err}"
                )

    def retrieve_secret(self, key: str) -> Optional[str]:
        if not self._is_windows():
            return self._in_memory_fallback.get(key)
        try:
            import keyring
            secret = keyring.get_password(self.service_name, key)
            if secret:
                return secret
        except Exception as e:
            logger.debug(f"Keyring retrieve failed for {key}: {e}")

        # Check DPAPI fallback
        if key in self._in_memory_fallback:
            val = self._in_memory_fallback[key]
            try:
                import win32crypt
                import base64
                decoded = base64.b64decode(val.encode("ascii"))
                decrypted = win32crypt.CryptUnprotectData(decoded, None, None, None, 0)[1]
                return decrypted.decode("utf-8")
            except Exception:
                return val
        return None

    def delete_secret(self, key: str) -> PlatformStatusResult:
        self._in_memory_fallback.pop(key, None)
        if not self._is_windows():
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"Secret '{key}' removed from memory cache"
            )
        try:
            import keyring
            keyring.delete_password(self.service_name, key)
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"Secret '{key}' deleted from Windows Credential Manager"
            )
        except Exception as e:
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"Secret '{key}' purged (keyring note: {e})"
            )

    def clear_all(self) -> PlatformStatusResult:
        self._in_memory_fallback.clear()
        known_keys = [
            "ed25519_private_key",
            "ed25519_public_key",
            "access_token",
            "refresh_token",
            "student_credentials",
            "device_id"
        ]
        for k in known_keys:
            self.delete_secret(k)
        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ACTIVE,
            message="All stored secrets purged"
        )
