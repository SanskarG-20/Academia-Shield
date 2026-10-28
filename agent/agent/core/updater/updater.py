"""
Update Checker and Verifier for Academia Shield Agent.
Queries backend release endpoints, validates release manifest signatures with Ed25519,
and verifies SHA-256 package hashes before staging or applying updates.
"""

import sys
import os
import logging
from typing import Optional, Dict, Any, Tuple
import requests

from .manifest import UpdateManifestVerifier
from .integrity import AgentIntegrityChecker

logger = logging.getLogger("agent.updater")

class AgentUpdateChecker:
    """
    Checks for available agent releases and cryptographically verifies their manifests.
    """

    def __init__(self, api_url: str = "http://127.0.0.1:8000", current_version: str = "2.3.0", public_key_hex: Optional[str] = None):
        self.api_url = api_url.rstrip("/")
        self.current_version = current_version
        self.verifier = UpdateManifestVerifier(public_key_hex=public_key_hex)
        self.integrity_checker = AgentIntegrityChecker()

    def check_for_updates(self, platform: str = "windows") -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Query backend for latest release manifest and verify its cryptographic authenticity.
        Returns:
            (update_available, release_manifest, message)
        """
        try:
            url = f"{self.api_url}/api/v1/agent/releases/latest"
            res = requests.get(url, timeout=5)
            if res.status_code != 200:
                return False, None, f"Failed to retrieve releases from backend (HTTP {res.status_code})"

            data = res.json()
            latest_version = data.get("latest_version")
            releases = data.get("releases", {})
            manifest = releases.get(platform.lower())

            if not manifest:
                return False, None, f"No release manifest found for platform '{platform}'"

            # Verify manifest signature & structure
            is_valid, msg = self.verifier.verify_manifest(manifest)
            if not is_valid:
                return False, None, f"Release manifest verification failed: {msg}"

            update_available = (latest_version != self.current_version)
            return update_available, manifest, f"Latest version: {latest_version} (Current: {self.current_version})"

        except Exception as e:
            logger.debug(f"Update check error: {e}")
            return False, None, f"Update check error: {e}"
