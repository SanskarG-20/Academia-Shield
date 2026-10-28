"""
Comprehensive Test Suite for Academia Shield Windows Installer Executable & Release Pipeline.

Covers:
1. Installer package contains all required agent components
2. SHA-256 package hash & release manifest signature verification
3. Device enrollment with Ed25519 keypair and secure credential storage
4. Signed-policy validation (integrity hash, signature, temporal validity)
5. Session join gate (agent NEVER activates before valid student session join)
6. Safe DNS backup and guaranteed restoration
7. Protected process safety (safeguarding Explorer, system processes, security runtimes, Notepad testing)
8. Policy restoration on session termination / shutdown
9. Safe uninstall and registry cleanup
10. Absence of arbitrary command execution or remote shell pathways
"""

import sys
import os
import time
import json
import hashlib
import tempfile
import pytest
from unittest.mock import patch, MagicMock

AGENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AGENT_ROOT not in sys.path:
    sys.path.insert(0, AGENT_ROOT)

from agent.core.state_machine.machine import AgentStateMachine, AgentState
from agent.core.auth.crypto import Ed25519Signer
from agent.core.updater.manifest import UpdateManifestVerifier
from agent.core.updater.integrity import AgentIntegrityChecker
from agent.core.policy.engine import PolicyEngine
from agent.core.storage.database import LocalDatabase
from agent.monitoring.protected_processes import ProtectedProcessManager
from agent.platforms.windows.process_monitor import WindowsProcessMonitor
from agent.platforms.windows.dns import WindowsDnsEnforcement
from agent.platforms.windows.installer import WindowsInstaller, WindowsUninstaller
from agent.platforms.windows.compliance import WindowsUsbStorageCompliance
import importlib.util

installer_path = os.path.join(AGENT_ROOT, "installer.py")
spec = importlib.util.spec_from_file_location("installer", installer_path)
installer_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer_mod)

install_agent_files = installer_mod.install_agent_files
uninstall_agent = installer_mod.uninstall_agent
is_admin = installer_mod.is_admin

# ==============================================================================
# 1. Installer Package Content & Component Verification
# ==============================================================================

def test_installer_package_contains_required_components():
    """Verify that the agent codebase contains all 12 required agent modules."""
    required_components = [
        "agent/main.py",                         # Agent service daemon
        "agent/cli/main.py",                     # Agent command-line utility
        "agent/ui/status_app.py",                # Agent tray/status app
        "agent/platforms/windows/storage.py",    # Secure credential storage
        "agent/core/enrollment/enrollment_manager.py", # Device enrollment
        "agent/core/policy/engine.py",           # Signed-policy verifier
        "agent/core/api/client.py",              # Heartbeat client
        "agent/core/telemetry/queue.py",         # Offline telemetry queue
        "agent/monitoring/process_monitor.py",   # Application monitoring
        "agent/dns/resolver.py",                 # DNS blocking module
        "agent/platforms/windows/installer.py",  # Safe uninstall & restoration
        "agent/core/updater/manifest.py",        # Update checker with signed manifest
        "agent/core/updater/integrity.py"        # Tamper detection
    ]

    for rel_path in required_components:
        full_path = os.path.join(AGENT_ROOT, rel_path)
        assert os.path.isfile(full_path), f"Required component missing: {rel_path}"

# ==============================================================================
# 2. Signature and Hash Verification
# ==============================================================================

