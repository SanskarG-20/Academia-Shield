import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime

# ━━━━━━━━━━━━━━━━━━━━━━
# CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━
SERVER_IP = "192.168.137.1"
BASE = f"http://{SERVER_IP}:5000"
POLL_INTERVAL = 30
TOKEN = None

# ━━━━━━━━━━━━━━━━━━━━━━
# HELPER
# ━━━━━━━━━━━━━━━━━━━━━━
def api(method, path, body=None, auth=True):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json"}
    
    if auth and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
        
    data = json.dumps(body).encode('utf-8') if body else None
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req) as response:
            payload = json.loads(response.read().decode('utf-8'))

            # Unwrap standard API envelope: { success, data, message }
            if isinstance(payload, dict) and "success" in payload and "data" in payload:
                if not payload.get("success"):
                    raise RuntimeError(payload.get("message", "API request failed"))
                return payload.get("data")

            return payload
    except urllib.error.URLError as e:
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"\n[ERROR] API request failed: {method} {url}")
        print(f"        {error_msg}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] API request failed: {method} {url}")
        print(f"        {str(e)}")
        sys.exit(1)

def get_time():
    return datetime.now().strftime("%H:%M:%S")

# ━━━━━━━━━━━━━━━━━━━━━━
# DEMO FLOW
# ━━━━━━━━━━━━━━━━━━━━━━
def main():
    global TOKEN
    
    print("╔══════════════════════════════════════╗")
    print("║   ACADEMIA SHIELD — LIVE DEMO        ║")
    print("║   Faculty Demonstration v1.0         ║")
    print("╚══════════════════════════════════════╝")
    print(f"Server: {BASE}")
    print(f"Time:   {get_time()}\n")
    
    time.sleep(1)

    # ---------------------------------------------------------
    # STEP 1
    # ---------------------------------------------------------
    print("Step 1/5 — Professor Authentication...")
    login_res = api("POST", "/api/auth/professor/login", {
        "email": "demo@professor.com",
        "password": "password123"
    }, auth=False)
    
    TOKEN = login_res.get("token")
    if not TOKEN:
        print("❌ Failed to retrieve authentication token.")
        sys.exit(1)
        
    print("✅ Authenticated as Demo Professor\n")
    time.sleep(2)

    # ---------------------------------------------------------
    # STEP 2
    # ---------------------------------------------------------
    print("Step 2/5 — Fetching Block Rules...")
    rules = api("GET", "/api/rules")
    for rule in rules:
        sites = rule.get("websites", [])
        apps = rule.get("applications", [])
        name = rule.get("name", "Unknown Rule")
        print(f"  🚫 Rule: {name} → {len(sites)} sites, {len(apps)} apps")
    print()
    time.sleep(2)

    # ---------------------------------------------------------
    # STEP 3
    # ---------------------------------------------------------
    print("Step 3/5 — Activating Block Session...")
    sessions = api("GET", "/api/sessions")
    
    target_session = None
    for s in sessions:
        if s.get("status", "").lower() in ["upcoming", "scheduled"]:
            target_session = s
            break
            
    if not target_session:
        print("❌ No upcoming/scheduled sessions found. Please create one in the Dashboard to demo.")
        print("Looking at current sessions:")
        for s in sessions:
            print(f"   - {s.get('title')} ({s.get('status')})")
        sys.exit(1)
        
    session_id = target_session.get("id") or target_session.get("_id")
    api("PATCH", f"/api/sessions/{session_id}/status", {"status": "active"})
    
    title = target_session.get("title", 'Unknown Session')
    print(f"✅ Session ACTIVATED: {title}")
    print(f"   Students will be blocked within {POLL_INTERVAL}s (next agent poll)\n")
    time.sleep(2)

    # ---------------------------------------------------------
    # STEP 4
    # ---------------------------------------------------------
    print("Step 4/5 — Live Monitoring (60 seconds)...")
    print("   Watching agent-config endpoint for state changes...")
    print("─" * 50)

    start = time.time()
    try:
        while time.time() - start < 60:
            config = api("GET", "/api/agent/config", auth=False)
            status = "🔴 BLOCKING ACTIVE" if config.get("blocking_active") else "🟢 STANDBY"
            domains = config.get("domains", [])
            active_list = config.get("active_sessions", [])
            
            print(f"  [{get_time()}] {status} | {len(domains)} domains | {len(active_list)} session(s)")
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nMonitoring interrupted.")
        
    print()

    # ---------------------------------------------------------
    # STEP 5
    # ---------------------------------------------------------
    print("Step 5/5 — Ending Session (Access Restored)...")
    api("PATCH", f"/api/sessions/{session_id}/status", {"status": "completed"})
    time.sleep(3)
    
    config = api("GET", "/api/agent/config", auth=False)
    final_status = config.get("blocking_active", False)
    print(f"✅ Session ended. blocking_active = {final_status}")
    print(f"   Students will regain access within {POLL_INTERVAL}s\n")

    # ---------------------------------------------------------
    # FINAL
    # ---------------------------------------------------------
    print("╔══════════════════════════════════════╗")
    print("║   DEMO COMPLETE ✅                   ║")
    print("╚══════════════════════════════════════╝")
    print("What faculty saw:")
    print("  1. Professor authenticated")
    print("  2. Block rules loaded from MongoDB Atlas")
    print("  3. Session activated → blocking enforced on student agents")
    print("  4. Real-time status monitored via API")
    print("  5. Session ended → access automatically restored")

if __name__ == "__main__":
    main()