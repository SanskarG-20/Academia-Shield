"""
DNS Telemetry Event Builder.

Formats authenticated, privacy-preserving DNS resolver telemetry events using UUID idempotency keys.
Strictly redacts packet payloads, user credentials, browsing content, or unrelated network activity.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

def create_dns_violation_event(
    device_identifier: str,
    session_id: Optional[str],
    rule_id: Optional[str],
    normalized_domain: str,
    qtype: int,
    action: str = "blocked"
) -> Dict[str, Any]:
    """Create privacy-minimized DNS violation telemetry item."""
    return {
        "event_id": str(uuid.uuid4()),
        "device_identifier": device_identifier,
        "session_id": session_id,
        "event_type": "dns_block",
        "payload": {
            "rule_id": rule_id,
            "domain": normalized_domain,
            "qtype": qtype,
            "action": action
        },
        "occurred_at": datetime.now(timezone.utc).isoformat()
    }

def create_dns_health_event(
    device_identifier: str,
    resolver_healthy: bool,
    upstream_healthy: bool,
    policy_version: int,
    cache_metrics: Dict[str, Any],
    drift_detected: bool = False
) -> Dict[str, Any]:
    """Create DNS health and metrics telemetry event."""
    return {
        "event_id": str(uuid.uuid4()),
        "device_identifier": device_identifier,
        "event_type": "dns_health",
        "payload": {
            "resolver_healthy": resolver_healthy,
            "upstream_healthy": upstream_healthy,
            "policy_version": policy_version,
            "cache_size": cache_metrics.get("size", 0),
            "cache_hits": cache_metrics.get("hits", 0),
            "cache_misses": cache_metrics.get("misses", 0),
            "cache_evictions": cache_metrics.get("evictions", 0),
            "drift_detected": drift_detected
        },
        "occurred_at": datetime.now(timezone.utc).isoformat()
    }

def create_dns_restoration_event(
    device_identifier: str,
    restoration_status: str,
    message: str
) -> Dict[str, Any]:
    """Create DNS configuration restoration audit telemetry event."""
    return {
        "event_id": str(uuid.uuid4()),
        "device_identifier": device_identifier,
        "event_type": "dns_restoration",
        "payload": {
            "status": restoration_status,
            "message": message
        },
        "occurred_at": datetime.now(timezone.utc).isoformat()
    }
