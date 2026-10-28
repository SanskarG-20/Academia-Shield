"""
Server Clock Time Synchronization Adapter.

Maintains estimated server UTC time offset, monitors sync freshness,
validates clock skew limits, and supplies corrected UTC timestamps to agent evaluators.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

LOGGER = logging.getLogger(__name__)

class ServerClock:
    """Manages agent-side server time synchronization and clock-skew checking."""

    def __init__(
        self,
        max_allowed_skew_seconds: float = 120.0,
        stale_threshold_seconds: float = 300.0
    ):
        self.max_allowed_skew_seconds = max_allowed_skew_seconds
        self.stale_threshold_seconds = stale_threshold_seconds

        self._server_offset_seconds: float = 0.0
        self._last_sync_time: Optional[float] = None
        self._last_server_time_iso: Optional[str] = None
        self._sync_count: int = 0

    def update_from_server_time(
        self,
        server_time_iso_or_dt: Any,
        max_allowed_skew: Optional[float] = None,
        local_now_utc: Optional[datetime] = None
    ) -> float:
        """
        Update server time offset given server time string or datetime.
        Returns calculated offset in seconds.
        """
        now_local = local_now_utc or datetime.now(timezone.utc)
        if now_local.tzinfo is None:
            now_local = now_local.replace(tzinfo=timezone.utc)
        else:
            now_local = now_local.astimezone(timezone.utc)
        now_local_ts = time.time()

        if max_allowed_skew is not None:
            self.max_allowed_skew_seconds = max_allowed_skew

        if isinstance(server_time_iso_or_dt, str):
            clean_iso = server_time_iso_or_dt.replace("Z", "+00:00")
            server_dt = datetime.fromisoformat(clean_iso)
        elif isinstance(server_time_iso_or_dt, datetime):
            server_dt = server_time_iso_or_dt
        else:
            LOGGER.warning("Invalid server time format: %s", server_time_iso_or_dt)
            return self._server_offset_seconds

        if server_dt.tzinfo is None:
            server_dt = server_dt.replace(tzinfo=timezone.utc)
        else:
            server_dt = server_dt.astimezone(timezone.utc)

        offset = (server_dt - now_local).total_seconds()
        self._server_offset_seconds = offset
        self._last_sync_time = now_local_ts
        self._last_server_time_iso = server_dt.isoformat()
        self._sync_count += 1

        LOGGER.debug("Updated ServerClock offset: %.2fs (sync #%s)", offset, self._sync_count)
        return offset

    def get_server_offset_seconds(self) -> float:
        """Return current estimated server offset in seconds."""
        return self._server_offset_seconds

    def is_sync_stale(self) -> bool:
        """Check if time sync has not occurred within stale threshold window."""
        if self._last_sync_time is None:
            return True
        return (time.time() - self._last_sync_time) > self.stale_threshold_seconds

    def is_clock_skew_excessive(self) -> bool:
        """Check if absolute clock skew exceeds maximum allowed threshold."""
        return abs(self._server_offset_seconds) > self.max_allowed_skew_seconds

    def is_time_valid(self) -> bool:
        """Check if server time is valid (fresh sync and acceptable clock skew)."""
        if self._last_sync_time is None or self.is_sync_stale():
            return False
        return abs(self._server_offset_seconds) <= self.max_allowed_skew_seconds

    def get_corrected_utc_time(self, local_now_utc: Optional[datetime] = None) -> datetime:
        """Return server-corrected timezone-aware UTC datetime."""
        now = local_now_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)
        return now + timedelta(seconds=self._server_offset_seconds)
