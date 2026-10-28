"""
Root Build Helper for Academia Shield Windows Release Pipeline.
Invokes agent/build_installer.py.
"""

import sys
import os
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    script_path = os.path.join(ROOT_DIR, "agent", "build_installer.py")
    subprocess.check_call([sys.executable, script_path], cwd=ROOT_DIR)
