import json
import os
from unittest.mock import MagicMock, PropertyMock, patch

from agent.platform.windows_dns import WindowsDNSAdapterManager


def test_active_adapter_discovery_filters_up_adapters():
    manager = WindowsDNSAdapterManager()
    ps_result = MagicMock(
        returncode=0,
        stdout=json.dumps([
            {
                "InterfaceAlias": "Wi-Fi",
                "InterfaceIndex": 12,
                "Name": "Wi-Fi",
                "InterfaceDescription": "Intel(R) Wi-Fi 6",
                "Status": "Up",
            },
            {
                "InterfaceAlias": "Ethernet 2",
                "InterfaceIndex": 7,
                "Name": "Ethernet 2",
                "InterfaceDescription": "VirtualBox Host-Only Ethernet Adapter",
                "Status": "Disconnected",
            },
        ]),
    )

    with patch("subprocess.run", return_value=ps_result) as run:
        adapters = manager.get_active_adapters()

    assert adapters == [{"alias": "Wi-Fi", "index": 12}]
    command = run.call_args.args[0][-1]
    assert "Get-NetAdapter" in command
    assert "Select-Object" in command


def test_enforcement_adapters_skip_virtual_default_routes():
    manager = WindowsDNSAdapterManager()
    manager._query_default_route_adapters = MagicMock(return_value=[
        {
            "InterfaceAlias": "Ethernet 2",
            "InterfaceIndex": 7,
            "InterfaceDescription": "VirtualBox Host-Only Ethernet Adapter",
        },
        {
            "InterfaceAlias": "Wi-Fi",
            "InterfaceIndex": 12,
            "InterfaceDescription": "Intel(R) Wi-Fi 6",
        },
    ])

    assert manager.get_enforcement_adapters() == [{"alias": "Wi-Fi", "index": 12}]


def test_redirect_refused_when_resolver_is_not_on_port_53(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)
    manager.get_enforcement_adapters = MagicMock(return_value=[{"alias": "Wi-Fi", "index": 12}])

    assert manager.configure_local_dns(target_dns="127.0.0.1", resolver_port=5353) is False
    assert not os.path.exists(manager.backup_file)


def test_redirect_refused_when_resolver_does_not_answer(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)
    manager.get_enforcement_adapters = MagicMock(return_value=[{"alias": "Wi-Fi", "index": 12}])

    with patch("agent.platform.windows_dns.probe_local_resolver", return_value=False):
        assert manager.configure_local_dns(target_dns="127.0.0.1", resolver_port=53) is False
    assert not os.path.exists(manager.backup_file)


def test_dns_redirect_does_not_claim_success_when_apply_fails(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)
    manager.get_enforcement_adapters = MagicMock(return_value=[{"alias": "Wi-Fi", "index": 12}])
    manager._query_adapter_dns_state = MagicMock(
        return_value={"ok": True, "dhcp": True, "servers": []}
    )
    manager._apply_adapter_servers = MagicMock(return_value=False)
    manager.ensure_recovery_task = MagicMock(return_value=True)

    with patch("agent.platform.windows_dns.probe_local_resolver", return_value=True):
        assert manager.configure_local_dns() is False

    assert not os.path.exists(manager.backup_file)


def test_journal_survives_restart_and_restore_is_verified(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)
    manager.get_enforcement_adapters = MagicMock(return_value=[{"alias": "Wi-Fi", "index": 12}])
    manager._apply_adapter_servers = MagicMock(return_value=True)
    manager.ensure_recovery_task = MagicMock(return_value=True)
    original = {"ok": True, "dhcp": False, "servers": ["8.8.8.8", "1.1.1.1"]}
    enforced = {"ok": True, "dhcp": False, "servers": ["127.0.0.1"]}
    manager._query_adapter_dns_state = MagicMock(side_effect=[original, original, enforced, enforced])

    with patch("agent.platform.windows_dns.probe_local_resolver", return_value=True):
        assert manager.configure_local_dns(target_dns="127.0.0.1", resolver_port=53) is True

    with open(manager.backup_file, "r", encoding="utf-8") as handle:
        journal = json.load(handle)
    assert journal["version"] == 2
    assert journal["status"] == "enforced"
    assert journal["adapters"]["Wi-Fi"]["original_servers"] == ["8.8.8.8", "1.1.1.1"]

    # A brand-new instance simulates a crash and reboot: it must find the journal.
    restarted = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    restarted.is_admin = MagicMock(return_value=True)
    restarted.get_all_adapters = MagicMock(
        return_value=[{"alias": "Wi-Fi", "index": 12, "status": "Up"}]
    )
    restarted._apply_adapter_servers = MagicMock(return_value=True)
    restarted._query_adapter_dns_state = MagicMock(return_value=original)
    restarted._flush_dns = MagicMock()
    restarted.remove_recovery_task = MagicMock(return_value=True)

    with patch("agent.platform.windows_dns.probe_local_resolver", return_value=False):
        result = restarted.recover_orphaned_state()

    assert result["status"] == "restored"
    assert not os.path.exists(restarted.backup_file)
    restarted._apply_adapter_servers.assert_called_once()
    assert restarted._apply_adapter_servers.call_args.args[1] == ["8.8.8.8", "1.1.1.1"]


