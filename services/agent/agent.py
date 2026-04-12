import os
import sys
import time
import json
import socket
import platform
import urllib.request
import urllib.error
from datetime import datetime

# ━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━
# ⚠️  SET THIS TO PROFESSOR'S LAPTOP HOTSPOT IP BEFORE DEMO
# Windows: ipconfig → Wireless LAN adapter → IPv4 Address
# Mac/Linux: ifconfig en0 | grep inet
SERVER_IP   = "192.168.137.1"
SERVER_PORT = 5000
POLL_INTERVAL = 30          # seconds between checks
CACHE_FILE    = "last_config.json"
MARKER        = "# academia-shield"

# ━━━━━━━━━━━━━━━━━━━━━━
# HOSTS FILE PATH
# ━━━━━━━━━━━━━━━━━━━━━━
def get_hosts_path():
    system = platform.system()
    if system == "Windows":
        return r"C:\Windows\System32\drivers\etc\hosts"
    elif system == "Darwin" or system == "Linux":
        return "/etc/hosts"
    else:
        print("[ERROR] Unsupported OS. Cannot determine hosts file path.")
        sys.exit(1)

HOSTS_FILE = get_hosts_path()

# ━━━━━━━━━━━━━━━━━━━━━━
# FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━
def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def fetch_config():
    url = f"http://{SERVER_IP}:{SERVER_PORT}/api/agent/config"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode('utf-8')
            config = json.loads(data)
            
            # Save raw JSON to cache
            with open(CACHE_FILE, 'w') as f:
                json.dump(config, f)
            return config
    except (urllib.error.URLError, socket.timeout) as e:
        print(f"[{get_timestamp()}] [WARN] Server unreachable — using cached config")
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"[{get_timestamp()}] [WARN] Cache file corrupted.")
                return None
        return None

def block_domains(domains):
    try:
        with open(HOSTS_FILE, 'r') as f:
            lines = f.readlines()

        # Clean existing markers just in case to avoid duplicates
        cleaned_lines = [line for line in lines if MARKER not in line]

        # Ensure newline before appending
        if cleaned_lines and not cleaned_lines[-1].endswith('\n'):
            cleaned_lines.append('\n')

        # Add new block lines
        for domain in domains:
            domain = domain.strip().lower()
            if not domain:
                continue
            cleaned_lines.append(f"0.0.0.0\t{domain}\t{MARKER}\n")
            if not domain.startswith("www."):
                cleaned_lines.append(f"0.0.0.0\twww.{domain}\t{MARKER}\n")
        
        with open(HOSTS_FILE, 'w') as f:
            f.writelines(cleaned_lines)
            
        print(f"[{get_timestamp()}] [BLOCKED] {len(domains)} domains enforced")
        
    except PermissionError:
        print("\n❌ Permission denied. Run with:")
        print("   Mac/Linux: sudo python3 agent.py")
        print("   Windows:   Right-click terminal → Run as Administrator")
        sys.exit(1)

def unblock_domains():
    try:
        with open(HOSTS_FILE, 'r') as f:
            lines = f.readlines()
            
        original_count = len(lines)
        cleaned_lines = [line for line in lines if MARKER not in line]

        if len(cleaned_lines) != original_count:
            with open(HOSTS_FILE, 'w') as f:
                f.writelines(cleaned_lines)

        print(f"[{get_timestamp()}] [UNBLOCKED] Access restored")

    except PermissionError:
        print("\n❌ Permission denied. Run with:")
        print("   Mac/Linux: sudo python3 agent.py")
        print("   Windows:   Right-click terminal → Run as Administrator")
        sys.exit(1)

def is_in_schedule(config):
    active_sessions = config.get("active_sessions", [])
    is_blocking = config.get("blocking_active", False)
    
    if not is_blocking:
        return False
        
    for session in active_sessions:
        ends_at = session.get("ends_at")
        if ends_at:
            try:
                # Assuming UTC ISO strings from API: 2026-03-14T20:30:00Z
                ends_dt = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
                # Getting UTC time
                current_utc = datetime.utcnow()
                # Check if current time is before the end time
                if current_utc.timestamp() < ends_dt.timestamp() and config.get("blocking_active", False):
                    return True
            except ValueError:
                continue
    return False

# ━━━━━━━━━━━━━━━━━━━━━━
# MAIN LOOP
# ━━━━━━━━━━━━━━━━━━━━━━
def main():
    print("╔══════════════════════════════════╗")
    print("║   ACADEMIA SHIELD AGENT v1.0     ║")
    print("╚══════════════════════════════════╝")
    print(f"Server:   http://{SERVER_IP}:{SERVER_PORT}")
    print(f"Polling:  every {POLL_INTERVAL}s")
    print("Run with sudo (Mac/Linux) or as Administrator (Windows)")
    print("Press Ctrl+C to stop")
    print("─" * 40)

    last_state = None  # track state changes to avoid redundant writes

    while True:
        try:
            config = fetch_config()
            if config is not None:
                should_block = config.get("blocking_active", False)
                domains_to_block = config.get("domains", [])
                
                if should_block and last_state != "blocking":
                    block_domains(domains_to_block)
                    last_state = "blocking"
                elif not should_block and last_state == "blocking":
                    unblock_domains()
                    last_state = "unblocked"
                else:
                    # No state change — just print status
                    status = "🔴 BLOCKING" if should_block else "🟢 STANDBY"
                    print(f"[{get_timestamp()}] {status} | domains: {len(domains_to_block)}")
            else:
                print(f"[{get_timestamp()}] [WARN] Could not retrieve configuration. Retrying in {POLL_INTERVAL}s")

            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            print("\n[EXIT] Cleaning up — removing all blocks...")
            unblock_domains()
            print("[EXIT] Done. Goodbye.")
            break

if __name__ == "__main__":
    main()