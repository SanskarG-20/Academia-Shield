"""
Academia Shield Agent — Logger Module
"""

import sys
import logging
from logging.handlers import RotatingFileHandler
import os
from config import LOG_FILE


def setup_logger():
    """Create and configure the agent logger with console + file output."""
    logger = logging.getLogger("academia_shield_agent")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if os.path.islink(LOG_FILE):
        raise RuntimeError("Agent log path is a symbolic link")
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
