"""
Tests for Cross-Platform Windows & macOS Abstractions and Compliance Adapters.
"""

import pytest
from agent.platforms import get_platform_bundle, PlatformCapabilityStatus
from agent.platforms.windows import (
    WindowsSecureStorage,
    WindowsProcessMonitor,
    WindowsDnsEnforcement,
    WindowsBrowserCompliance,
    WindowsApplicationControlCompliance,
    WindowsUsbStorageCompliance
)
from agent.platforms.macos import (
    MacosSecureStorage,
    MacosProcessMonitor,
    MacosDnsEnforcement,
    MacosBrowserCompliance,
    MacosApplicationControlCompliance,
    MacosUsbStorageCompliance
)

def test_platform_bundle_instantiation():
    win_bundle = get_platform_bundle(force_platform="win32")
    assert win_bundle.platform_name == "windows"
    assert win_bundle.storage is not None
    assert win_bundle.dns is not None

    mac_bundle = get_platform_bundle(force_platform="darwin")
    assert mac_bundle.platform_name == "macos"
    assert mac_bundle.storage is not None
    assert mac_bundle.process_monitor is not None

def test_windows_storage_secret_lifecycle():
    storage = WindowsSecureStorage(service_name="TestAcademiaShieldWin")
    res = storage.store_secret("test_key", "secret_value_123")
    assert res.status in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.UNAVAILABLE, PlatformCapabilityStatus.REQUIRES_USER_APPROVAL)
    
    val = storage.retrieve_secret("test_key")
    assert val == "secret_value_123"
    
    del_res = storage.delete_secret("test_key")
    assert del_res.status == PlatformCapabilityStatus.ACTIVE
    assert storage.retrieve_secret("test_key") is None

def test_macos_storage_secret_lifecycle():
    storage = MacosSecureStorage(service_name="test.academiashield.mac")
    res = storage.store_secret("mac_key", "mac_secret_456")
    assert res.status in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.UNAVAILABLE, PlatformCapabilityStatus.REQUIRES_USER_APPROVAL)
    
    val = storage.retrieve_secret("mac_key")
    assert val == "mac_secret_456"
    
    storage.delete_secret("mac_key")
    assert storage.retrieve_secret("mac_key") is None

def test_windows_process_monitor_protected_safety():
    monitor = WindowsProcessMonitor()
    # Attempt to close a protected process (e.g., explorer.exe or svchost.exe)
    res = monitor.handle_process_action(pid=100, process_name="explorer.exe", action="close")
    assert res.details.get("protected") is True
    assert res.details.get("action_taken") == "logged"

def test_macos_process_monitor_audit_mode_only():
    monitor = MacosProcessMonitor()
    # On macOS, close action should safely downgrade to audit/warn
    res = monitor.handle_process_action(pid=200, process_name="spotify", action="close")
    assert res.status == PlatformCapabilityStatus.REQUIRES_MDM
    assert res.details.get("action_taken") == "warned"

def test_macos_protected_process_safety():
    monitor = MacosProcessMonitor()
    res = monitor.handle_process_action(pid=1, process_name="windowserver", action="close")
    assert res.details.get("protected") is True

def test_windows_compliance_reporting():
    browser = WindowsBrowserCompliance()
    app_ctrl = WindowsApplicationControlCompliance()
    usb = WindowsUsbStorageCompliance()

    b_res = browser.check_compliance()
    assert b_res.status in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.REQUIRES_MDM, PlatformCapabilityStatus.SUPPORTED)

    a_res = app_ctrl.check_compliance()
    assert a_res.status in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.REQUIRES_MDM, PlatformCapabilityStatus.SUPPORTED)

    u_res = usb.check_compliance()
    assert u_res.status in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.SUPPORTED)

def test_macos_compliance_reporting():
    browser = MacosBrowserCompliance()
    app_ctrl = MacosApplicationControlCompliance()
    usb = MacosUsbStorageCompliance()

    assert browser.check_compliance().status in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.REQUIRES_MDM, PlatformCapabilityStatus.SUPPORTED)
    assert app_ctrl.check_compliance().status in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.REQUIRES_MDM, PlatformCapabilityStatus.REQUIRES_USER_APPROVAL, PlatformCapabilityStatus.SUPPORTED)
    assert usb.check_compliance().status in (PlatformCapabilityStatus.ACTIVE, PlatformCapabilityStatus.SUPPORTED)
