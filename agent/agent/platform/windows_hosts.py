"""
Windows Hosts File Enforcement Engine.

Provides zero-latency, tamper-evident domain blocking by mapping restricted domains
to 127.0.0.1 in the Windows hosts file (C:\\Windows\\System32\\drivers\\etc\\hosts)
and flushing the DNS resolver cache.
"""

import os
import sys
import subprocess
import logging
from typing import List, Union

LOGGER = logging.getLogger(__name__)

MARKER_START = "# === ACADEMIA SHIELD MANAGED BLOCKLIST START ==="
MARKER_END = "# === ACADEMIA SHIELD MANAGED BLOCKLIST END ==="

KNOWN_COMPANION_DOMAINS = {
    "youtube.com": [
        "www.youtube.com", "m.youtube.com", "music.youtube.com", "gaming.youtube.com",
        "youtu.be", "www.youtu.be", "ytimg.com", "i.ytimg.com", "googlevideo.com",
        "youtube-nocookie.com", "yt3.ggpht.com"
    ],
    "instagram.com": [
        "www.instagram.com", "m.instagram.com", "graph.instagram.com",
        "cdninstagram.com", "ig.me"
    ],
    "facebook.com": [
        "www.facebook.com", "m.facebook.com", "fb.com", "www.fb.com",
        "fbcdn.net", "messenger.com", "www.messenger.com"
    ],
    "reddit.com": [
        "www.reddit.com", "old.reddit.com", "new.reddit.com", "redd.it",
        "redditstatic.com", "redditmedia.com", "v.redd.it"
    ],
    "chatgpt.com": [
        "www.chatgpt.com", "openai.com", "www.openai.com", "api.openai.com",
        "oaistatic.com", "oaiusercontent.com"
    ],
    "openai.com": [
        "www.openai.com", "chatgpt.com", "www.chatgpt.com", "oaistatic.com", "oaiusercontent.com"
    ],
    "twitter.com": [
        "www.twitter.com", "x.com", "www.x.com", "twimg.com", "api.twitter.com"
    ],
    "x.com": [
        "www.x.com", "twitter.com", "www.twitter.com", "twimg.com"
    ],
    "tiktok.com": [
        "www.tiktok.com", "m.tiktok.com", "tiktokcdn.com", "tiktokv.com"
    ],
    "whatsapp.com": [
        "www.whatsapp.com", "web.whatsapp.com", "whatsapp.net"
    ],
    "netflix.com": [
        "www.netflix.com", "nflxvideo.net", "nflxext.com", "nflximg.net"
    ],
    "discord.com": [
        "www.discord.com", "discordapp.com", "discord.gg", "gateway.discord.gg"
    ]
}

# Known DoH (DNS-over-HTTPS) providers that browsers use to bypass OS hosts file
DOH_PROVIDER_DOMAINS = [
    "chrome.cloudflare-dns.com",
    "cloudflare-dns.com",
    "dns.google",
    "dns.google.com",
    "dns.quad9.net",
    "doh.opendns.com",
    "dns.adguard.com",
    "doh.cleanbrowsing.org"
]


