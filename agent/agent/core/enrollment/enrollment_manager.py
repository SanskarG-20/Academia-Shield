"""
Device Enrollment Manager.
Orchestrates keypair generation, secure private key retention,
and device registration with the Academia Shield backend.
"""

import logging
from typing import Optional, Dict, Any

from ...platforms.base import PlatformSecureStorage
from ..auth.crypto import Ed25519Signer
from .device_info import DeviceInfo, AGENT_VERSION


logger = logging.getLogger(__name__)

KEY_DEVICE_ID = "device_id"
KEY_DEVICE_IDENTIFIER = "device_identifier"
KEY_ED25519_PRIV = "ed25519_private_key"
KEY_ED25519_PUB = "ed25519_public_key"

class EnrollmentManager:
    def __init__(self, storage: PlatformSecureStorage, api_client=None):
        self.storage = storage
        self.api_client = api_client

    def is_enrolled(self) -> bool:
        device_id = self.storage.retrieve_secret(KEY_DEVICE_ID)
        priv_key = self.storage.retrieve_secret(KEY_ED25519_PRIV)
        pub_key = self.storage.retrieve_secret(KEY_ED25519_PUB)
        return bool(device_id and priv_key and pub_key)

    def get_enrollment_info(self) -> Dict[str, Optional[str]]:
        return {
            "device_id": self.storage.retrieve_secret(KEY_DEVICE_ID),
            "device_identifier": self.storage.retrieve_secret(KEY_DEVICE_IDENTIFIER),
            "public_key": self.storage.retrieve_secret(KEY_ED25519_PUB)
        }

    def get_private_key(self) -> Optional[str]:
        return self.storage.retrieve_secret(KEY_ED25519_PRIV)

    def get_public_key(self) -> Optional[str]:
        return self.storage.retrieve_secret(KEY_ED25519_PUB)

    def enroll_device(self, api_client=None) -> Dict[str, Any]:
        """
        Generates Ed25519 device keypair if not present, gathers hardware metadata,
        and registers the device with the backend endpoint `/api/v1/agent/devices/register`.
        """
        client = api_client or self.api_client
        if not client:
            raise ValueError("API client required for device enrollment")

        meta = DeviceInfo.get_device_metadata()

        # Retrieve or generate Ed25519 keypair
        priv_key = self.storage.retrieve_secret(KEY_ED25519_PRIV)
        pub_key = self.storage.retrieve_secret(KEY_ED25519_PUB)

        if not priv_key or not pub_key:
            priv_key, pub_key = Ed25519Signer.generate_keypair()
            self.storage.store_secret(KEY_ED25519_PRIV, priv_key)
            self.storage.store_secret(KEY_ED25519_PUB, pub_key)

        self.storage.store_secret(KEY_DEVICE_IDENTIFIER, meta["device_identifier"])

        payload = {
            "device_name": meta["device_name"],
            "device_identifier": meta["device_identifier"],
            "public_key": pub_key,
            "platform": meta["platform"],
            "agent_version": meta["agent_version"]
        }

        resp = client.post("/api/v1/agent/devices/register", json=payload)
        if resp.get("status_code", 200) in (200, 201) and "device_id" in resp.get("data", {}):
            data = resp["data"]
            device_id = str(data["device_id"])
            self.storage.store_secret(KEY_DEVICE_ID, device_id)
            return {
                "success": True,
                "device_id": device_id,
                "device_identifier": meta["device_identifier"],
                "public_key": pub_key,
                "platform": meta["platform"]
            }
        else:
            error_msg = resp.get("error", "Device registration failed")
            logger.error(f"Enrollment failed: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

    def clear_enrollment(self):
        self.storage.delete_secret(KEY_DEVICE_ID)
        self.storage.delete_secret(KEY_DEVICE_IDENTIFIER)
        self.storage.delete_secret(KEY_ED25519_PRIV)
        self.storage.delete_secret(KEY_ED25519_PUB)