def test_sha256_package_hash_and_signature_verification():
    """Verify SHA-256 package hashing and Ed25519 digital signature validation."""
    priv_hex, pub_hex = Ed25519Signer.generate_keypair()
    verifier = UpdateManifestVerifier(public_key_hex=pub_hex)

    # Test file hashing
    dummy_bytes = b"ACADEMIA_SHIELD_BINARY_PAYLOAD_TEST_DATA"
    expected_hash = hashlib.sha256(dummy_bytes).hexdigest()
    assert verifier.verify_binary_hash(dummy_bytes, expected_hash) is True
    assert verifier.verify_binary_hash(dummy_bytes, "wrong_hash") is False

    # Test manifest signature verification
    manifest = {
        "version": "2.3.0",
        "platform": "windows",
        "download_url": "http://127.0.0.1:5000/installers/windows/AcademiaShieldInstaller.exe",
        "sha256": expected_hash
    }
    canonical_str = f"{manifest['version']}:{manifest['platform']}:{manifest['sha256']}:{manifest['download_url']}"
    sig = Ed25519Signer.sign_message(priv_hex, canonical_str.encode("utf-8"))
    manifest["signature"] = sig

    is_valid, msg = verifier.verify_manifest(manifest)
    assert is_valid is True
    assert msg == "Manifest verified"

    # Tampered manifest detection
    tampered_manifest = dict(manifest)
    tampered_manifest["sha256"] = "tampered_hash_12345"
    is_valid_tampered, _ = verifier.verify_manifest(tampered_manifest)
    assert is_valid_tampered is False

# ==============================================================================
# 3. Device Enrollment & Keypair Generation
# ==============================================================================

def test_device_enrollment_keypair_generation():
    """Verify that local Ed25519 device keypair is generated and public key is extracted."""
    priv_hex, pub_hex = Ed25519Signer.generate_keypair()
    assert len(priv_hex) == 64
    assert len(pub_hex) == 64
    assert priv_hex != pub_hex

    # Verify signature produced with private key verifies against public key
    msg = b"Device Registration Nonce: 123456789"
    sig = Ed25519Signer.sign_message(priv_hex, msg)
    assert Ed25519Signer.verify_signature(pub_hex, sig, msg) is True

# ==============================================================================
# 4. Policy Signature and Integrity Validation
# ==============================================================================

def test_policy_signature_validation():
    """Verify policy signature checking with PolicyEngine."""
    db = LocalDatabase(":memory:")
    server_priv, server_pub = Ed25519Signer.generate_keypair()
    engine = PolicyEngine(db, server_public_key=server_pub)

    policy_data = {
        "session_id": "sess_100",
        "policy_version": 2,
        "policy_active": True,
        "domain_rules": [{"id": "r1", "domain_pattern": "gaming.com", "action": "block"}],
        "application_rules": [{"id": "r2", "executable_name": "notepad.exe", "action": "close"}]
    }

    # Calculate canonical integrity hash
    integ_hash = engine.calculate_integrity_hash(policy_data)
    policy_data["integrity_hash"] = integ_hash
    
    # Sign with server private key
    sig = Ed25519Signer.sign_message(server_priv, integ_hash.encode("utf-8"))
    policy_data["signature"] = sig

    assert engine.verify_policy_signature(policy_data) is True

    # Test invalid signature rejection
    policy_data["signature"] = "0" * 128
    assert engine.verify_policy_signature(policy_data) is False

# ==============================================================================
# 5. Session Join Gate (No Enforcement Before Student Join)
# ==============================================================================

def test_no_activation_before_valid_student_session_join():
    """Verify state machine strictly forbids ENFORCING state before student manually joins."""
    sm = AgentStateMachine(initial_state=AgentState.ENROLLED_IDLE)
    assert sm.current_state == AgentState.ENROLLED_IDLE

    # Attempt direct transition to ENFORCING without joining
    transition_success = sm.transition_to(AgentState.ENFORCING)
    assert transition_success is False
    assert sm.current_state != AgentState.ENFORCING

    # Transition to WAITING_FOR_STUDENT_JOIN
    sm.transition_to(AgentState.WAITING_FOR_STUDENT_JOIN)
    assert sm.current_state == AgentState.WAITING_FOR_STUDENT_JOIN

    # Student manually joins active session
    join_success = sm.student_join("session_math_101")
    assert join_success is True
    assert sm.current_state == AgentState.POLICY_RECEIVED
    assert sm.context["student_joined"] is True

    # Now transition to ENFORCING is valid
    enforce_success = sm.transition_to(AgentState.ENFORCING)
    assert enforce_success is True
    assert sm.current_state == AgentState.ENFORCING

