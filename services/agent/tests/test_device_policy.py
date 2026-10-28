"""Safe policy tests: temporary files and fake OS adapters only."""

import json
from logging.handlers import RotatingFileHandler
import os
import runpy
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comms import http_client
from enforcement import hosts, dns
import enforcement
from enforcement.apps import enforce_blocked_apps
import agent
import env_loader


class FakeProcess:
    def __init__(self, name, pid, owner="student", exe=None):
        self.info = {"name": name, "pid": pid, "username": owner,
                     "exe": exe or rf"C:\Program Files\Test\{name}"}
        self.terminated = False

    def terminate(self):
        self.terminated = True


class DevicePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = os.path.join(self.temp.name, "policy.json")
        self.credential = patch.object(http_client, "load_credential", return_value="device.secret")
        self.identifier = patch.object(http_client, "device_id", return_value="device")
        self.cache_patch = patch.object(http_client, "CACHE_FILE", self.cache)
        for item in (self.credential, self.identifier, self.cache_patch):
            item.start()
            self.addCleanup(item.stop)

    def policy(self, expiry):
        return {"active": True, "deviceId": "device", "issuedAt": datetime.now(timezone.utc).isoformat(),
                "expiresAt": expiry.isoformat(), "blockedDomains": ["example.com"], "blockedApps": ["notepad.exe"],
                "active_sessions": [{"id": "s", "ends_at": expiry.isoformat()}]}

    def test_cached_policy_expires(self):
        config = self.policy(datetime.now(timezone.utc) + timedelta(minutes=1))
        http_client.save_cached_config(config)
        self.assertTrue(http_client.load_cached_config()["active"])
        config = self.policy(datetime.now(timezone.utc) - timedelta(seconds=1))
        with open(self.cache, "w", encoding="utf-8") as file:
            json.dump({"policy": config, "mac": "invalid"}, file)
        self.assertIsNone(http_client.load_cached_config())
        self.assertIsNone(http_client._check_and_expire_cached_config(config))

    def test_cross_device_cache_rejected(self):
        config = self.policy(datetime.now(timezone.utc) + timedelta(minutes=1))
        config["deviceId"] = "other-device"
        self.assertIsNone(http_client._check_and_expire_cached_config(config))

    def test_invalid_remote_policy_does_not_fall_back_to_cache(self):
        config = self.policy(datetime.now(timezone.utc) + timedelta(minutes=1))
        http_client.save_cached_config(config)
        with patch.object(http_client, "fetch_remote_config_once", side_effect=http_client.InvalidPolicyError("expired")), \
             patch.object(http_client, "load_cached_config") as cached:
            self.assertIsNone(http_client.fetch_config_with_retry())
            cached.assert_not_called()
        self.assertFalse(os.path.exists(self.cache))

    def test_malformed_cache_cannot_break_recovery(self):
        with open(self.cache, "w", encoding="utf-8") as file:
            json.dump({"policy": {"active": True, "deviceId": "device", "expiresAt": 1}, "mac": 12}, file)
        self.assertIsNone(http_client.load_cached_config())
        with patch.object(agent, "STOP_FILE", os.path.join(self.temp.name, "stop")), \
             patch.object(agent, "DNS_BACKUP_FILE", os.path.join(self.temp.name, "dns-backup")), \
             patch.object(agent, "load_credential", return_value="device.secret"), \
             patch.object(agent, "restore_previous_system_state", return_value=True) as restore:
            self.assertTrue(agent.recover_expired_policy())
            restore.assert_called_once()

    def test_production_agent_rejects_plain_http_policy_server(self):
        config_path = str(Path(__file__).resolve().parents[1] / "config.py")
        with patch.dict(os.environ, {"API_URL": "http://example.com", "TEST_MODE": "false"}):
            with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                runpy.run_path(config_path)

    def test_packaged_agent_rejects_http_even_with_test_mode(self):
        config_path = str(Path(__file__).resolve().parents[1] / "config.py")
        with patch.object(sys, "frozen", True, create=True), \
             patch.dict(os.environ, {"API_URL": "http://example.com", "TEST_MODE": "true",
                                  "ProgramData": self.temp.name}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                runpy.run_path(config_path)

    def test_packaged_agent_rejects_external_socket_origin(self):
        config_path = str(Path(__file__).resolve().parents[1] / "config.py")
        with patch.object(sys, "frozen", True, create=True), \
             patch.dict(os.environ, {"API_URL": "https://api.example.com", "SOCKET_URL": "https://other.example.com",
                                  "ProgramData": self.temp.name}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Socket.IO URL"):
                runpy.run_path(config_path)

    def test_frozen_agent_ignores_config_next_to_downloaded_executable(self):
        download_dir = os.path.join(self.temp.name, "Downloads")
        os.makedirs(download_dir)
        with patch.object(env_loader.sys, "frozen", True, create=True), \
             patch.object(env_loader.sys, "platform", "win32"), \
             patch.object(env_loader.sys, "executable", os.path.join(download_dir, "AcademiaShield.exe")), \
             patch.dict(os.environ, {"ProgramData": self.temp.name}):
            candidates = env_loader._candidate_dirs()
        self.assertNotIn(download_dir, candidates)
        self.assertIn(os.path.join(self.temp.name, "AcademiaShield"), candidates)

    def test_agent_file_logs_are_bounded(self):
        handlers = [handler for handler in agent.LOGGER.handlers if isinstance(handler, RotatingFileHandler)]
        self.assertTrue(handlers)
        self.assertEqual(handlers[0].maxBytes, 2_000_000)
        self.assertEqual(handlers[0].backupCount, 3)

    def test_oversized_rule_lists_are_rejected_before_enforcement(self):
        with self.assertRaisesRegex(RuntimeError, "safe size"):
            http_client.normalize_config({"active": True, "blockedDomains": ["example.com"] * 201,
                                          "blockedApps": [], "active_sessions": []})
        oversized = self.policy(datetime.now(timezone.utc) + timedelta(minutes=1))
        oversized["blockedApps"] = ["app.exe"] * 51
        self.assertIsNone(http_client._check_and_expire_cached_config(oversized))

    def test_app_enforcement_exact_name_and_protected_processes(self):
        allowed = FakeProcess("editor.exe", 101)
        blocked = FakeProcess("notepad.exe", 102)
        protected = FakeProcess("explorer.exe", 103)
        system = FakeProcess("notepad.exe", 104, "SYSTEM")
        os_binary = FakeProcess("notepad.exe", 105, exe=r"C:\Windows\System32\notepad.exe")
        requested = []
        result = enforce_blocked_apps(
            ["notepad.exe", "explorer.exe"],
            lambda: [allowed, blocked, protected, system, os_binary],
            current_username="student", windows_dir=r"C:\Windows",
            request_close=lambda pid: requested.append(pid) or True,
        )
        self.assertEqual(result, ["notepad.exe"])
        self.assertEqual(requested, [102])
        self.assertFalse(any(p.terminated for p in [allowed, blocked, protected, system, os_binary]))

    def test_hosts_restoration_preserves_unmanaged_lines(self):
        target = os.path.join(self.temp.name, "hosts")
        backup = os.path.join(self.temp.name, "backup")
        original = "127.0.0.1 localhost\n1.2.3.4 custom.example\n"
        Path(target).write_text(original, encoding="utf-8")
        engine = hosts.HostsEnforcementEngine.__new__(hosts.HostsEnforcementEngine)
        engine._hosts_path = target
        with patch.object(hosts, "BACKUP_FILE", backup):
            self.assertTrue(engine.apply_rules(["blocked.example"]))
            self.assertTrue(engine.restore_rules())
        self.assertEqual(Path(target).read_text(encoding="utf-8"), original)
        self.assertEqual(hosts._remove_managed_block(["a\n", hosts.MARKER_START + "\n", "b\n", hosts.MARKER_END + "\n"]), ["a\n"])
        with self.assertRaises(ValueError):
            hosts._remove_managed_block([hosts.MARKER_START + "\n", "unmanaged?\n"])
        with self.assertRaises(ValueError):
            hosts._remove_managed_block([hosts.MARKER_END + "\n"])
        with self.assertRaises(ValueError):
            hosts._remove_managed_block([hosts.MARKER_START + "\n", hosts.MARKER_START + "\n"])

    def test_hosts_restore_preserves_non_utf8_bytes(self):
        target = os.path.join(self.temp.name, "hosts-binary")
        backup = os.path.join(self.temp.name, "backup-binary")
        original = b"127.0.0.1 localhost\r\n1.2.3.4 custom-\xff.example\r\n"
        Path(target).write_bytes(original)
        engine = hosts.HostsEnforcementEngine.__new__(hosts.HostsEnforcementEngine)
        engine._hosts_path = target
        with patch.object(hosts, "BACKUP_FILE", backup):
            self.assertTrue(engine.apply_rules(["blocked.example"]))
            self.assertTrue(engine.restore_rules())
        self.assertEqual(Path(target).read_bytes(), original)

    def test_hosts_refuses_missing_final_newline_without_changing_file(self):
        target = os.path.join(self.temp.name, "hosts-no-newline")
        original = b"127.0.0.1 localhost"
        Path(target).write_bytes(original)
        engine = hosts.HostsEnforcementEngine.__new__(hosts.HostsEnforcementEngine)
        engine._hosts_path = target
        self.assertFalse(engine.apply_rules(["blocked.example"]))
        self.assertEqual(Path(target).read_bytes(), original)

    def test_hosts_rejects_local_ip_and_backend_domains(self):
        self.assertEqual(hosts.normalize_domain("localhost"), "")
        self.assertEqual(hosts.normalize_domain("router.local"), "")
        self.assertEqual(hosts.normalize_domain("192.168.1.1"), "")
        self.assertEqual(hosts.normalize_domain(hosts.SERVER_IP), "")
        self.assertEqual(hosts.normalize_domain("example.com"), "example.com")

    def test_hosts_does_not_overwrite_concurrent_edit(self):
        target = os.path.join(self.temp.name, "hosts-concurrent")
        backup = os.path.join(self.temp.name, "hosts-concurrent-backup")
        Path(target).write_text("127.0.0.1 localhost\n", encoding="utf-8")
        engine = hosts.HostsEnforcementEngine.__new__(hosts.HostsEnforcementEngine)
        engine._hosts_path = target
        original_reader = hosts._read_hosts_lines
        def edit_during_read(path):
            lines = original_reader(path)
            Path(path).write_text("127.0.0.1 localhost\n1.2.3.4 user-added.example\n", encoding="utf-8")
            return lines
        with patch.object(hosts, "BACKUP_FILE", backup), patch.object(hosts, "_read_hosts_lines", side_effect=edit_during_read):
            self.assertFalse(engine.apply_rules(["blocked.example"]))
        self.assertIn("user-added.example", Path(target).read_text(encoding="utf-8"))

    def test_dns_backup_retained_on_restore_failure(self):
        with patch.object(dns, "_load_dns_backup", return_value={"interface": "Test", "servers": ["1.1.1.1"]}), \
             patch.object(dns, "_get_current_dns_windows", return_value=["127.0.0.1"]), \
             patch.object(dns, "_set_dns_windows", return_value=False), \
             patch.object(dns, "_remove_dns_backup") as remove, \
             patch.object(dns.platform, "system", return_value="Windows"):
            self.assertFalse(dns._restore_dns_from_backup())
            remove.assert_not_called()

    def test_invalid_dns_backup_is_not_silently_discarded(self):
        backup = os.path.join(self.temp.name, "dns-backup.json")
        Path(backup).write_text("{broken", encoding="utf-8")
        with patch.object(dns, "DNS_BACKUP_FILE", backup), \
             patch.object(dns, "_remove_dns_backup") as remove:
            self.assertFalse(dns._restore_dns_from_backup())
            remove.assert_not_called()
        self.assertTrue(os.path.exists(backup))

    def test_dns_restore_keeps_backup_when_adapter_cannot_be_read(self):
        with patch.object(dns, "_load_dns_backup", return_value={"interface": "Test", "servers": ["1.1.1.1"]}), \
             patch.object(dns, "_get_current_dns_windows", return_value=None), \
             patch.object(dns, "_remove_dns_backup") as remove, \
             patch.object(dns.platform, "system", return_value="Windows"):
            self.assertFalse(dns._restore_dns_from_backup())
            remove.assert_not_called()

    def test_dns_restore_preserves_new_secondary_server(self):
        with patch.object(dns, "_load_dns_backup", return_value={"interface": "Test", "servers": ["8.8.8.8"]}), \
             patch.object(dns, "_get_current_dns_windows", return_value=["127.0.0.1", "1.1.1.1"]), \
             patch.object(dns, "_set_dns_windows", return_value=True) as set_dns, \
             patch.object(dns, "_remove_dns_backup") as remove, \
             patch.object(dns.platform, "system", return_value="Windows"):
            self.assertTrue(dns._restore_dns_from_backup())
            set_dns.assert_called_once_with("Test", "1.1.1.1")
            remove.assert_called_once()

    def test_no_policy_restores_previous_enforcement(self):
        class FakeEngine:
            name = "fake"
            restored = False
            def restore_rules(self):
                self.restored = True
                return True

        engine = FakeEngine()
        with patch.object(agent, "fetch_config_with_retry", return_value=None), \
             patch.object(agent, "LAST_STATE", "ACTIVE"), \
             patch.object(agent, "activity_tracker", None):
            agent.sync_once(engine)
            self.assertTrue(engine.restored)
            self.assertEqual(agent.LAST_STATE, "STANDBY")

    def test_restart_cleanup_checks_hosts_and_dns_even_after_mode_change(self):
        with patch.object(hosts.HostsEnforcementEngine, "restore_rules", return_value=True) as restore_hosts, \
             patch.object(dns, "_restore_dns_from_backup", return_value=True) as restore_dns:
            self.assertTrue(enforcement.restore_previous_system_state())
            restore_hosts.assert_called_once()
            restore_dns.assert_called_once()

    def test_dns_setting_cannot_redirect_adapter(self):
        with patch.object(enforcement, "HostsEnforcementEngine") as hosts_engine, \
             patch.object(dns, "_set_dns_windows") as set_dns:
            hosts_engine.return_value.is_available.return_value = True
            self.assertIs(enforcement.get_engine("DNS"), hosts_engine.return_value)
            self.assertFalse(dns.DnsEnforcementEngine.__new__(dns.DnsEnforcementEngine).apply_rules(["example.com"]))
            set_dns.assert_not_called()

    def test_activity_tracking_stops_and_clears_after_policy_loss(self):
        class Tracker:
            started = 0
            stopped = 0
            cleared = 0
            def set_blocked_domains(self, domains):
                pass
            def start(self):
                self.started += 1
            def stop(self):
                self.stopped += 1
            def clear(self):
                self.cleared += 1

        class Engine:
            name = "fake"
            def apply_rules(self, domains):
                return True
            def restore_rules(self):
                return True

        tracker = Tracker()
        policy = {"active": True, "blockedDomains": ["example.com"], "blockedApps": []}
        with patch.object(agent, "STOP_FILE", os.path.join(self.temp.name, "stop")), \
             patch.object(agent, "activity_tracker", tracker), \
             patch.object(agent, "LAST_STATE", None), \
             patch.object(agent, "LAST_APPLIED_DOMAINS", None), \
             patch.object(agent, "fetch_config_with_retry", side_effect=[policy, None]), \
             patch.object(agent, "report_to_server"):
            agent.sync_once(Engine())
            self.assertEqual(tracker.started, 1)
            agent.sync_once(Engine())
            self.assertGreaterEqual(tracker.stopped, 1)
            self.assertGreaterEqual(tracker.cleared, 1)

    def test_second_agent_instance_does_not_touch_system_state(self):
        with patch.object(agent, "acquire_main_instance", return_value=False), \
             patch.object(agent, "restore_previous_system_state") as restore:
            agent.main()
            restore.assert_not_called()

    def test_install_registers_recovery_before_logon_task(self):
        class Result:
            returncode = 0
            stderr = ""
        source = os.path.join(self.temp.name, "source.exe")
        Path(source).write_bytes(b"mock executable")
        installed = os.path.join(self.temp.name, "AcademiaShield")
        calls = []
        def fake_run(args, **kwargs):
            calls.append(args)
            return Result()
        with patch.object(agent.platform, "system", return_value="Windows"), \
             patch.object(agent, "_is_admin", return_value=True), \
             patch.object(agent.sys, "frozen", True, create=True), \
             patch.object(agent, "_get_current_exe", return_value=source), \
             patch.object(agent, "INSTALL_DIR", installed), \
             patch.object(agent, "INSTALL_EXE", os.path.join(installed, "AcademiaShield.exe")), \
             patch.object(agent, "INSTALL_ENV", os.path.join(installed, ".env.production")), \
             patch.object(agent, "STOP_FILE", os.path.join(installed, "stop.request")), \
             patch.object(agent, "load_credential", return_value=None), \
             patch.object(agent.subprocess, "run", side_effect=fake_run):
            self.assertEqual(agent.do_install(), 0)
        self.assertEqual(calls[0][3], agent.RECOVERY_TASK_NAME)
        self.assertEqual(calls[1][3], agent.TASK_NAME)
        self.assertFalse(any("/delete" in call for call in calls))

    def test_recovery_restores_when_cache_expired_without_network(self):
        with patch.object(agent, "STOP_FILE", os.path.join(self.temp.name, "stop")), \
             patch.object(agent, "DNS_BACKUP_FILE", os.path.join(self.temp.name, "dns-backup")), \
             patch.object(agent, "load_credential", return_value="device.secret"), \
             patch.object(agent.http_client, "load_cached_config", return_value=None), \
             patch.object(agent, "restore_previous_system_state", return_value=True) as restore:
            self.assertTrue(agent.recover_expired_policy())
            restore.assert_called_once()

    def test_recovery_leaves_valid_policy_untouched(self):
        with patch.object(agent, "STOP_FILE", os.path.join(self.temp.name, "stop")), \
             patch.object(agent, "DNS_BACKUP_FILE", os.path.join(self.temp.name, "dns-backup")), \
             patch.object(agent, "load_credential", return_value="device.secret"), \
             patch.object(agent.http_client, "load_cached_config", return_value=self.policy(datetime.now(timezone.utc) + timedelta(minutes=1))), \
             patch.object(agent, "restore_previous_system_state") as restore:
            self.assertTrue(agent.recover_expired_policy())
            restore.assert_not_called()

    def test_recovery_restores_legacy_dns_even_with_valid_cache(self):
        backup = os.path.join(self.temp.name, "legacy-dns-backup")
        Path(backup).write_text("mock", encoding="utf-8")
        with patch.object(agent, "STOP_FILE", os.path.join(self.temp.name, "stop")), \
             patch.object(agent, "DNS_BACKUP_FILE", backup), \
             patch.object(agent, "load_credential", return_value="device.secret"), \
             patch.object(agent.http_client, "load_cached_config", return_value=self.policy(datetime.now(timezone.utc) + timedelta(minutes=1))), \
             patch.object(agent, "restore_previous_system_state", return_value=True) as restore:
            self.assertTrue(agent.recover_expired_policy())
            restore.assert_called_once()

    def test_uninstall_restores_and_preserves_files(self):
        class Result:
            returncode = 0
            stderr = ""
        installed = os.path.join(self.temp.name, "AcademiaShield")
        os.makedirs(installed)
        keep = os.path.join(installed, "student-file.txt")
        Path(keep).write_text("keep", encoding="utf-8")
        with patch.object(agent.platform, "system", return_value="Windows"), \
             patch.object(agent, "_is_admin", return_value=True), \
             patch.object(agent.sys, "frozen", True, create=True), \
             patch.object(agent, "STOP_FILE", os.path.join(installed, "stop.request")), \
             patch.object(agent, "INSTALL_DIR", installed), \
             patch.object(agent.subprocess, "run", return_value=Result()), \
             patch.object(agent, "restore_previous_system_state", return_value=True), \
             patch.object(agent, "clear_credential"), \
             patch.object(agent.shutil, "rmtree") as remove_tree:
            self.assertEqual(agent.do_uninstall(), 0)
            remove_tree.assert_not_called()
        self.assertTrue(os.path.exists(keep))


if __name__ == "__main__":
    unittest.main()
