"""Activity tracking module — cross-platform foreground window monitoring."""

import platform
import logging

LOGGER = logging.getLogger("academia_shield")


def get_activity_tracker():
    """Return a platform-specific ActivityTracker instance."""
    system = platform.system()
    if system == "Windows":
        from activity.windows import WindowsActivityTracker
        return WindowsActivityTracker()
    else:
        LOGGER.warning("Activity tracking not supported on %s. Using stub.", system)
        from activity.base import ActivityTrackerStub
        return ActivityTrackerStub()
