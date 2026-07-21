"""
Academia Shield Agent — .env loader
Add this to the top of agent.py to automatically load .env files.
"""

import os
from pathlib import Path


def load_env_file(env_file_path):
    """Load environment variables from a .env file."""
    if not os.path.exists(env_file_path):
        return
    
    with open(env_file_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


# Auto-load .env file based on NODE_ENV
env_file = Path(__file__).parent / f".env.{os.getenv('NODE_ENV', 'development')}"
load_env_file(str(env_file))

# Fall back to .env
load_env_file(str(Path(__file__).parent / ".env"))
