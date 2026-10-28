"""
Academia Shield Agent Root Package.
Exposes core, cli, auth, policy, dns, monitoring, ui, and platforms.
"""

import os
import sys

_sub_pkg = os.path.join(os.path.dirname(__file__), "agent")
if _sub_pkg not in __path__:
    __path__.append(_sub_pkg)
