"""
Academia Shield Desktop Agent — Main Orchestrator Entry Point

Usage:
  python agent.py enroll    # Real authentication and Ed25519 key enrollment
  python agent.py run       # Run background agent service (policy sync, DNS, process monitor)
  python agent.py logout    # Revoke session and clear OS credentials
  python agent.py status    # Display status
  python agent.py uninstall # Remove agent configuration
"""

import sys
import os

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from agent.cli.main import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("run")
    main()
