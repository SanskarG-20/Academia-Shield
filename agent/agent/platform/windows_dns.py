"""
Windows Network Adapter DNS Configuration Adapter.

Provides explicit administrator-approved network adapter DNS configuration pointing to local resolver,
secure backup of original DNS settings, continuous drift detection, and safe restoration.
"""

import os
import json
import ctypes
import platform
import subprocess
import logging
from typing import Dict, Any, List, Optional

LOGGER = logging.getLogger(__name__)

class WindowsDNSAdapterManager:
    """Manages Windows network adapter DNS settings with backup & restoration."""

    def __init__(self, backup_dir: Optional[str] = None):
        self.backup_dir = backup_dir or os.path.expanduser("~/.academia_shield")
        os.makedirs(self.backup_dir, exist_ok=True)
        self.backup_file = os.path.join(self.backup_dir, "dns_adapter_backup.json")

    def is_admin(self) -> bool:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def get_active_adapters(self) -> List[Dict[str, Any]]:
        """Get connected physical/wireless network adapters."""
        adapters = []
        try:
            ps_script = """
            Get-NetAdapter | Where-Object Status -eq 'Up' |
                Select-Object InterfaceAlias, InterfaceIndex, Name |
                ConvertTo-Json
            """
            res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    adapters.append({
                        "alias": item.get("InterfaceAlias") or item.get("Name"),
                        "index": item.get("InterfaceIndex")
                    })
        except Exception as err:
            LOGGER.warning("PowerShell net adapter query exception: %s", err)

        if not adapters:
            # Fallback to default Ethernet/Wi-Fi
            adapters = [{"alias": "Wi-Fi", "index": None}, {"alias": "Ethernet", "index": None}]

        return adapters

    def configure_local_dns(self, target_dns: str = "127.0.0.1", resolver_healthy: bool = True, selected_adapter: Optional[str] = None) -> bool:
        """
        Configure Windows active network adapter to point to local DNS resolver.
        Requires explicit administrator privileges. Verifies resolver health first.
        Saves original settings securely before making any changes.
        """
        if not resolver_healthy:
            LOGGER.error("Cannot enable DNS enforcement: Local DNS resolver is not healthy.")
            return False

        if not self.is_admin():
            LOGGER.warning("Privilege Warning: Admin rights required to configure Windows adapter DNS. Skipping live adapter redirection.")
            return False

        # Save original settings first
        self.backup_original_dns()

        adapters = self.get_active_adapters()
        if selected_adapter:
            adapters = [a for a in adapters if a["alias"].lower() == selected_adapter.lower()]
            if not adapters:
                adapters = [{"alias": selected_adapter, "index": None}]

        success_count = 0

        for adapter in adapters:
            alias = adapter["alias"]
            try:
                cmd = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ServerAddresses ("{target_dns}")'
                res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    LOGGER.info("Configured DNS for adapter '%s' -> %s", alias, target_dns)
                    success_count += 1
                else:
                    # Fallback to netsh.  Do not report success unless netsh
                    # actually changes the adapter; a false positive here makes
                    # the agent claim DNS blocking is active when it is not.
                    netsh_res = subprocess.run(
                        ["netsh", "interface", "ipv4", "set", "dns", f"name={alias}", "static", target_dns],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if netsh_res.returncode == 0:
                        LOGGER.info("Configured DNS for adapter '%s' via netsh -> %s", alias, target_dns)
                        success_count += 1
                    else:
                        LOGGER.error(
                            "Could not configure DNS for adapter '%s' via PowerShell or netsh: %s",
                            alias,
                            (netsh_res.stderr or netsh_res.stdout).strip(),
                        )
            except Exception as err:
                LOGGER.error("Failed configuring DNS on adapter '%s': %s", alias, err)

        return success_count > 0

    def backup_original_dns(self) -> bool:
        """Save current adapter DNS server configuration to backup JSON file."""
        if os.path.exists(self.backup_file):
            try:
                with open(self.backup_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                # Verify it's not poisoned with loopback
                is_poisoned = False
                for alias, srvs in existing.items():
                    if any(s in ("127.0.0.1", "::1", "localhost") for s in srvs):
                        is_poisoned = True
                        break
                if not is_poisoned and existing:
                    return True  # Preserve clean initial backup
                LOGGER.warning("Detected poisoned DNS backup file containing loopback IP. Re-creating clean backup.")
            except Exception:
                pass

        backup_data = {}
        adapters = self.get_active_adapters()

        for adapter in adapters:
            alias = adapter["alias"]
            try:
                ps_script = f'Get-DnsClientServerAddress -InterfaceAlias "{alias}" -AddressFamily IPv4 | Select-Object -ExpandProperty ServerAddresses'
                res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], capture_output=True, text=True, timeout=5)
                servers = [s.strip() for s in res.stdout.splitlines() if s.strip()]
                # Filter out any loopback IPs so we never back up 127.0.0.1 as original DNS
                clean_servers = [s for s in servers if s not in ("127.0.0.1", "::1", "localhost")]
                backup_data[alias] = clean_servers
            except Exception as err:
                LOGGER.warning("Could not query original DNS for '%s': %s", alias, err)

        try:
            with open(self.backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2)
            LOGGER.info("Backed up original Windows DNS configuration to %s", self.backup_file)
            return True
        except Exception as err:
            LOGGER.error("Failed writing DNS backup file: %s", err)
            return False

    def restore_original_dns(self) -> bool:
        """Restore original DNS configuration from backup JSON file."""
        if not self.is_admin():
            LOGGER.warning("Admin privileges required to restore Windows adapter DNS.")
            return False

        if not os.path.exists(self.backup_file):
            # Reset to DHCP default
            LOGGER.info("No DNS backup file found; resetting adapter DNS to DHCP default.")
            for adapter in self.get_active_adapters():
                alias = adapter["alias"]
                try:
                    cmd = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ResetServerAddresses'
                    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, timeout=5)
                except Exception:
                    pass
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5)
            return True

        try:
            with open(self.backup_file, "r", encoding="utf-8") as f:
                backup_data = json.load(f)

            for alias, servers in backup_data.items():
                clean_servers = [s for s in servers if s not in ("127.0.0.1", "::1", "localhost")] if servers else []
                try:
                    if clean_servers:
                        server_list_str = ",".join([f'"{s}"' for s in clean_servers])
                        cmd = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ServerAddresses ({server_list_str})'
                    else:
                        cmd = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ResetServerAddresses'

                    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, timeout=5)
                    LOGGER.info("Restored DNS for adapter '%s' -> %s", alias, clean_servers or "DHCP")
                except Exception as err:
                    LOGGER.error("Failed restoring DNS for '%s': %s", alias, err)

            try:
                os.remove(self.backup_file)
            except Exception:
                pass
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5)
            return True
        except Exception as err:
            LOGGER.error("Error reading DNS backup file for restoration: %s", err)
            return False

    def clean_stale_dns(self) -> bool:
        """
        Safety check: If any adapter is currently pointed to 127.0.0.1 while
        no local resolver is running, reset adapter DNS back to DHCP / backup.
        """
        if not self.is_admin():
            return False

        restored_any = False
        adapters = self.get_active_adapters()
        for adapter in adapters:
            alias = adapter["alias"]
            try:
                ps_script = f'Get-DnsClientServerAddress -InterfaceAlias "{alias}" -AddressFamily IPv4 | Select-Object -ExpandProperty ServerAddresses'
                res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], capture_output=True, text=True, timeout=5)
                servers = [s.strip() for s in res.stdout.splitlines() if s.strip()]
                if any(s in ("127.0.0.1", "::1") for s in servers):
                    LOGGER.warning("Stale loopback DNS detected on adapter '%s'. Resetting to DHCP / original configuration.", alias)
                    cmd = f'Set-DnsClientServerAddress -InterfaceAlias "{alias}" -ResetServerAddresses'
                    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, timeout=5)
                    restored_any = True
            except Exception:
                pass

        if os.path.exists(self.backup_file):
            try:
                self.restore_original_dns()
                restored_any = True
            except Exception:
                pass

        if restored_any:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5)
        return restored_any

    def detect_drift(self, expected_dns: str = "127.0.0.1") -> bool:
        """
        Compare current active adapter DNS configuration with expected_dns.
        Returns True if drift is detected.
        """
        if not self.is_admin():
            return False

        adapters = self.get_active_adapters()
        for adapter in adapters:
            alias = adapter["alias"]
            try:
                ps_script = f'Get-DnsClientServerAddress -InterfaceAlias "{alias}" -AddressFamily IPv4 | Select-Object -ExpandProperty ServerAddresses'
                res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script], capture_output=True, text=True, timeout=3)
                servers = [s.strip() for s in res.stdout.splitlines() if s.strip()]
                if expected_dns not in servers:
                    LOGGER.warning("DNS Drift Detected on adapter '%s': current=%s, expected=%s", alias, servers, expected_dns)
                    return True
            except Exception:
                pass
        return False
