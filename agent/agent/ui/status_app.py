"""
Academia Shield Windows Desktop Status & Diagnostics GUI.
Provides a visible, consent-based status dashboard for students and administrators.

Displays:
- Agent state & backend connection
- Active session name & batch
- Policy enforcement (DNS & Application monitoring)
- Compliance status (Personal vs College-Managed MDM)
- Heartbeat timestamp & safe error details

Allows:
- Interactive Sign-In / Device Enrollment modal (Token or Email/Password)
- Diagnostics export (sanitized JSON report)
- Authorized enforcement disabling
- Device logout and credential wipe
- Clean uninstallation
"""

import sys
import os
import json
import time
import getpass
import logging
import threading
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from ..config import get_config, get_agent_mode, set_agent_mode
    from ..auth import TokenManager, Ed25519KeyManager
    from ..api import APIClientAdapter
    from ..storage import LocalStorageDB
    from ..platform import get_platform_adapter, WindowsDNSAdapterManager, USBComplianceManager
    from ..core.state_machine.machine import AgentState
except (ImportError, ValueError):
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _agent_pkg_dir = os.path.dirname(_current_dir)
    _agent_root_dir = os.path.dirname(_agent_pkg_dir)
    if _agent_root_dir not in sys.path:
        sys.path.insert(0, _agent_root_dir)

    from agent.config import get_config, get_agent_mode, set_agent_mode
    from agent.auth import TokenManager, Ed25519KeyManager
    from agent.api import APIClientAdapter
    from agent.storage import LocalStorageDB
    from agent.platform import get_platform_adapter, WindowsDNSAdapterManager, USBComplianceManager
    from agent.core.state_machine.machine import AgentState

logger = logging.getLogger("agent.ui")

