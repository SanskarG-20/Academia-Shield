"""
Abstract Base Class for Platform Adapters.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class BasePlatformAdapter(ABC):
    """Platform adapter interface for OS-specific operations."""

    @abstractmethod
    def is_admin(self) -> bool:
        """Check if agent process has elevated administrator/root rights."""
        pass

    @abstractmethod
    def show_notification(self, title: str, message: str) -> None:
        """Display local visible notification to user before policy enforcement."""
        pass

    @abstractmethod
    def terminate_process_gracefully(self, pid: int, process_name: str) -> bool:
        """Gracefully close explicitly blocked user application."""
        pass

    @abstractmethod
    def get_os_info(self) -> Dict[str, str]:
        """Return OS name and version."""
        pass
