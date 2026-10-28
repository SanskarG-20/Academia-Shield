"""
Tests for DNS Configuration Lifecycle & Drift Detection.
"""

from agent.dns.configuration import DNSConfigurationLifecycle
from agent.platform.windows_dns import WindowsDNSAdapterManager

def test_unprivileged_safe_dns_configuration():
    lifecycle = DNSConfigurationLifecycle()
    
    # Non-admin enable enforcement (starts socket, skips live adapter alteration safely)
    success = lifecycle.enable_enforcement(admin_consent=False)
    assert success is True
    assert lifecycle.enforcement_enabled is True
    assert lifecycle.adapter_redirected is False

    health = lifecycle.check_drift_and_health()
    assert health["enforcement_enabled"] is True
    assert health["drift_detected"] is False

    # Cleanup
    lifecycle.disable_enforcement()
    assert lifecycle.enforcement_enabled is False

def test_windows_dns_adapter_backup_path():
    manager = WindowsDNSAdapterManager()
    assert manager.backup_dir is not None
    assert "academia_shield" in manager.backup_file
