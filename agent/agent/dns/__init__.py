"""
DNS Package Module.
"""

from .protocol import DNSPacket, DNSQuestion, DNSResourceRecord, normalize_domain_name
from .rules import DomainRuleMatcher, PolicyDomainRule
from .upstream import UpstreamResolver
from .cache import DNSCache
from .resolver import LocalDNSResolver
from .server import LocalDNSServer
from .configuration import DNSConfigurationLifecycle

__all__ = [
    "DNSPacket",
    "DNSQuestion",
    "DNSResourceRecord",
    "normalize_domain_name",
    "DomainRuleMatcher",
    "PolicyDomainRule",
    "UpstreamResolver",
    "DNSCache",
    "LocalDNSResolver",
    "LocalDNSServer",
    "DNSConfigurationLifecycle"
]
