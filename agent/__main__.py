"""
Root Entry point for python -m agent
"""
import sys
import os

pkg_dir = os.path.dirname(os.path.abspath(__file__))
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

try:
    from agent.cli.main import main
except Exception:
    try:
        from agent.agent.cli.main import main
    except Exception:
        from cli.main import main

if __name__ == "__main__":
    main()