# ==============================================================================
# 6. DNS Backup and Restoration Safety
# ==============================================================================

def test_dns_backup_and_restoration():
    """Verify DNS settings are backed up and cleanly restored without touching hosts or firewall."""
    dns_adapter = WindowsDnsEnforcement()
    
    # Simulate active enforcement and mock backup
    dns_adapter._original_dns_backup = {
        "Wi-Fi": {"dhcp": True, "servers": ["192.168.1.1"]}
    }
    dns_adapter._is_enforced = True

    # Restore settings
    res = dns_adapter.restore_original_dns()
    assert dns_adapter._is_enforced is False
    assert len(dns_adapter._original_dns_backup) == 0
    assert "restored" in res.message.lower()

# ==============================================================================
# 7. Protected Process Safety
# ==============================================================================

def test_protected_process_safety():
    """Verify that critical system, accessibility, and security processes can NEVER be terminated."""
    mgr = ProtectedProcessManager()
    
    critical_processes = [
        "explorer.exe", "svchost.exe", "lsass.exe", "csrss.exe", "services.exe",
        "magnify.exe", "narrator.exe", "osk.exe", "msmpeng.exe", "python.exe"
    ]
    for proc in critical_processes:
        assert mgr.is_protected(proc) is True, f"Critical process '{proc}' must be protected"

    # User test app (Notepad) is not protected and can be managed
    assert mgr.is_protected("notepad.exe") is False
    assert mgr.is_protected("game.exe") is False

def test_windows_process_monitor_protects_critical_apps():
    """Verify WindowsProcessMonitor downgrades action to log for protected apps."""
    monitor = WindowsProcessMonitor()
    res = monitor.handle_process_action(pid=1000, process_name="explorer.exe", action="close")
    assert res.details.get("protected") is True
    assert res.details.get("action_taken") == "logged"

# ==============================================================================
# 8. Policy Restoration After Session End
# ==============================================================================

def test_policy_restoration_after_session_end():
    """Verify state machine triggers restoration callback on session end or student leave."""
    restored_called = False
    def on_restore_hook():
        nonlocal restored_called
        restored_called = True

    sm = AgentStateMachine(initial_state=AgentState.ENFORCING, on_restore=on_restore_hook)
    
    # Student leaves session
    sm.student_leave()
    assert sm.current_state == AgentState.RESTORING
    assert restored_called is True

# ==============================================================================
# 9. Safe Uninstall & Cleanup
# ==============================================================================

def test_safe_uninstall_cleanup():
    """Verify uninstaller purges files and restores settings safely."""
    with tempfile.TemporaryDirectory() as tmp_install_dir:
        # Create dummy agent files
        dummy_file = os.path.join(tmp_install_dir, "agent.py")
        with open(dummy_file, "w") as f:
            f.write("# dummy agent")

        assert os.path.isfile(dummy_file)
        
        # Run uninstallation on temp dir
        uninstalled = uninstall_agent(tmp_install_dir)
        assert uninstalled is True
        assert not os.path.exists(tmp_install_dir)

# ==============================================================================
# 10. Absence of Arbitrary Command Pathways
# ==============================================================================

def test_no_arbitrary_command_execution_path():
    """Verify agent has no remote shell or arbitrary command execution APIs."""
    from agent.cli import main as cli_func
    from agent import main as agent_mod

    cli_file = cli_func.__code__.co_filename
    with open(cli_file, "r", encoding="utf-8") as f:
        cli_content = f.read()
        assert "remote_shell" not in cli_content
        assert "eval(" not in cli_content

    agent_file = agent_mod.__file__
    with open(agent_file, "r", encoding="utf-8") as f:
        main_content = f.read()
        assert "remote_shell" not in main_content
        assert "eval(" not in main_content
