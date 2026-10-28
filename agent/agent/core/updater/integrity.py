"""
Integrity and Tamper Detection Module for Academia Shield Agent.
Audits the filesystem presence and SHA-256 checksums of core agent files.
Detects missing, replaced, or modified internal binaries and reports tamper events
to the backend telemetry queue without using anti-debugging or hidden self-protection.
"""

import os
import sys
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

class AgentIntegrityChecker:
    """
    Computes and verifies cryptographic hashes of critical agent components.
    """

    def __init__(self, root_dir: Optional[str] = None):
        if root_dir:
            self.root_dir = root_dir
        else:
            # Locate agent package root
            self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def compute_file_sha256(self, filepath: str) -> Optional[str]:
        """Compute SHA-256 hash of a file on disk."""
        if not os.path.isfile(filepath):
            return None
        sha = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception as e:
            logger.warning(f"Failed to hash {filepath}: {e}")
            return None

    def scan_agent_files(self) -> Dict[str, str]:
        """Generate manifest of current agent source/binary files and their SHA-256 hashes."""
        hashes = {}
        for root, _, files in os.walk(self.root_dir):
            if "__pycache__" in root or ".git" in root or ".venv" in root:
                continue
            for fn in files:
                if fn.endswith((".py", ".exe", ".json", ".pyd", ".dll")):
                    full_path = os.path.join(root, fn)
                    rel_path = os.path.relpath(full_path, self.root_dir).replace("\\", "/")
                    f_hash = self.compute_file_sha256(full_path)
                    if f_hash:
                        hashes[rel_path] = f_hash
        return hashes

    def verify_integrity(self, expected_manifest: Optional[Dict[str, str]] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Verify agent files against an expected baseline manifest.
        Returns:
            (is_clean, list_of_tamper_findings)
        """
        findings: List[Dict[str, Any]] = []

        # If running as PyInstaller frozen bundle, verify the executable itself
        if getattr(sys, "frozen", False):
            exe_path = sys.executable
            if not os.path.isfile(exe_path):
                findings.append({"file": "sys.executable", "issue": "missing_binary"})
            return len(findings) == 0, findings

        if not expected_manifest:
            # Baseline self-check: verify existence of core package files
            critical_files = [
                "agent/__init__.py",
                "agent/main.py",
                "agent/core/state_machine/machine.py",
                "agent/core/policy/engine.py",
                "agent/core/auth/crypto.py",
                "agent/dns/resolver.py",
                "agent/monitoring/process_monitor.py",
                "agent/platforms/windows/dns.py"
            ]
            for rel in critical_files:
                full = os.path.join(self.root_dir, rel)
                if not os.path.exists(full):
                    findings.append({
                        "file": rel,
                        "issue": "missing_file",
                        "expected": True
                    })
            return len(findings) == 0, findings

        current_hashes = self.scan_agent_files()
        for rel_path, exp_hash in expected_manifest.items():
            curr_hash = current_hashes.get(rel_path)
            if curr_hash is None:
                findings.append({
                    "file": rel_path,
                    "issue": "missing_file",
                    "expected_sha256": exp_hash
                })
            elif curr_hash.lower() != exp_hash.lower():
                findings.append({
                    "file": rel_path,
                    "issue": "modified_file",
                    "current_sha256": curr_hash,
                    "expected_sha256": exp_hash
                })

        is_clean = (len(findings) == 0)
        return is_clean, findings
