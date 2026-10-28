"""
Academia Shield Agent - Settings & Configuration Validation Module.
"""

import os
import re
import socket
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

SENSITIVE_KEYS_PATTERNS = [
    re.compile(r"pass(word)?", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"key", re.IGNORECASE),
    re.compile(r"auth", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]

def redact_sensitive_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of a dictionary with sensitive keys redacted."""
    redacted = {}
    for k, v in data.items():
        if any(pattern.search(str(k)) for pattern in SENSITIVE_KEYS_PATTERNS):
            redacted[k] = "[REDACTED]"
        elif isinstance(v, dict):
            redacted[k] = redact_sensitive_dict(v)
        else:
            redacted[k] = v
    return redacted

def redact_text(text: str) -> str:
    """Redact bearer tokens or potential raw tokens from log strings."""
    if not text:
        return ""
    # Redact Bearer tokens
    text = re.sub(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", "Bearer [REDACTED]", text, flags=re.IGNORECASE)
    return text

@dataclass
class AgentConfig:
    # Keep the out-of-the-box agent configuration aligned with the bundled
    # FastAPI backend, which listens on port 8000 by default.
    api_url: str = field(default_factory=lambda: os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/"))
    poll_interval: int = field(default_factory=lambda: max(3, min(int(os.getenv("POLL_INTERVAL", "8")), 60)))
    request_timeout: int = field(default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT", "10")))
    retry_attempts: int = field(default_factory=lambda: int(os.getenv("RETRY_ATTEMPTS", "3")))
    retry_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("RETRY_BACKOFF_SECONDS", "2.0")))
    
    # Device identity
    device_id: str = field(default_factory=lambda: os.getenv("AGENT_DEVICE_ID", socket.gethostname()))
    agent_version: str = "2.3.0"
    
    # Agent Operating Mode: DEVELOPMENT_ENFORCEMENT (active blocking on active sessions), AUDIT, MANAGED_ENFORCEMENT
    mode: str = "DEVELOPMENT_ENFORCEMENT"
    
    # DNS settings
    dns_listen_port: int = field(default_factory=lambda: int(os.getenv("DNS_LISTEN_PORT", "5353")))
    dns_listen_host: str = field(default_factory=lambda: os.getenv("DNS_LISTEN_HOST", "127.0.0.1"))
    dns_upstream: str = field(default_factory=lambda: os.getenv("DNS_UPSTREAM", "8.8.8.8"))
    dns_upstream_port: int = field(default_factory=lambda: int(os.getenv("DNS_UPSTREAM_PORT", "53")))
    dns_ttl: int = field(default_factory=lambda: int(os.getenv("DNS_TTL", "300")))
    
    # Process Monitoring
    process_scan_interval: float = field(default_factory=lambda: float(os.getenv("PROCESS_SCAN_INTERVAL", "3.0")))
    
    # Data Storage
    storage_dir: str = field(default_factory=lambda: os.path.expanduser(os.getenv("AGENT_DATA_DIR", "~/.academia_shield")))
    
    # OS Services safeguards (Never terminate these)
    protected_processes: List[str] = field(default_factory=lambda: [
        "system", "system idle process", "explorer.exe", "lsass.exe", "csrss.exe",
        "services.exe", "winlogon.exe", "smss.exe", "svchost.exe", "taskmgr.exe",
        "msmpeng.exe", "securityhealthservice.exe", "narrator.exe", "osk.exe", "magnify.exe",
        "acad_agent.exe", "academiashield.exe", "agent.exe",
        "sshd", "init", "systemd", "launchd", "python", "python.exe", "pytest"
    ])

    def validate(self) -> None:
        """Validate configuration limits and format."""
        if not self.api_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid API URL: {self.api_url}. Must start with http:// or https://")
        if self.poll_interval < 1:
            raise ValueError("Poll interval must be at least 1 second.")
        if self.dns_listen_port < 1 or self.dns_listen_port > 65535:
            raise ValueError("DNS listen port must be between 1 and 65535.")
        if self.mode not in ("AUDIT", "DEVELOPMENT_ENFORCEMENT", "MANAGED_ENFORCEMENT"):
            raise ValueError(f"Invalid mode: {self.mode}. Must be AUDIT, DEVELOPMENT_ENFORCEMENT, or MANAGED_ENFORCEMENT.")

_config_instance: Optional[AgentConfig] = None

def get_agent_mode(storage_dir: Optional[str] = None) -> str:
    """Retrieve persistently stored agent mode."""
    target_dir = storage_dir or os.path.expanduser(os.getenv("AGENT_DATA_DIR", "~/.academia_shield"))
    mode_file = os.path.join(target_dir, "mode.json")
    if os.path.exists(mode_file):
        try:
            import json
            with open(mode_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                mode = data.get("mode", "AUDIT")
                if mode in ("AUDIT", "DEVELOPMENT_ENFORCEMENT", "MANAGED_ENFORCEMENT"):
                    return mode
        except Exception:
            pass
    return os.getenv("AGENT_MODE", "DEVELOPMENT_ENFORCEMENT")

def set_agent_mode(mode: str, storage_dir: Optional[str] = None) -> None:
    """Persistently store agent operating mode."""
    if mode not in ("AUDIT", "DEVELOPMENT_ENFORCEMENT", "MANAGED_ENFORCEMENT"):
        raise ValueError(f"Invalid mode: {mode}")
    target_dir = storage_dir or os.path.expanduser(os.getenv("AGENT_DATA_DIR", "~/.academia_shield"))
    os.makedirs(target_dir, exist_ok=True)
    mode_file = os.path.join(target_dir, "mode.json")
    import json
    with open(mode_file, "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f, indent=2)
    
    cfg = get_config()
    cfg.mode = mode

def get_config() -> AgentConfig:
    global _config_instance
    if _config_instance is None:
        _config_instance = AgentConfig()
        _config_instance.mode = get_agent_mode(_config_instance.storage_dir)
        _config_instance.validate()
    return _config_instance
