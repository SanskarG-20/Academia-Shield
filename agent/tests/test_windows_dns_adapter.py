from unittest.mock import MagicMock, patch

from agent.platform.windows_dns import WindowsDNSAdapterManager


def test_active_adapter_discovery_uses_valid_powershell_cmdlets():
    manager = WindowsDNSAdapterManager()
    ps_result = MagicMock(
        returncode=0,
        stdout='[{"InterfaceAlias":"Wi-Fi","InterfaceIndex":12,"Name":"Wi-Fi"}]',
    )

    with patch("subprocess.run", return_value=ps_result) as run:
        adapters = manager.get_active_adapters()

    assert adapters == [{"alias": "Wi-Fi", "index": 12}]
    command = run.call_args.args[0][-1]
    assert "Where-Object Status -eq 'Up'" in command
    assert "Select-Object" in command


def test_dns_redirect_does_not_claim_success_when_both_commands_fail(tmp_path):
    manager = WindowsDNSAdapterManager(backup_dir=str(tmp_path))
    manager.is_admin = MagicMock(return_value=True)
    manager.backup_original_dns = MagicMock(return_value=True)
    manager.get_active_adapters = MagicMock(return_value=[{"alias": "Wi-Fi", "index": 12}])

    failed = MagicMock(returncode=1, stdout="", stderr="access denied")
    with patch("subprocess.run", return_value=failed):
        assert manager.configure_local_dns() is False
