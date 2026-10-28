"""
Platform Abstraction Interfaces for Academia Shield Local Agent.
Defines standard status contracts and interfaces for Windows and macOS adapters.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime

class PlatformCapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    UNAVAILABLE = "unavailable"
    REQUIRES_USER_APPROVAL = "requires_user_approval"
    REQUIRES_MDM = "requires_mdm"
    ACTIVE = "active"
    ERROR = "error"


class PlatformStatusResult:
    def __init__(
        self,
        status: PlatformCapabilityStatus,
        message: str = "",
        details: Optional[Dict[str, Any]] = None
    ):
        self.status = status
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "details": self.details
        }

    def __repr__(self) -> str:
        return f"<PlatformStatusResult status={self.status.value} message='{self.message}'>"


class PlatformSecureStorage(ABC):
    """Secure credential and key storage (Windows Credential Manager/DPAPI or macOS Keychain)."""

    @abstractmethod
    def store_secret(self, key: str, value: str) -> PlatformStatusResult:
        """Securely store a secret key-value pair."""
        pass

    @abstractmethod
    def retrieve_secret(self, key: str) -> Optional[str]:
        """Retrieve a stored secret by key."""
        pass

    @abstractmethod
    def delete_secret(self, key: str) -> PlatformStatusResult:
        """Delete a stored secret by key."""
        pass

    @abstractmethod
    def clear_all(self) -> PlatformStatusResult:
        """Purge all agent secrets."""
        pass


class PlatformServiceLifecycle(ABC):
    """Background service / daemon lifecycle management (Windows Service or macOS launchd)."""

    @abstractmethod
    def get_status(self) -> PlatformStatusResult:
        """Query if background service is installed and running."""
        pass

    @abstractmethod
    def install_service(self, run_as_system: bool = False) -> PlatformStatusResult:
        """Register the agent background service/daemon."""
        pass

    @abstractmethod
    def start_service(self) -> PlatformStatusResult:
        """Start the background service/daemon."""
        pass

    @abstractmethod
    def stop_service(self) -> PlatformStatusResult:
        """Stop the background service/daemon."""
        pass

    @abstractmethod
    def uninstall_service(self) -> PlatformStatusResult:
        """Unregister the background service/daemon."""
        pass


class PlatformProcessMonitor(ABC):
    """Process monitoring and foreground application inspection."""

    @abstractmethod
    def get_status(self) -> PlatformStatusResult:
        """Check if process monitoring is supported and operational."""
        pass

    @abstractmethod
    def get_running_processes(self) -> List[Dict[str, Any]]:
        """List running process metadata safely."""
        pass

    @abstractmethod
    def handle_process_action(self, pid: int, process_name: str, action: str) -> PlatformStatusResult:
        """Execute a safe policy action ('log', 'warn', 'close'). Never kill protected processes."""
        pass


class PlatformDnsEnforcement(ABC):
    """Local DNS configuration and redirection management."""

    @abstractmethod
    def check_resolver_health(self, host: str = "127.0.0.1", port: int = 5353) -> bool:
        """Verify the local DNS proxy is responding before applying network settings."""
        pass

    @abstractmethod
    def apply_dns_redirect(self, dns_ip: str = "127.0.0.1", port: int = 5353) -> PlatformStatusResult:
        """Direct system/adapter DNS to local proxy after taking backup of original settings."""
        pass

    @abstractmethod
    def restore_original_dns(self) -> PlatformStatusResult:
        """Revert system/adapter DNS strictly to saved pre-enforcement configuration."""
        pass

    @abstractmethod
    def get_status(self) -> PlatformStatusResult:
        """Get current DNS enforcement status."""
        pass


class PlatformBrowserCompliance(ABC):
    """Browser compliance checking for managed/kiosk modes (e.g. Edge on Windows, Safari/Chrome on macOS)."""

    @abstractmethod
    def check_compliance(self) -> PlatformStatusResult:
        """Audit whether managed browser or kiosk profile is active."""
        pass


class PlatformApplicationControlCompliance(ABC):
    """Application Control compliance (WDAC on Windows, Gatekeeper/AppLocker/MDM on macOS)."""

    @abstractmethod
    def check_compliance(self) -> PlatformStatusResult:
        """Audit application control policy status."""
        pass


class PlatformUsbStorageCompliance(ABC):
    """Removable media and USB storage compliance inspection."""

    @abstractmethod
    def check_compliance(self) -> PlatformStatusResult:
        """Audit whether USB removable storage restrictions are enforced."""
        pass


class PlatformInstaller(ABC):
    """Platform package installer orchestrator."""

    @abstractmethod
    def install(self, options: Optional[Dict[str, Any]] = None) -> PlatformStatusResult:
        """Perform platform-specific installation with proper consent verification."""
        pass


class PlatformUninstaller(ABC):
    """Platform package uninstaller orchestrator."""

    @abstractmethod
    def uninstall(self, purge_data: bool = False) -> PlatformStatusResult:
        """Cleanly remove agent components and restore any agent-managed system settings."""
        pass
