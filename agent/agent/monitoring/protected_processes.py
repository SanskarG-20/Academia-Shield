"""
Protected Process Manager and Allowlist Safeguards.

Maintains system-critical OS processes, accessibility tools, security runtimes,
and Academia Shield Agent components that MUST NEVER be closed or terminated.
"""

import logging
from typing import Set, List, Dict, Any, Optional

LOGGER = logging.getLogger(__name__)

# Default system-critical protected process names (case-insensitive)
DEFAULT_PROTECTED_PROCESSES: Set[str] = {
    "explorer.exe",
    "svchost.exe",
    "csrss.exe",
    "smss.exe",
    "services.exe",
    "lsass.exe",
    "winlogon.exe",
    "taskmgr.exe",
    "msmpeng.exe",
    "securityhealthservice.exe",
    "system",
    "system idle process",
    "systemd",
    "init",
    "python.exe",
    "python",
    "python3",
    "pytest",
    "agent.exe",
    "acad_agent.exe",
    "academiashield.exe",
    "academia_shield_agent.exe",
    "academiashieldagent.exe",
    "narrator.exe",
    "magnify.exe",
    "osk.exe",
    "cmd.exe",
    "powershell.exe"
}

class ProtectedProcessManager:
    """Evaluates whether an application process is protected against close/termination."""

    def __init__(self, additional_protected: Optional[Set[str]] = None):
        self.protected_names: Set[str] = set(DEFAULT_PROTECTED_PROCESSES)
        if additional_protected:
            self.protected_names.update(p.strip().lower() for p in additional_protected if p)

    def update_from_policy(self, server_protected_list: List[Dict[str, Any]]) -> None:
        """Merge dynamic protected processes provided by backend policy."""
        self.protected_names = set(DEFAULT_PROTECTED_PROCESSES)
        for item in server_protected_list:
            if isinstance(item, dict):
                name = item.get("executable_name") or item.get("name")
            else:
                name = str(item)
            if name:
                self.protected_names.add(name.strip().lower())

    def is_protected(self, executable_name: str, executable_path: Optional[str] = None) -> bool:
        """
        Check if process is in the protected allowlist.
        Returns True if process is protected and MUST NOT be closed.
        """
        if not executable_name:
            return True

        clean_name = executable_name.strip().lower()
        clean_base = clean_name[:-4] if clean_name.endswith(".exe") else clean_name

        for p in self.protected_names:
            p_clean = p.strip().lower()
            p_base = p_clean[:-4] if p_clean.endswith(".exe") else p_clean
            if clean_name == p_clean or clean_base == p_base:
                return True

        return False
