"""
Academia Shield Agent — Enforcement Engine Interface

Both the Hosts and DNS engines implement this contract so
the orchestrator can swap between them via a config flag.
"""

from abc import ABC, abstractmethod
from typing import List


class EnforcementEngine(ABC):
    """Abstract base class for domain-blocking enforcement engines."""

    @abstractmethod
    def apply_rules(self, domains: List[str]) -> bool:
        """
        Block the given domains.

        Args:
            domains: List of domain strings to block (e.g. ["youtube.com", "instagram.com"]).

        Returns:
            True if the rules were applied successfully.
        """
        ...

    @abstractmethod
    def restore_rules(self) -> bool:
        """
        Remove all managed blocks, restoring the original system state.

        Returns:
            True if the restore was successful.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this engine can run on the current system.

        Returns:
            True if the engine has all prerequisites met.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging (e.g. 'Hosts File Engine')."""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """
        Perform any necessary cleanup and shutdown the engine safely.
        """
        ...
