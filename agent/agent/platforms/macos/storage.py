"""
macOS Secure Storage Adapter.
Uses macOS Keychain via `security` CLI and keyring for secure token and key storage.
"""

import sys
import subprocess
import logging
from typing import Optional, Dict, Any

from ..base import PlatformSecureStorage, PlatformCapabilityStatus, PlatformStatusResult

logger = logging.getLogger(__name__)

SERVICE_NAME = "org.academiashield.agent"

class MacosSecureStorage(PlatformSecureStorage):
    """
    Secure storage backed by macOS Keychain.
    Uses `keyring` (macOS Keychain Services) or native `/usr/bin/security`.
    """

    def __init__(self, service_name: str = SERVICE_NAME):
        self.service_name = service_name
        self._in_memory_fallback: Dict[str, str] = {}

    def _is_macos(self) -> bool:
        return sys.platform == "darwin"

    def store_secret(self, key: str, value: str) -> PlatformStatusResult:
        if not self._is_macos():
            self._in_memory_fallback[key] = value
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.UNAVAILABLE,
                message="macOS Keychain unavailable on non-macOS host (using fallback cache)"
            )
        try:
            import keyring
            keyring.set_password(self.service_name, key, value)
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.ACTIVE,
                message=f"Secret '{key}' securely stored in macOS Keychain"
            )
        except Exception as e:
            # Fallback to macOS `security` tool
            try:
                cmd = [
                    "/usr/bin/security", "add-generic-password",
                    "-U",
                    "-s", self.service_name,
                    "-a", key,
                    "-w", value
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    return PlatformStatusResult(
                        status=PlatformCapabilityStatus.ACTIVE,
                        message=f"Secret '{key}' stored in Keychain via security tool"
                    )
            except Exception as sec_err:
                logger.warning(f"Keychain storage failed: {sec_err}")

            self._in_memory_fallback[key] = value
            return PlatformStatusResult(
                status=PlatformCapabilityStatus.REQUIRES_USER_APPROVAL,
                message=f"Keychain store failed: {e}. Fallback cache used."
            )

    def retrieve_secret(self, key: str) -> Optional[str]:
        if not self._is_macos():
            return self._in_memory_fallback.get(key)
        try:
            import keyring
            secret = keyring.get_password(self.service_name, key)
            if secret:
                return secret
        except Exception as e:
            logger.debug(f"Keyring retrieve failed on macOS for {key}: {e}")

        # Fallback to macOS security find-generic-password
        try:
            cmd = ["/usr/bin/security", "find-generic-password", "-s", self.service_name, "-a", key, "-w"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

        return self._in_memory_fallback.get(key)

    def delete_secret(self, key: str) -> PlatformStatusResult:
        self._in_memory_fallback.pop(key, None)
        if not self._is_macos():
            return PlatformStatusResult(status=PlatformCapabilityStatus.ACTIVE, message=f"Deleted '{key}'")
        try:
            import keyring
            keyring.delete_password(self.service_name, key)
        except Exception:
            try:
                cmd = ["/usr/bin/security", "delete-generic-password", "-s", self.service_name, "-a", key]
                subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            except Exception:
                pass
        return PlatformStatusResult(
            status=PlatformCapabilityStatus.ACTIVE,
            message=f"Secret '{key}' removed from macOS Keychain"
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
            message="macOS Keychain secrets cleared"
        )
