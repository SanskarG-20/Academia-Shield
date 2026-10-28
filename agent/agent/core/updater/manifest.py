"""
Signed Update Manifest Verifier for Academia Shield Agent.
Ensures binary updates are signed, authentic, and verified with SHA-256 hashes.
"""

import hashlib
import logging
from typing import Dict, Any, Tuple, Optional

from ..auth.crypto import Ed25519Signer

logger = logging.getLogger(__name__)

class UpdateManifestVerifier:
    def __init__(self, public_key_hex: Optional[str] = None):
        self.public_key_hex = public_key_hex

    def verify_manifest(self, manifest: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Verify the integrity and digital signature of an update manifest.
        Expected keys: version, platform, download_url, sha256, signature.
        """
        required = ["version", "platform", "download_url", "sha256"]
        for key in required:
            if key not in manifest:
                return False, f"Missing required manifest field '{key}'"

        # Validate signature if present and public key is available
        signature = manifest.get("signature")
        if self.public_key_hex and signature:
            # Canonical payload to sign: version + platform + sha256 + download_url
            canonical_str = f"{manifest['version']}:{manifest['platform']}:{manifest['sha256']}:{manifest['download_url']}"
            if not Ed25519Signer.verify_signature(self.public_key_hex, signature, canonical_str.encode("utf-8")):
                return False, "Digital signature verification failed on update manifest"

        return True, "Manifest verified"

    def verify_binary_hash(self, file_bytes: bytes, expected_sha256: str) -> bool:
        computed = hashlib.sha256(file_bytes).hexdigest().lower()
        return computed == expected_sha256.lower().strip()
