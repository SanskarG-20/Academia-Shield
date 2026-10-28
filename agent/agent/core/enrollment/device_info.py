"""
Hardware metadata probe and device identification.
"""

import sys
import os
import socket
import hashlib
import platform
import uuid
from typing import Dict, Any

AGENT_VERSION = "2.3.0"

class DeviceInfo:
    @staticmethod
    def get_hardware_identifier() -> str:
        """
        Derive a stable hardware identifier based on machine characteristics.
        """
        components = [
            socket.gethostname(),
            platform.machine(),
            platform.system(),
            str(uuid.getnode()) # MAC address integer
        ]
        raw = "-".join(components)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def get_device_metadata() -> Dict[str, Any]:
        os_platform = "windows" if sys.platform.startswith("win") else ("macos" if sys.platform == "darwin" else "linux")
        return {
            "device_name": socket.gethostname(),
            "device_identifier": DeviceInfo.get_hardware_identifier(),
            "platform": os_platform,
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "agent_version": AGENT_VERSION
        }