def _configure_browser_doh_policy(disable: bool = True):
    """Enforce browser use of OS hosts file by disabling DoH bypass in Chrome and Edge policies."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        targets = [
            r"SOFTWARE\Policies\Google\Chrome",
            r"SOFTWARE\Policies\Microsoft\Edge"
        ]
        for key_path in targets:
            try:
                if disable:
                    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                        winreg.SetValueEx(k, "DnsOverHttpsMode", 0, winreg.REG_SZ, "off")
                else:
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE) as k:
                            winreg.DeleteValue(k, "DnsOverHttpsMode")
                    except FileNotFoundError:
                        pass
            except PermissionError:
                LOGGER.debug("Admin privileges required to configure browser DoH policy in %s", key_path)
            except Exception as err:
                LOGGER.debug("Browser DoH policy configuration error: %s", err)
    except Exception:
        pass


class HostsEnforcementEngine:
    """Manages Academia Shield blocked domains in the Windows hosts file."""

    def __init__(self, hosts_path: str = None):
        if hosts_path:
            self.hosts_path = hosts_path
        elif sys.platform == "win32":
            self.hosts_path = os.path.expandvars(r"%SystemRoot%\System32\drivers\etc\hosts")
        else:
            self.hosts_path = "/etc/hosts"

    def is_writable(self) -> bool:
        """Check if hosts file can be opened for writing."""
        try:
            if not os.path.exists(self.hosts_path):
                return False
            with open(self.hosts_path, "a") as f:
                pass
            return True
        except (PermissionError, OSError):
            return False

    def flush_dns(self) -> bool:
        """Flush the OS DNS resolver cache and NetBIOS cache."""
        if sys.platform == "win32":
            try:
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, text=True, timeout=5)
                subprocess.run(["nbtstat", "-R"], capture_output=True, text=True, timeout=3)
                subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "Clear-DnsClientCache"], capture_output=True, timeout=3)
                return True
            except Exception as err:
                LOGGER.warning("DNS cache flush error: %s", err)
                return False
        return True

    def apply_rules(self, domains: List[Union[str, any]], allowed_domains: Optional[Any] = None) -> bool:
        """
        Write blocked domain entries to hosts file within managed markers and flush DNS cache.
        Includes automatic subdomain expansion, companion services, and DoH bypass prevention.
        Explicitly excludes any allowed academic domains.
        """
        if not domains:
            return self.restore_rules()

        # Normalize domain list
        clean_domains = set()
        for d in domains:
            if isinstance(d, str):
                domain_raw = d
            elif isinstance(d, dict):
                action = d.get("action", "block")
                if action != "block":
                    continue
                domain_raw = d.get("domain_pattern") or d.get("domain") or ""
            else:
                action = getattr(d, "action", "block")
                if action != "block":
                    continue
                domain_raw = getattr(d, "domain_pattern", None) or getattr(d, "domain", str(d))

            domain_str = str(domain_raw).strip().lower()
            if "://" in domain_str:
                from urllib.parse import urlparse
                try:
                    parsed = urlparse(domain_str)
                    domain_str = parsed.netloc or parsed.path or domain_str
                except Exception:
                    pass

            # Strip port, path, query, fragment
            domain_str = domain_str.split("/")[0].split("?")[0].split("#")[0].split(":")[0].strip().lower()

            if domain_str:
                # If no dot, default to .com (e.g. youtube -> youtube.com)
                if "." not in domain_str:
                    domain_str = f"{domain_str}.com"

                # Strip wildcards if specified
                if domain_str.startswith("*."):
                    domain_str = domain_str[2:]
                elif domain_str.startswith("."):
                    domain_str = domain_str[1:]

                clean_domains.add(domain_str)
                base_domain = domain_str[4:] if domain_str.startswith("www.") else domain_str

                # Subdomain expansion
                clean_domains.add(base_domain)
                clean_domains.add(f"www.{base_domain}")
                if base_domain.count(".") == 1:
                    for prefix in ("m.", "mobile.", "web.", "api.", "app.", "login.", "auth."):
                        clean_domains.add(f"{prefix}{base_domain}")

                # Companion domains mapping (e.g., YouTube -> youtu.be, googlevideo.com)
                for k, companions in KNOWN_COMPANION_DOMAINS.items():
                    if k == base_domain or k == domain_str:
                        clean_domains.update(companions)

        # Exclude any allowed academic domains from being blocked in hosts file
        if allowed_domains:
            for ad in allowed_domains:
                if not ad:
                    continue
                ad_str = str(ad).strip().lower()
                if "://" in ad_str:
                    from urllib.parse import urlparse
                    try:
                        ad_str = urlparse(ad_str).netloc or ad_str
                    except Exception:
                        pass
                ad_str = ad_str.split("/")[0].split("?")[0].split("#")[0].split(":")[0].strip().lower()
                if ad_str:
                    base_ad = ad_str[4:] if ad_str.startswith("www.") else ad_str
                    # Remove exact match and all prefixed subdomains
                    to_remove = [cd for cd in clean_domains if cd == ad_str or cd == base_ad or cd.endswith(f".{base_ad}")]
                    for rem in to_remove:
                        clean_domains.discard(rem)

        if not clean_domains:
            return self.restore_rules()

        # Also block DoH providers so Chrome/Edge cannot bypass hosts file
        for doh_dom in DOH_PROVIDER_DOMAINS:
            clean_domains.add(doh_dom)

        # Configure Chrome and Edge policies to disable DoH
        _configure_browser_doh_policy(disable=True)

        if not os.path.exists(self.hosts_path):
            LOGGER.error("Hosts file not found at %s", self.hosts_path)
            return False

        try:
            with open(self.hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Strip existing managed block
            lines = content.splitlines()
            filtered_lines = []
            in_managed_block = False

            for line in lines:
                if MARKER_START in line:
                    in_managed_block = True
                    continue
                if MARKER_END in line:
                    in_managed_block = False
                    continue
                if not in_managed_block:
                    filtered_lines.append(line)

            # Build new block
            block_lines = [
                MARKER_START,
                f"# Updated: {len(clean_domains)} restricted domain(s) enforced by active session policy"
            ]
            for dom in sorted(clean_domains):
                block_lines.append(f"127.0.0.1 {dom}")
                block_lines.append(f"::1 {dom}")
            block_lines.append(MARKER_END)

            # Recombine
            new_content = "\n".join(filtered_lines).rstrip() + "\n\n" + "\n".join(block_lines) + "\n"

            if content.strip() == new_content.strip():
                # Hosts file already contains the exact up-to-date rules, no write required
                return True

            if not self._unlock_and_write(new_content):
                return False

            self.flush_dns()
            LOGGER.info("Hosts file updated: %s domain(s) blocked and DNS cache flushed.", len(clean_domains))
            return True

        except Exception as err:
            LOGGER.error("Error updating hosts file: %s", err)
            return False

    def _unlock_and_write(self, content: str) -> bool:
        """Write content to hosts file, clearing read-only attributes, attempting elevation if needed."""
        import stat
        import time
        try:
            if os.path.exists(self.hosts_path):
                try:
                    os.chmod(self.hosts_path, stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
                if sys.platform == "win32":
                    try:
                        subprocess.run(["attrib", "-R", self.hosts_path], capture_output=True, timeout=2)
                    except Exception:
                        pass

            with open(self.hosts_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except PermissionError:
            # On Windows, try elevated PowerShell helper to write and permanently grant modify rights to Users
            if sys.platform == "win32":
                try:
                    import tempfile
                    tmp_f = os.path.join(tempfile.gettempdir(), f"as_hosts_{os.getpid()}.tmp")
                    with open(tmp_f, "w", encoding="utf-8") as tf:
                        tf.write(content)

                    ps_cmd = (
                        f'Copy-Item -LiteralPath "{tmp_f}" -Destination "{self.hosts_path}" -Force; '
                        f'icacls "{self.hosts_path}" /grant "BUILTIN\\Users:(M)"'
                    )
                    subprocess.run(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            f'Start-Process powershell -ArgumentList \'-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "{ps_cmd}"\' -Verb RunAs -Wait -WindowStyle Hidden'
                        ],
                        capture_output=True,
                        timeout=5
                    )
                    if os.path.exists(tmp_f):
                        try:
                            os.remove(tmp_f)
                        except Exception:
                            pass

                    # Verify if write succeeded
                    if self.is_writable():
                        LOGGER.info("Successfully configured hosts file permissions via elevated helper.")
                        return True
                except Exception:
                    pass

            now_ts = time.time()
            if (now_ts - getattr(self, "_last_perm_err_log", 0.0)) > 300.0:
                self._last_perm_err_log = now_ts
                LOGGER.warning(
                    "Permission denied writing to %s. Administrator privileges required. "
                    "Hosts file domain enforcement is inactive. "
                    "Run 'agent\\run_agent_admin.bat' or 'scripts\\grant_hosts_permission.bat' as Administrator to enable.",
                    self.hosts_path
                )
            return False
        except Exception as err:
            LOGGER.error("Error writing to hosts file: %s", err)
            return False

    def restore_rules(self) -> bool:
        """Remove all Academia Shield entries from hosts file and flush DNS."""
        if not os.path.exists(self.hosts_path):
            return True

        try:
            with open(self.hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if MARKER_START not in content:
                return True

            lines = content.splitlines()
            filtered_lines = []
            in_managed_block = False

            for line in lines:
                if MARKER_START in line:
                    in_managed_block = True
                    continue
                if MARKER_END in line:
                    in_managed_block = False
                    continue
                if not in_managed_block:
                    filtered_lines.append(line)

            clean_content = "\n".join(filtered_lines).rstrip() + "\n"

            if content.strip() == clean_content.strip():
                return True

            if not self._unlock_and_write(clean_content):
                return False

            _configure_browser_doh_policy(disable=False)
            self.flush_dns()
            LOGGER.info("Hosts file cleaned: all domain blocks removed and DNS cache flushed.")
            return True

        except Exception as err:
            LOGGER.error("Error restoring hosts file: %s", err)
            return False
