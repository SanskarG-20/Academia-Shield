"""Base class for cross-platform activity tracking."""

import time
import re
import logging
from abc import ABC, abstractmethod
from collections import deque
from threading import Lock

LOGGER = logging.getLogger("academia_shield")

# Browser process names (lowercase) -> used to detect browser windows
BROWSER_PROCESSES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "vivaldi.exe", "iexplore.exe", "safari",
    "chromium", "chrome", "firefox", "msedge", "brave",
}

# Known domain patterns in browser title bars
# Most browsers show: "<Page Title> - <Browser Name>" or "<Page Title> — <Browser Name>"
# Some show the URL in the title for certain pages
DOMAIN_REGEX = re.compile(
    r'(?:https?://)?'           # optional scheme
    r'(?:www\.)?'               # optional www
    r'([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?' # domain
    r'(?:\.[a-zA-Z]{2,})+)',    # TLD
    re.IGNORECASE
)

# Map well-known page titles to domains
TITLE_TO_DOMAIN = {
    "youtube": "youtube.com",
    "instagram": "instagram.com",
    "facebook": "facebook.com",
    "twitter": "twitter.com",
    "whatsapp": "web.whatsapp.com",
    "telegram": "web.telegram.org",
    "reddit": "reddit.com",
    "netflix": "netflix.com",
    "amazon": "amazon.com",
    "linkedin": "linkedin.com",
    "github": "github.com",
    "stackoverflow": "stackoverflow.com",
    "stack overflow": "stackoverflow.com",
    "wikipedia": "wikipedia.org",
    "google": "google.com",
    "gmail": "mail.google.com",
    "google docs": "docs.google.com",
    "google sheets": "sheets.google.com",
    "google slides": "slides.google.com",
    "discord": "discord.com",
    "spotify": "open.spotify.com",
    "chatgpt": "chatgpt.com",
    "slack": "slack.com",
    "notion": "notion.so",
    "figma": "figma.com",
    "canva": "canva.com",
    "zoom": "zoom.us",
    "microsoft teams": "teams.microsoft.com",
}


def extract_domain_from_title(title, process_name=""):
    """Attempt to extract a domain from a browser window title.

    Returns the domain string or None if extraction fails.
    Only attempts extraction if the process is a known browser.
    """
    if not title:
        return None

    proc_lower = (process_name or "").lower().replace(".exe", "")
    is_browser = any(b.replace(".exe", "") in proc_lower for b in BROWSER_PROCESSES) if proc_lower else False

    if not is_browser:
        return None

    # Strategy 1: Direct URL in title
    match = DOMAIN_REGEX.search(title)
    if match:
        return match.group(1).lower()

    # Strategy 2: Known title keywords
    title_lower = title.lower()
    # Remove browser suffix (e.g. " - Google Chrome", " — Mozilla Firefox")
    for sep in [" - ", " — ", " – "]:
        if sep in title_lower:
            title_lower = title_lower.rsplit(sep, 1)[0].strip()
            break

    for keyword, domain in TITLE_TO_DOMAIN.items():
        if keyword in title_lower:
            return domain

    return None


class ActivityEvent:
    """A single foreground activity event."""
    __slots__ = (
        "application", "domain", "title", "status",
        "started_at", "ended_at",
    )

    def __init__(self, application, title="", domain=None, status="ALLOWED",
                 started_at=None, ended_at=None):
        self.application = application
        self.title = (title or "")[:200]  # Truncate to 200 chars
        self.domain = domain
        self.status = status  # "ALLOWED" or "BLOCKED"
        self.started_at = started_at or time.time()
        self.ended_at = ended_at or self.started_at

    @property
    def duration_ms(self):
        return int((self.ended_at - self.started_at) * 1000)

    def to_dict(self):
        return {
            "application": self.application,
            "domain": self.domain,
            "title": self.title,
            "status": self.status,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "durationMs": self.duration_ms,
        }


class BaseActivityTracker(ABC):
    """Abstract base for platform-specific activity trackers."""

    def __init__(self, max_buffer=500):
        self._buffer = deque(maxlen=max_buffer)
        self._lock = Lock()
        self._current_event = None
        self._blocked_domains = set()
        self._running = False

    def set_blocked_domains(self, domains):
        """Update the set of currently blocked domains."""
        self._blocked_domains = {d.lower() for d in (domains or [])}

    def flush(self):
        """Return all buffered events and clear the buffer."""
        with self._lock:
            # Finalize current event
            if self._current_event:
                self._current_event.ended_at = time.time()
                # Only add if duration > 1 second
                if self._current_event.duration_ms > 1000:
                    self._buffer.append(self._current_event)
                # Don't clear current_event — it's still the active window
                # Just snapshot it into the buffer
                self._current_event = ActivityEvent(
                    application=self._current_event.application,
                    title=self._current_event.title,
                    domain=self._current_event.domain,
                    status=self._current_event.status,
                    started_at=time.time(),
                )

            events = list(self._buffer)
            self._buffer.clear()
            return [e.to_dict() for e in events]

    def _on_window_change(self, application, title):
        """Called when the foreground window changes. Handles event lifecycle."""
        now = time.time()

        with self._lock:
            # Finalize previous event
            if self._current_event:
                self._current_event.ended_at = now
                if self._current_event.duration_ms > 1000:
                    self._buffer.append(self._current_event)

            # Extract domain if this is a browser
            domain = extract_domain_from_title(title, application)

            # Determine blocked status
            status = "ALLOWED"
            if domain and domain.lower() in self._blocked_domains:
                status = "BLOCKED"

            # Start new event
            self._current_event = ActivityEvent(
                application=application,
                title=title,
                domain=domain,
                status=status,
                started_at=now,
            )

    @abstractmethod
    def start(self):
        """Start tracking foreground window changes."""
        pass

    @abstractmethod
    def stop(self):
        """Stop tracking."""
        pass


class ActivityTrackerStub(BaseActivityTracker):
    """No-op stub for unsupported platforms."""

    def start(self):
        LOGGER.info("Activity tracking is not supported on this platform.")
        self._running = True

    def stop(self):
        self._running = False
