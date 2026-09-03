"""
Academia Shield Agent — Enforcement package

Exposes the enforcement engines and a factory that picks the right one
for the current machine.

    from enforcement import get_engine, normalize_domain_list

Engines:
    HostsEnforcementEngine — writes to the OS hosts file (default, cross-platform)
    DnsEnforcementEngine   — local DNS resolver on 127.0.0.1:53 (Windows only)

get_engine() always returns a usable engine object. If the requested engine
is unavailable it falls back to the hosts engine, so callers never have to
handle a None return.
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


def _load_dns_engine():
    """
    Try to build the DNS engine. Returns the engine or None.

    The DNS engine needs port 53 and netsh, so failure here is expected on
    most machines and must never be fatal.
    """
    try:
        from enforcement.dns import DnsEnforcementEngine
    except ImportError as err:
        LOGGER.warning("DNS engine could not be imported (%s) — falling back to HOSTS mode", err)
        return None

    try:
        engine = DnsEnforcementEngine()
    except Exception as err:
        LOGGER.warning("DNS engine initialisation failed (%s) — falling back to HOSTS mode", err)
        return None

    if not engine.is_available():
        LOGGER.warning("DNS engine is not available on this system — falling back to HOSTS mode")
        return None

    LOGGER.info("DNS enforcement engine loaded successfully")
    return engine


def get_engine(mode=None):
    """
    Select an enforcement engine.

    Args:
        mode: "DNS" or "HOSTS". Defaults to config.ENFORCEMENT_MODE.

    Returns:
        An EnforcementEngine instance. Never None — if nothing is available
        the hosts engine is returned anyway and errors surface at
        apply_rules() time, where they are logged and retried.
    """
    if mode is None:
        from config import ENFORCEMENT_MODE

        mode = ENFORCEMENT_MODE

    if str(mode).strip().upper() == "DNS":
        engine = _load_dns_engine()
        if engine is not None:
            return engine

    engine = HostsEnforcementEngine()
    if not engine.is_available():
        LOGGER.error(
            "Hosts engine is not writable — run the agent as administrator. "
            "Enforcement will be retried each cycle."
        )

    return engine
