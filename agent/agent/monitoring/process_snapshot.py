"""
Process Metadata Snapshot and psutil Scanner.

Collects privacy-minimized process metadata (PID, executable name, executable path,
process owner, start time, foreground status) without inspecting process memory,
command-line arguments, open files, keystrokes, browser content, or user documents.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set

LOGGER = logging.getLogger(__name__)

@dataclass
class ProcessMetadata:
    """Privacy-minimized metadata for a running operating system process."""
    pid: int
    executable_name: str
    executable_path: Optional[str] = None
    owner: Optional[str] = None
    create_time: float = 0.0
    is_foreground: bool = False
    trusted_hash: Optional[str] = None

    def __post_init__(self):
        if self.executable_name:
            self.executable_name = self.executable_name.strip().lower()

class ProcessScanner:
    """Enumerates running processes using psutil with safe error handling."""

    def __init__(self, foreground_detector: Optional[Any] = None):
        self.foreground_detector = foreground_detector

    def get_foreground_pid(self) -> Optional[int]:
        """Detect current foreground window PID if platform adapter is available."""
        if self.foreground_detector and hasattr(self.foreground_detector, "get_foreground_process_id"):
            try:
                return self.foreground_detector.get_foreground_process_id()
            except Exception as err:
                LOGGER.debug("Foreground PID detection error: %s", err)
        return None

    def scan_processes(self) -> List[ProcessMetadata]:
        """Scan processes using psutil and return privacy-minimized snapshots."""
        try:
            import psutil
        except ImportError:
            LOGGER.warning("psutil package not available; skipping process scanning")
            return []

        foreground_pid = self.get_foreground_pid()
        snapshots = []

        for proc in psutil.process_iter(attrs=["pid", "name", "exe", "username", "create_time"]):
            try:
                info = proc.info
                pid = info.get("pid")
                raw_name = info.get("name")
                if pid is None or not raw_name:
                    continue

                exe_name = str(raw_name).strip().lower()
                exe_path = str(info.get("exe") or "").strip() if info.get("exe") else None
                owner = str(info.get("username") or "").strip() if info.get("username") else None
                create_time = float(info.get("create_time") or 0.0)

                is_fg = (pid == foreground_pid) if foreground_pid is not None else False

                snapshots.append(ProcessMetadata(
                    pid=pid,
                    executable_name=exe_name,
                    executable_path=exe_path,
                    owner=owner,
                    create_time=create_time,
                    is_foreground=is_fg
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as err:
                LOGGER.debug("Error retrieving process info for PID %s: %s", getattr(proc, "pid", "unknown"), err)
                continue

        return snapshots
