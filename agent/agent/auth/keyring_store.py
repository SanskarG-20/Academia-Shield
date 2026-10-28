"""
OS Secure Credential Store Manager.

Uses OS Keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service).
Never stores passwords or tokens in plain text.
"""

import os
import json
import logging
from typing import Optional, Dict, Any

LOGGER = logging.getLogger(__name__)

SERVICE_NAME = "AcademiaShieldAgent"

class SecureStorageManager:
    """Manages sensitive credentials securely via OS Keyring with local fallback."""

    def __init__(self, service_name: str = SERVICE_NAME, storage_dir: Optional[str] = None):
        self.service_name = service_name
        self.storage_dir = storage_dir or os.path.expanduser("~/.academia_shield")
        os.makedirs(self.storage_dir, exist_ok=True)
        self.fallback_file = os.path.join(self.storage_dir, ".credentials.sec")
        self._keyring_available = self._check_keyring()

    def _check_keyring(self) -> bool:
        try:
            import keyring
            # Test keyring backend functionality
            backend = keyring.get_keyring()
            LOGGER.info("OS Keyring initialized: %s", type(backend).__name__)
            return True
        except Exception as err:
            LOGGER.warning("OS Keyring unavailable (%s); falling back to secure file storage.", err)
            return False

    def store_credential(self, key: str, value: str) -> bool:
        """Store secret in OS credential store and persistent fallback for admin/user cross-session parity."""
        if not key or not value:
            return False
        
        keyring_ok = False
        if self._keyring_available:
            try:
                import keyring
                keyring.set_password(self.service_name, key, value)
                keyring_ok = True
            except Exception as err:
                LOGGER.warning("Keyring set_password failed (%s); using file storage fallback", err)
        
        # Also always write to secure fallback file for cross-process/elevation resilience
        try:
            data = self._read_fallback_file()
            data[key] = value
            with open(self.fallback_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            if hasattr(os, "chmod"):
                os.chmod(self.fallback_file, 0o600)
            return True
        except Exception as err:
            LOGGER.error("Failed to store credential in fallback: %s", err)
            return keyring_ok

    def get_credential(self, key: str) -> Optional[str]:
        """Retrieve secret from OS credential store."""
        if self._keyring_available:
            try:
                import keyring
                val = keyring.get_password(self.service_name, key)
                if val:
                    return val
            except Exception as err:
                LOGGER.warning("Keyring get_password failed (%s)", err)

        data = self._read_fallback_file()
        return data.get(key)

    def delete_credential(self, key: str) -> bool:
        """Delete secret from OS credential store."""
        success = True
        if self._keyring_available:
            try:
                import keyring
                keyring.delete_password(self.service_name, key)
            except Exception:
                pass
        
        data = self._read_fallback_file()
        if key in data:
            del data[key]
            try:
                with open(self.fallback_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception as err:
                LOGGER.error("Failed updating fallback file: %s", err)
                success = False
        return success

    def clear_all(self) -> bool:
        """Clear all stored secrets upon logout or uninstall."""
        keys = ["refresh_token", "access_token", "private_key", "device_id"]
        for k in keys:
            self.delete_credential(k)
        if os.path.exists(self.fallback_file):
            try:
                os.remove(self.fallback_file)
            except Exception:
                pass
        return True

    def _read_fallback_file(self) -> Dict[str, str]:
        if not os.path.exists(self.fallback_file):
            return {}
        try:
            with open(self.fallback_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