def test_failed_restore_keeps_journal_and_guard(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)
    manager.get_all_adapters = MagicMock(
        return_value=[{"alias": "Wi-Fi", "index": 12, "status": "Up"}]
    )
    manager._apply_adapter_servers = MagicMock(return_value=False)
    manager._flush_dns = MagicMock()
    manager.remove_recovery_task = MagicMock(return_value=True)
    manager._write_journal({
        "version": 2,
        "status": "enforced",
        "resolver_port": 53,
        "adapters": {
            "Wi-Fi": {
                "alias": "Wi-Fi",
                "index": 12,
                "original_servers": ["8.8.8.8"],
                "was_dhcp": False,
                "changed": True,
                "restored": False,
            }
        },
    })

    assert manager.restore_original_dns() is False
    assert os.path.exists(manager.backup_file)
    with open(manager.backup_file, "r", encoding="utf-8") as handle:
        journal = json.load(handle)
    assert journal["status"] == "restore_pending"
    manager.remove_recovery_task.assert_not_called()


def test_orphaned_loopback_adapter_is_repaired_without_journal(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)
    manager.get_all_adapters = MagicMock(
        return_value=[{"alias": "Wi-Fi", "index": 12, "status": "Up"}]
    )
    manager._query_adapter_dns_state = MagicMock(side_effect=[
        {"ok": True, "dhcp": False, "servers": ["127.0.0.1"]},
        {"ok": True, "dhcp": True, "servers": []},
    ])
    manager._apply_adapter_servers = MagicMock(return_value=True)
    manager._flush_dns = MagicMock()
    manager.remove_recovery_task = MagicMock(return_value=True)

    with patch("agent.platform.windows_dns.probe_local_resolver", return_value=False):
        assert manager.restore_original_dns() is True

    assert manager._apply_adapter_servers.call_args.args[1] is None
    assert not os.path.exists(manager.backup_file)


def test_orphan_repair_preserves_real_upstream_servers(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)
    manager.get_all_adapters = MagicMock(
        return_value=[{"alias": "Wi-Fi", "index": 12, "status": "Up"}]
    )
    manager._query_adapter_dns_state = MagicMock(side_effect=[
        {"ok": True, "dhcp": False, "servers": ["127.0.0.1", "1.1.1.1"]},
        {"ok": True, "dhcp": False, "servers": ["1.1.1.1"]},
    ])
    manager._apply_adapter_servers = MagicMock(return_value=True)
    manager._flush_dns = MagicMock()
    manager.remove_recovery_task = MagicMock(return_value=True)

    with patch("agent.platform.windows_dns.probe_local_resolver", return_value=False):
        assert manager.restore_original_dns() is True

    assert manager._apply_adapter_servers.call_args.args[1] == ["1.1.1.1"]


def test_legacy_v1_backup_is_migrated(tmp_path):
    legacy = tmp_path / "legacy_backup.json"
    legacy.write_text('{"Wi-Fi": ["8.8.8.8", "1.1.1.1"]}', encoding="utf-8")

    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path / "state"))
    manager._legacy_backup_paths = MagicMock(return_value=[str(legacy)])

    journal = manager._migrate_legacy_journal()

    assert journal["adapters"]["Wi-Fi"]["original_servers"] == ["8.8.8.8", "1.1.1.1"]
    assert os.path.exists(manager.backup_file)
    assert not legacy.exists()


def test_recovery_guard_task_install_and_remove(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)

    success = MagicMock(returncode=0, stdout="", stderr="")
    with patch.object(
        WindowsDNSAdapterManager, "_is_windows", new_callable=PropertyMock, return_value=True
    ):
        with patch("subprocess.run", return_value=success):
            assert manager.ensure_recovery_task() is True
        assert os.path.exists(manager.guard_script_file)
        with patch("subprocess.run", return_value=success):
            assert manager.remove_recovery_task() is True
