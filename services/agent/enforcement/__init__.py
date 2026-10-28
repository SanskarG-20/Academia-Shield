"""
Academia Shield Agent — Enforcement package

Exposes the enforcement engines and a factory that picks the right one
for the current machine.

    from enforcement import get_engine, normalize_domain_list

Engines:
    HostsEnforcementEngine — writes to the OS hosts file (default, cross-platform)
    DnsEnforcementEngine   — retained only to restore legacy DNS backups

get_engine() uses hosts enforcement; DNS redirection is disabled to avoid
machine-wide DNS outages after agent failure.
"""

import logging

from enforcement.base import EnforcementEngine
from enforcement.hosts import (
    HostsEnforcementEngine,
    normalize_domain,
    normalize_domain_list,
)

LOGGER = logging.getLogger("academia_shield_agent")

__all__ = [
    "EnforcementEngine",
    "HostsEnforcementEngine",
    "get_engine",
    "normalize_domain",
    "normalize_domain_list",
]


def get_engine(mode=None):
    """
    Select an enforcement engine.

    Args:
        mode: "DNS" or "HOSTS". DNS requests safely fall back to hosts.

    Returns:
        A hosts enforcement engine. Never None; permission errors surface at
        apply_rules() time and are retried.
    """
    if mode is None:
        from config import ENFORCEMENT_MODE

        mode = ENFORCEMENT_MODE

    if str(mode).strip().upper() == "DNS":
        LOGGER.warning("DNS redirection is disabled for device safety; using hosts enforcement")

    engine = HostsEnforcementEngine()
    if not engine.is_available():
        LOGGER.error(
            "Hosts engine is not writable — run the agent as administrator. "
            "Enforcement will be retried each cycle."
        )

    return engine


def restore_previous_system_state():
    """Clean up managed settings even if the configured engine changed."""
    hosts_ok = HostsEnforcementEngine().restore_rules()
    from enforcement.dns import _restore_dns_from_backup
    dns_ok = _restore_dns_from_backup()
    return hosts_ok and dns_ok
