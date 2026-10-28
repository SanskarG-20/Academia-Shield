"""
Structured Logging with Automatic Secret Redaction.
"""

import logging
import re
import sys
from app.core.config import settings

# Sensitive patterns to redact from logs
SENSITIVE_PATTERNS = [
    r'(?i)(password|passwd|pwd)\s*[:=]\s*[\'"]?([^\s\'"&,]+)',
    r'(?i)(token|access_token|refresh_token|secret|jwt_secret|api_key)\s*[:=]\s*[\'"]?([^\s\'"&,]+)',
    r'(?i)(authorization|bearer)\s*[:=]\s*[\'"]?([^\s\'"&,]+)',
]

class SecretRedactingFormatter(logging.Formatter):
    """Custom logging formatter that replaces sensitive values with '[REDACTED]'."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        redacted = original
        for pattern in SENSITIVE_PATTERNS:
            redacted = re.sub(pattern, r'\1=[REDACTED]', redacted)
        if settings.JWT_SECRET and len(settings.JWT_SECRET) > 4:
            redacted = redacted.replace(settings.JWT_SECRET, '[REDACTED_JWT_SECRET]')
        return redacted

def setup_logging():
    """Configures structured logging for the FastAPI application."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger = logging.getLogger("academia_shield")
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = SecretRedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

logger = setup_logging()
