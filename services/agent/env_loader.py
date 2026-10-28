"""
Academia Shield Agent — .env loader

Call load_env() once, before `config` is imported, so that every module
sees a fully populated os.environ.

Lookup order (first file that defines a key wins, and real environment
variables always win over file values):

    1. Stable ProgramData installation directory (frozen Windows agent)
    2. The directory containing this source file   (development)
    3. The PyInstaller extraction dir, sys._MEIPASS (bundled .env.production)

Within each directory we try `.env.<NODE_ENV>` first, then plain `.env`.

NODE_ENV defaults to "production" for a frozen (PyInstaller) build and
"development" when running from source, so the installed .exe picks up the
.env.production that the installer writes next to it.
"""

import os
import sys

DEV_NODE_ENV = "development"
FROZEN_NODE_ENV = "production"


def default_node_env():
    """development when running from source, production for a built .exe."""
    return FROZEN_NODE_ENV if getattr(sys, "frozen", False) else DEV_NODE_ENV


def _candidate_dirs():
    """Directories to search for .env files, in priority order."""
    dirs = []

    # A downloaded executable must not trust a configuration planted next to
    # it in Downloads. Frozen Windows builds use only stable ProgramData state.
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            dirs.append(os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "AcademiaShield"))
        else:
            dirs.append(os.path.dirname(os.path.abspath(sys.executable)))

    # 2. Next to this source file (development runs).
    dirs.append(os.path.dirname(os.path.abspath(__file__)))

    # 3. PyInstaller's temporary extraction dir (files added via --add-data).
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)

    # Preserve order while removing duplicates.
    seen = set()
    unique = []
    for directory in dirs:
        normalized = os.path.normcase(os.path.normpath(directory))
        if normalized not in seen:
            seen.add(normalized)
            unique.append(directory)
    return unique


def load_env_file(env_file_path, override=False):
    """
    Load environment variables from a single .env file.

    Existing environment variables are preserved unless override=True.
    Returns True if the file existed and was read.
    """
    if not os.path.exists(env_file_path):
        return False

    try:
        with open(env_file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if not key:
                    continue

                if override:
                    os.environ[key] = value
                else:
                    os.environ.setdefault(key, value)
    except OSError:
        # A malformed or unreadable .env file must never stop the agent.
        return False

    return True


def load_env(node_env=None):
    """
    Load .env files into os.environ.

    Must be called before `config` is imported, because config.py reads
    os.environ at import time.

    Returns the list of files that were loaded.
    """
    node_env = node_env or os.getenv("NODE_ENV") or default_node_env()
    filenames = [f".env.{node_env}", ".env"]

    loaded = []
    for directory in _candidate_dirs():
        for filename in filenames:
            path = os.path.join(directory, filename)
            if load_env_file(path):
                loaded.append(path)

    return loaded
