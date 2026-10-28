"""
Pytest configuration and sys.path setup for Academia Shield Agent tests.
"""

import sys
import os

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)
