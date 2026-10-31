"""
Safety tests for the legacy standalone agent's DNS enforcement engine.

Focus: durable journal, verified restore, adapter filtering and orphan repair.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

from enforcement import dns  # noqa: E402


def _write_journal(tmp_path, adapters):
    path = tmp_path / "dns_backup.json"
    path.write_text(
        json.dumps({
            "version": 2,
            "status": "enforced",
            "resolver_port": 53,
            "adapters": adapters,
        }),
        encoding="utf-8",
    )
    return str(path)


def _entry(servers, was_dhcp=False):
    return {
        "alias": "Wi-Fi",
        "original_servers": servers,
        "was_dhcp": was_dhcp,
        "changed": True,
        "restored": False,
    }


def test_default_route_query_skips_virtual_interfaces():
    result = MagicMock(
        returncode=0,
        stdout=json.dumps([
            {
                "InterfaceAlias": "Ethernet 2",
                "InterfaceDescription": "VirtualBox Host-Only Ethernet Adapter",
            },
            {
                "InterfaceAlias": "Wi-Fi",
                "InterfaceDescription": "Intel(R) Wi-Fi 6",
            },
        ]),
    )
    with patch.object(dns, "_run_powershell", return_value=result):
        assert dns._get_windows_dns_interfaces() == ["Wi-Fi"]


def test_restore_applies_and_verifies_journal(tmp_path):
    journal_path = _write_journal(tmp_path, {"Wi-Fi": _entry(["8.8.8.8"])})
    with patch.object(dns, "DNS_BACKUP_FILE", journal_path), \
         patch.object(dns, "_is_admin", return_value=True), \
         patch.object(dns, "_apply_interface_servers", return_value=True) as apply, \
         patch.object(dns, "_interface_state", return_value={
             "ok": True, "dhcp": False, "servers": ["8.8.8.8"],
         }), \
         patch.object(dns, "_flush_dns"):
        assert dns._restore_dns_from_journal() is True

    apply.assert_called_once_with("Wi-Fi", ["8.8.8.8"])
    assert not os.path.exists(journal_path)


def test_dhcp_original_state_resets_to_dhcp(tmp_path):
    journal_path = _write_journal(tmp_path, {"Wi-Fi": _entry([], was_dhcp=True)})
    with patch.object(dns, "DNS_BACKUP_FILE", journal_path), \
         patch.object(dns, "_is_admin", return_value=True), \
         patch.object(dns, "_apply_interface_servers", return_value=True) as apply, \
         patch.object(dns, "_interface_state", return_value={
             "ok": True, "dhcp": True, "servers": [],
         }), \
         patch.object(dns, "_flush_dns"):
        assert dns._restore_dns_from_journal() is True

    apply.assert_called_once_with("Wi-Fi", None)


def test_failed_restore_keeps_journal(tmp_path):
    journal_path = _write_journal(tmp_path, {"Wi-Fi": _entry(["8.8.8.8"])})
    with patch.object(dns, "DNS_BACKUP_FILE", journal_path), \
         patch.object(dns, "_is_admin", return_value=True), \
         patch.object(dns, "_apply_interface_servers", return_value=False), \
         patch.object(dns, "_flush_dns"):
        assert dns._restore_dns_from_journal() is False

    assert os.path.exists(journal_path)
    with open(journal_path, "r", encoding="utf-8") as handle:
        journal = json.load(handle)
    assert journal["status"] == "restore_pending"


def test_cleanup_repairs_orphaned_loopback_interface(tmp_path):
    missing = str(tmp_path / "no_journal.json")
    with patch.object(dns, "DNS_BACKUP_FILE", missing), \
         patch.object(dns, "_probe_resolver", return_value=False), \
         patch.object(dns, "_all_interfaces", return_value=[
             {"alias": "Wi-Fi", "description": "", "status": "Up"},
         ]), \
         patch.object(dns, "_interface_state", side_effect=[
             {"ok": True, "dhcp": False, "servers": ["127.0.0.1"]},
             {"ok": True, "dhcp": True, "servers": []},
         ]), \
         patch.object(dns, "_apply_interface_servers", return_value=True) as apply, \
         patch.object(dns, "_is_admin", return_value=True), \
         patch.object(dns, "_flush_dns"):
        assert dns.cleanup_stale_dns() is True

    apply.assert_called_once_with("Wi-Fi", None)