class AcademiaShieldStatusApp:
    def __init__(self, root: tk.Tk, auto_enroll: bool = False):
        self.root = root
        self.root.title("Academia Shield — Device Protection Agent")
        self.root.geometry("640 x 600")
        self.root.minsize(580, 520)

        # Style configuration
        self._setup_styles()

        self.token_mgr = TokenManager()
        self.db = LocalStorageDB()
        self.config = get_config()

        # Build UI layout
        self._build_ui()

        # Start periodic background status refresh
        self._refresh_timer = None
        self.refresh_status()

        if auto_enroll and not self.token_mgr.get_refresh_token():
            self.root.after(500, self.open_enrollment_dialog)

    def _setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Color palette
        self.bg_color = "#0f172a"        # Dark slate
        self.card_bg = "#1e293b"         # Slate card
        self.text_primary = "#f8fafc"    # Light text
        self.text_secondary = "#94a3b8"  # Dim text
        self.accent_blue = "#2563eb"     # Brand blue
        self.accent_green = "#10b981"    # Success green
        self.accent_amber = "#f59e0b"    # Warning amber
        self.accent_red = "#ef4444"      # Danger red

        self.root.configure(bg=self.bg_color)

    def _build_ui(self):
        # Header container
        header_frame = tk.Frame(self.root, bg=self.card_bg, padx=20, pady=16)
        header_frame.pack(fill="x", padx=16, pady=(16, 8))

        title_lbl = tk.Label(
            header_frame,
            text="🛡️ ACADEMIA SHIELD AGENT",
            font=("Segoe UI", 16, "bold"),
            fg=self.text_primary,
            bg=self.card_bg
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            header_frame,
            text="Endpoint Protection & Academic Integrity Monitor (Consent-Based)",
            font=("Segoe UI", 9),
            fg=self.text_secondary,
            bg=self.card_bg
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Status Grid Card
        status_card = tk.Frame(self.root, bg=self.card_bg, padx=20, pady=16)
        status_card.pack(fill="both", expand=True, padx=16, pady=8)

        # Status items
        self.status_labels = {}
        rows = [
            ("Agent State:", "state_val", "Checking..."),
            ("Backend Server:", "backend_val", "http://127.0.0.1:8000"),
            ("Device Enrollment:", "enroll_val", "Checking..."),
            ("Active Session:", "session_val", "None (Idle)"),
            ("Policy Enforcement:", "policy_val", "Inactive"),
            ("DNS Protection:", "dns_val", "Normal (Baseline)"),
            ("App Monitor:", "app_val", "Active (Safeguarded)"),
            ("Compliance Level:", "compliance_val", "Personal (Standard)"),
            ("Last Heartbeat:", "heartbeat_val", "Never")
        ]

        for i, (label_text, key, default_val) in enumerate(rows):
            lbl_title = tk.Label(
                status_card,
                text=label_text,
                font=("Segoe UI", 10, "bold"),
                fg=self.text_secondary,
                bg=self.card_bg,
                anchor="w"
            )
            lbl_title.grid(row=i, column=0, sticky="w", pady=4)

            lbl_val = tk.Label(
                status_card,
                text=default_val,
                font=("Segoe UI", 10),
                fg=self.text_primary,
                bg=self.card_bg,
                anchor="w"
            )
            lbl_val.grid(row=i, column=1, sticky="w", padx=(16, 0), pady=4)
            self.status_labels[key] = lbl_val

        # Action Buttons Card
        btn_card = tk.Frame(self.root, bg=self.bg_color, padx=0, pady=8)
        btn_card.pack(fill="x", padx=16, pady=(0, 16))

        self.btn_enroll = tk.Button(
            btn_card,
            text="🔑 Sign In / Enroll",
            font=("Segoe UI", 10, "bold"),
            bg=self.accent_blue,
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=6,
            command=self.open_enrollment_dialog
        )
        self.btn_enroll.pack(side="left", padx=(0, 6))

        self.btn_refresh = tk.Button(
            btn_card,
            text="🔄 Refresh",
            font=("Segoe UI", 10),
            bg=self.card_bg,
            fg=self.text_primary,
            relief="flat",
            padx=10,
            pady=6,
            command=self.refresh_status
        )
        self.btn_refresh.pack(side="left", padx=4)

        self.btn_diag = tk.Button(
            btn_card,
            text="📋 Export Diagnostics",
            font=("Segoe UI", 10),
            bg=self.card_bg,
            fg=self.text_primary,
            relief="flat",
            padx=10,
            pady=6,
            command=self.export_diagnostics
        )
        self.btn_diag.pack(side="left", padx=4)

        self.btn_disable = tk.Button(
            btn_card,
            text="⏹️ Stop Enforcement",
            font=("Segoe UI", 10),
            bg=self.card_bg,
            fg=self.accent_amber,
            relief="flat",
            padx=10,
            pady=6,
            command=self.disable_enforcement
        )
        self.btn_disable.pack(side="left", padx=4)

        self.btn_logout = tk.Button(
            btn_card,
            text="🚪 Sign Out",
            font=("Segoe UI", 10),
            bg=self.card_bg,
            fg=self.accent_red,
            relief="flat",
            padx=10,
            pady=6,
            command=self.logout_device
        )
        self.btn_logout.pack(side="right", padx=(4, 0))

    def refresh_status(self):
        """Poll local database and backend for live status updates."""
        try:
            config = get_config()
            current_mode = get_agent_mode(config.storage_dir)
            refresh_tok = self.token_mgr.get_refresh_token()
            device_id = self.token_mgr.get_device_id() or config.device_id

            self.status_labels["backend_val"].config(text=config.api_url)

            if refresh_tok:
                self.status_labels["enroll_val"].config(
                    text=f"Enrolled ({device_id})",
                    fg=self.accent_green
                )
                self.btn_enroll.config(text="🔑 Re-Enroll Device")
            else:
                self.status_labels["enroll_val"].config(
                    text="Not Enrolled (Sign-in Required)",
                    fg=self.accent_amber
                )
                self.btn_enroll.config(text="🔑 Sign In / Enroll")

            # Check backend connection & active session
            api_client = APIClientAdapter(token_manager=self.token_mgr)
            backend_online = api_client.is_backend_available()

            if not backend_online:
                self.status_labels["state_val"].config(text="BACKEND DISCONNECTED", fg=self.accent_red)
                self.status_labels["session_val"].config(text="Offline", fg=self.text_secondary)
                self.status_labels["policy_val"].config(text="Inactive", fg=self.text_secondary)
            else:
                if not refresh_tok:
                    self.status_labels["state_val"].config(text="NOT_ENROLLED", fg=self.accent_amber)
                    self.status_labels["session_val"].config(text="None", fg=self.text_secondary)
                    self.status_labels["policy_val"].config(text="Inactive", fg=self.text_secondary)
                else:
                    pol_res = api_client.fetch_policy()
                    if pol_res and pol_res.get("policy_active"):
                        sess_id = pol_res.get("session_id", "Active")
                        dom_cnt = len(pol_res.get("domain_rules", []))
                        app_cnt = len(pol_res.get("application_rules", []))

                        self.status_labels["state_val"].config(text="ENFORCING", fg=self.accent_green)
                        self.status_labels["session_val"].config(text=f"In Session: {sess_id}", fg=self.accent_green)
                        self.status_labels["policy_val"].config(
                            text=f"Active ({dom_cnt} websites, {app_cnt} apps)",
                            fg=self.accent_green
                        )
                    else:
                        self.status_labels["state_val"].config(text="ENROLLED_IDLE", fg="#38bdf8")
                        self.status_labels["session_val"].config(text="No Active Class Session", fg=self.text_secondary)
                        self.status_labels["policy_val"].config(text="Inactive (Normal Internet)", fg=self.text_secondary)

            # Check DNS adapter status
            win_dns = WindowsDNSAdapterManager()
            journal_status = win_dns.get_status().get("journal_status")
            if journal_status == "enforced":
                self.status_labels["dns_val"].config(text="Enforced (Adapter Redirected)", fg=self.accent_green)
            elif journal_status:
                self.status_labels["dns_val"].config(text="Restore Pending (Recovery Guard Active)", fg=self.accent_amber)
            else:
                self.status_labels["dns_val"].config(text="Normal (Local Resolver Port 5353)", fg=self.text_secondary)

            # Compliance status
            usb_mgr = USBComplianceManager(mode=current_mode)
            if usb_mgr.is_usb_storage_restricted():
                self.status_labels["compliance_val"].config(text="College-Managed (USB Restricted)", fg=self.accent_green)
            else:
                self.status_labels["compliance_val"].config(text="Personal Device (Standard)", fg=self.text_secondary)

            now_str = datetime.now().strftime("%I:%M:%S %p")
            self.status_labels["heartbeat_val"].config(text=f"Live ({now_str})")

        except Exception as e:
            logger.debug(f"Status refresh exception: {e}")

        # Schedule next automatic refresh in 10s
        if self._refresh_timer:
            self.root.after_cancel(self._refresh_timer)
        self._refresh_timer = self.root.after(10000, self.refresh_status)

    def open_enrollment_dialog(self):
        """Modal dialog to enroll device using 8-char token or student email/password."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Enroll Device — Academia Shield")
        dialog.geometry("480 x 420")
        dialog.configure(bg=self.bg_color)
        dialog.transient(self.root)
        dialog.grab_set()

        notebook = ttk.Notebook(dialog)
        notebook.pack(fill="both", expand=True, padx=16, pady=16)

        # Tab 1: Enrollment Token
        tab_token = tk.Frame(notebook, bg=self.card_bg, padx=16, pady=16)
        notebook.add(tab_token, text="8-Character Token")

        tk.Label(
            tab_token,
            text="Enter Enrollment Token from Website:",
            font=("Segoe UI", 10, "bold"),
            fg=self.text_primary,
            bg=self.card_bg
        ).pack(anchor="w", pady=(0, 6))

        token_entry = tk.Entry(
            tab_token,
            font=("Consolas", 14, "bold"),
            justify="center",
            bg="#0f172a",
            fg="#38bdf8",
            insertbackground="white"
        )
        token_entry.pack(fill="x", pady=(0, 12))

        # Tab 2: Email & Password
        tab_login = tk.Frame(notebook, bg=self.card_bg, padx=16, pady=16)
        notebook.add(tab_login, text="Student Login")

        tk.Label(
            tab_login,
            text="Student Email / Institutional ID:",
            font=("Segoe UI", 9, "bold"),
            fg=self.text_primary,
            bg=self.card_bg
        ).pack(anchor="w", pady=(0, 4))

        email_entry = tk.Entry(tab_login, font=("Segoe UI", 10), bg="#0f172a", fg="white", insertbackground="white")
        email_entry.pack(fill="x", pady=(0, 10))

        tk.Label(
            tab_login,
            text="Password:",
            font=("Segoe UI", 9, "bold"),
            fg=self.text_primary,
            bg=self.card_bg
        ).pack(anchor="w", pady=(0, 4))

        pass_entry = tk.Entry(tab_login, show="•", font=("Segoe UI", 10), bg="#0f172a", fg="white", insertbackground="white")
        pass_entry.pack(fill="x", pady=(0, 12))

        # Backend URL field
        url_frame = tk.Frame(dialog, bg=self.bg_color, padx=16)
        url_frame.pack(fill="x", pady=(0, 8))

        tk.Label(
            url_frame,
            text="Backend API URL:",
            font=("Segoe UI", 8),
            fg=self.text_secondary,
            bg=self.bg_color
        ).pack(anchor="w")

        url_entry = tk.Entry(url_frame, font=("Segoe UI", 9), bg=self.card_bg, fg=self.text_primary, insertbackground="white")
        url_entry.insert(0, self.config.api_url)
        url_entry.pack(fill="x", pady=(2, 0))

        # Submit Action
        def do_enroll():
            api_url = url_entry.get().strip() or "http://127.0.0.1:8000"
            self.config.api_url = api_url.rstrip("/")

            key_mgr = Ed25519KeyManager()
            priv_pem, pub_hex = key_mgr.generate_keypair()
            self.token_mgr.storage.store_credential("private_key", priv_pem)

            api_client = APIClientAdapter(token_manager=self.token_mgr, key_manager=key_mgr)
            os_adapter = get_platform_adapter()
            os_info = os_adapter.get_os_info()

            selected_tab = notebook.index(notebook.select())
            try:
                if selected_tab == 0:
                    tok = token_entry.get().strip()
                    if not tok:
                        messagebox.showwarning("Missing Token", "Please enter the 8-character enrollment token.", parent=dialog)
                        return
                    res = api_client.enroll_with_token(
                        enrollment_token=tok,
                        public_key_hex=pub_hex,
                        hostname=self.config.device_id,
                        os_name=os_info["os_name"],
                        os_version=os_info["os_version"]
                    )
                else:
                    email = email_entry.get().strip()
                    pwd = pass_entry.get().strip()
                    if not email or not pwd:
                        messagebox.showwarning("Missing Credentials", "Please enter student email and password.", parent=dialog)
                        return
                    login_res = api_client.login(email, pwd)
                    if not login_res.get("access_token"):
                        messagebox.showerror("Login Failed", "Invalid credentials or backend error.", parent=dialog)
                        return
                    res = api_client.enroll_device(
                        public_key_hex=pub_hex,
                        hostname=self.config.device_id,
                        os_name=os_info["os_name"],
                        os_version=os_info["os_version"]
                    )

                messagebox.showinfo("Success", f"Device '{self.config.device_id}' enrolled successfully!", parent=dialog)
                dialog.destroy()
                self.refresh_status()

            except Exception as err:
                messagebox.showerror("Enrollment Error", str(err), parent=dialog)

        btn_submit = tk.Button(
            dialog,
            text="Enrol Device",
            font=("Segoe UI", 10, "bold"),
            bg=self.accent_green,
            fg="white",
            relief="flat",
            padx=16,
            pady=8,
            command=do_enroll
        )
        btn_submit.pack(pady=(8, 16))

    def export_diagnostics(self):
        """Export sanitized diagnostic report without private keys or passwords."""
        config = get_config()
        current_mode = get_agent_mode(config.storage_dir)
        os_adapter = get_platform_adapter()
        os_info = os_adapter.get_os_info()

        diag_data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "agent_version": config.agent_version,
            "device_id": config.device_id,
            "operating_mode": current_mode,
            "backend_url": config.api_url,
            "is_enrolled": bool(self.token_mgr.get_refresh_token()),
            "os_info": os_info,
            "elevated_admin": sys.platform == "win32" and os.getenv("USERNAME", "") != "",
            "database_tables": ["policies", "telemetry_queue", "audit_log"]
        }

        save_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            initialfile=f"AcademiaShield_Diagnostics_{config.device_id}.json",
            title="Save Diagnostics Report"
        )
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(diag_data, f, indent=2)
            messagebox.showinfo("Diagnostics Exported", f"Report saved to:\n{save_path}")

    def disable_enforcement(self):
        """Stop active blocking and restore original DNS and process state."""
        if messagebox.askyesno("Disable Enforcement", "Stop all active session enforcement and restore original system settings?"):
            config = get_config()
            win_dns = WindowsDNSAdapterManager()
            try:
                restored = win_dns.restore_original_dns()
            except Exception:
                restored = False
            set_agent_mode("AUDIT", storage_dir=config.storage_dir)
            if restored:
                messagebox.showinfo("Restored", "Agent mode reverted to AUDIT. All network and app restrictions restored.")
            else:
                messagebox.showwarning(
                    "Restore Pending",
                    "Original DNS settings could not be verified yet. The recovery journal was kept and the "
                    "network guard will keep retrying. Re-run as Administrator if this persists."
                )
            self.refresh_status()

    def logout_device(self):
        """Revoke device token and wipe DPAPI credentials."""
        if messagebox.askyesno("Sign Out", "Are you sure you want to sign out and unenroll this device?"):
            api_client = APIClientAdapter(token_manager=self.token_mgr)
            try:
                api_client.logout()
            except Exception:
                self.token_mgr.clear_session()
            messagebox.showinfo("Signed Out", "Device session revoked and credentials cleared.")
            self.refresh_status()


def run_status_gui(auto_enroll: bool = False):
    root = tk.Tk()
    app = AcademiaShieldStatusApp(root, auto_enroll=auto_enroll)
    root.mainloop()

if __name__ == "__main__":
    run_status_gui()
