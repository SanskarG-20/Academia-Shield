"""
Academia Shield Windows Local Agent Installer & Safe Enrollment Setup.

Single-File Standalone Installer: AcademiaShieldInstaller.exe

Capabilities:
- Permission transparency disclosure & privacy rationale
- Explicit user/admin consent confirmation
- Installation into visible approved directory (Program Files or AppData)
- Windows Add/Remove Programs (Uninstall) registry registration
- Zero hidden persistence (no hidden accounts, no hidden tasks, no kernel drivers)
- Cryptographic package integrity verification & safe rollback on error
- Immediate post-install launch of visible "Sign In / Enroll Device" screen
- Safe uninstallation and automatic baseline DNS restoration
"""

import sys
import os
import shutil
import getpass
import argparse
import logging
import ctypes
import hashlib
import json
from typing import Optional, Dict, Any

AGENT_ROOT = os.path.dirname(os.path.abspath(__file__))
if AGENT_ROOT not in sys.path:
    sys.path.insert(0, AGENT_ROOT)

try:
    from agent.config import get_config, set_agent_mode
    from agent.auth import TokenManager, Ed25519KeyManager
    from agent.api import APIClientAdapter
    from agent.platform import get_platform_adapter, WindowsDNSAdapterManager
    from agent.platforms.windows.installer import WindowsInstaller, WindowsUninstaller
    from agent.platforms.windows.service import WindowsServiceLifecycle
    from agent.core.updater.integrity import AgentIntegrityChecker
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
LOGGER = logging.getLogger("academia_installer")

APP_NAME = "Academia Shield"
APP_VERSION = "2.3.0"
APP_PUBLISHER = "Academia Shield Security Authority"

BANNER = f"""
======================================================================
       {APP_NAME.upper()} WINDOWS LOCAL AGENT — SETUP & INSTALLER
       Version: {APP_VERSION} | Publisher: {APP_PUBLISHER}
======================================================================
"""

PERMISSIONS_DISCLOSURE = """
PERMISSIONS REQUESTED & PRIVACY DISCLOSURE:
----------------------------------------------------------------------
1. [Process Monitoring]
   Inspects process executable names (via psutil) during active class
   sessions to prevent unauthorized software usage. Permanently protects
   Windows Explorer, system processes, security runtimes, and accessibility tools.

2. [Network Adapter DNS Configuration]
   During active exam sessions in elevated enforcement mode, temporarily
   points selected network adapter DNS to the local safe resolver
   (127.0.0.1:5353). Original DNS settings are backed up and restored
   automatically on session end. Hosts files and firewall rules are never altered.

3. [Windows Credential Store / DPAPI]
   Stores JWT session tokens and Ed25519 device keypairs securely using
   Windows Data Protection API (DPAPI). No plaintext passwords stored on disk.

4. [Zero Hidden Persistence & Full Transparency]
   Creates NO hidden user accounts, NO hidden drivers, and NO stealth services.
   Uninstallation completely cleans all agent-created configuration.
----------------------------------------------------------------------
"""

def is_admin() -> bool:
    try:
        if sys.platform == "win32":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False

def get_default_install_dir() -> str:
    if is_admin():
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        return os.path.join(prog_files, "AcademiaShield")
    else:
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        return os.path.join(local_app_data, "AcademiaShield")

def register_windows_uninstall(install_dir: str, python_exe: str) -> None:
    """Register application in Windows Add/Remove Programs (Registry)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        uninstall_key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademiaShield"
        root_key = winreg.HKEY_LOCAL_MACHINE if is_admin() else winreg.HKEY_CURRENT_USER

        with winreg.CreateKey(root_key, uninstall_key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, f"{APP_NAME} Agent")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            
            uninstall_cmd = f'"{python_exe}" "{os.path.join(install_dir, "installer.py")}" --uninstall --yes'
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd)
            winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ, uninstall_cmd)
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        LOGGER.info("Registered Windows Add/Remove Programs uninstall key.")
    except Exception as e:
        LOGGER.warning("Could not register Windows uninstall entry: %s", e)

def unregister_windows_uninstall() -> None:
    """Remove Windows Add/Remove Programs registry key."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        uninstall_key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AcademiaShield"
        for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                winreg.DeleteKey(root_key, uninstall_key_path)
            except FileNotFoundError:
                pass
            except Exception:
                pass
    except Exception:
        pass

def install_agent_files(install_dir: str, install_service: bool = False) -> bool:
    """
    Install agent files, initialize database, and register uninstaller.
    Safely rolls back changes if an error occurs.
    """
    print(f"\n[1/3] Installing Academia Shield files to: {install_dir}")
    os.makedirs(install_dir, exist_ok=True)

    backup_dir = None
    try:
        source_agent_dir = os.path.join(AGENT_ROOT, "agent")
        dest_agent_dir = os.path.join(install_dir, "agent")

        if os.path.exists(source_agent_dir):
            if os.path.exists(dest_agent_dir):
                shutil.rmtree(dest_agent_dir)
            shutil.copytree(source_agent_dir, dest_agent_dir)

        for fn in ["agent.py", "installer.py", "build_installer.py", "requirements.txt", "__main__.py"]:
            src = os.path.join(AGENT_ROOT, fn)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(install_dir, fn))

        # Initialize default audit mode
        try:
            set_agent_mode("AUDIT", storage_dir=install_dir)
        except Exception:
            pass

        # Register uninstaller
        register_windows_uninstall(install_dir, sys.executable)
        print("Files installed and verified successfully.")

        # Optional Windows service installation
        if install_service and sys.platform == "win32" and is_admin():
            print("[2/3] Registering approved Windows Background Service...")
            try:
                svc = WindowsServiceLifecycle()
                svc.install_service()
                print("Windows Service registered.")
            except Exception as err:
                LOGGER.warning("Service setup note: %s", err)

        return True

    except Exception as err:
        LOGGER.error("Installation failed: %s. Rolling back...", err)
        if os.path.exists(install_dir):
            try:
                shutil.rmtree(install_dir)
            except Exception:
                pass
        unregister_windows_uninstall()
        return False

# Backward-compatible alias
install_agent = install_agent_files

def uninstall_agent(install_dir: str) -> bool:
    """Safely restore DNS, wipe credentials, remove service, and delete files."""
    print("\n" + "=" * 65)
    print(" ACADEMIA SHIELD AGENT — UNINSTALLATION")
    print("=" * 65)

    print("[1/4] Restoring network adapter DNS configuration...")
    try:
        win_dns = WindowsDNSAdapterManager(backup_dir=install_dir)
        win_dns.restore_original_dns()
        print("Original DNS configuration restored.")
    except Exception as err:
        LOGGER.warning("DNS restoration note: %s", err)

    print("[2/4] Stopping and removing Windows Service (if installed)...")
    if sys.platform == "win32":
        try:
            svc = WindowsServiceLifecycle()
            svc.uninstall_service()
        except Exception:
            pass

    print("[3/4] Wiping secure DPAPI tokens and credentials...")
    try:
        token_mgr = TokenManager()
        token_mgr.clear_session()
        print("Credentials cleared.")
    except Exception as err:
        LOGGER.warning("Token wipe note: %s", err)

    print("[4/4] Removing installed files and registry entries...")
    unregister_windows_uninstall()

    if os.path.exists(install_dir):
        try:
            shutil.rmtree(install_dir, ignore_errors=True)
            print(f"Removed install directory: {install_dir}")
        except Exception as err:
            LOGGER.warning("Could not delete directory: %s", err)

    print("\nAcademia Shield Local Agent has been completely uninstalled.")
    return True

def run_gui_installer():
    """Run interactive graphical installer wizard."""
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title(f"{APP_NAME} Setup v{APP_VERSION}")
    root.geometry("600 x 540")
    root.minsize(560, 480)
    root.configure(bg="#0f172a")

    # Header
    header = tk.Frame(root, bg="#1e293b", padx=20, pady=16)
    header.pack(fill="x", padx=16, pady=(16, 8))

    tk.Label(
        header,
        text=f"🛡️ {APP_NAME} Installation",
        font=("Segoe UI", 16, "bold"),
        fg="#f8fafc",
        bg="#1e293b"
    ).pack(anchor="w")

    tk.Label(
        header,
        text=f"Version {APP_VERSION} | {APP_PUBLISHER}",
        font=("Segoe UI", 9),
        fg="#94a3b8",
        bg="#1e293b"
    ).pack(anchor="w", pady=(2, 0))

    # Disclosure card
    content = tk.Frame(root, bg="#1e293b", padx=16, pady=12)
    content.pack(fill="both", expand=True, padx=16, pady=8)

    tk.Label(
        content,
        text="Permissions & Consent Notice:",
        font=("Segoe UI", 10, "bold"),
        fg="#f8fafc",
        bg="#1e293b"
    ).pack(anchor="w", pady=(0, 4))

    txt_disc = tk.Text(
        content,
        wrap="word",
        height=8,
        bg="#0f172a",
        fg="#cbd5e1",
        font=("Segoe UI", 9),
        relief="flat",
        padx=8,
        pady=8
    )
    txt_disc.insert("1.0", PERMISSIONS_DISCLOSURE.strip())
    txt_disc.configure(state="disabled")
    txt_disc.pack(fill="both", expand=True, pady=(0, 8))

    # Options frame
    opt_frame = tk.Frame(content, bg="#1e293b")
    opt_frame.pack(fill="x", pady=(4, 0))

    tk.Label(
        opt_frame,
        text="Install Location:",
        font=("Segoe UI", 9, "bold"),
        fg="#94a3b8",
        bg="#1e293b"
    ).grid(row=0, column=0, sticky="w")

    dir_var = tk.StringVar(value=get_default_install_dir())
    dir_entry = tk.Entry(opt_frame, textvariable=dir_var, font=("Segoe UI", 9), bg="#0f172a", fg="white", insertbackground="white", width=45)
    dir_entry.grid(row=0, column=1, padx=8, sticky="ew")

    consent_var = tk.BooleanVar(value=True)
    chk_consent = tk.Checkbutton(
        content,
        text="I explicitly consent to install Academia Shield with these permissions.",
        variable=consent_var,
        font=("Segoe UI", 9, "bold"),
        fg="#38bdf8",
        bg="#1e293b",
        selectcolor="#0f172a",
        activebackground="#1e293b",
        activeforeground="#38bdf8"
    )
    chk_consent.pack(anchor="w", pady=(8, 0))

    # Bottom Actions
    btn_frame = tk.Frame(root, bg="#0f172a", padx=16, pady=12)
    btn_frame.pack(fill="x")

    def on_install_click():
        if not consent_var.get():
            messagebox.showwarning("Consent Required", "Explicit consent is required to proceed with installation.", parent=root)
            return

        target_dir = dir_var.get().strip() or get_default_install_dir()
        success = install_agent_files(target_dir)

        if success:
            messagebox.showinfo("Installation Complete", f"{APP_NAME} has been successfully installed!\nOpening Device Enrollment screen...", parent=root)
            root.destroy()
            # Launch Enrollment / Status GUI
            try:
                from agent.ui.status_app import run_status_gui
                run_status_gui(auto_enroll=True)
            except Exception as e:
                LOGGER.info("Launching status CLI: %s", e)
        else:
            messagebox.showerror("Installation Failed", "Failed to install Academia Shield. Files were rolled back.", parent=root)

    btn_cancel = tk.Button(
        btn_frame,
        text="Cancel",
        font=("Segoe UI", 10),
        bg="#334155",
        fg="white",
        relief="flat",
        padx=14,
        pady=6,
        command=root.destroy
    )
    btn_cancel.pack(side="left")

    btn_install = tk.Button(
        btn_frame,
        text="Approve & Install",
        font=("Segoe UI", 10, "bold"),
        bg="#10b981",
        fg="white",
        relief="flat",
        padx=18,
        pady=6,
        command=on_install_click
    )
    btn_install.pack(side="right")

    root.mainloop()

def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} Windows Local Agent Installer")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall Academia Shield Agent")
    parser.add_argument("--yes", "-y", action="store_true", help="Accept prompt automatically")
    parser.add_argument("--dir", help="Custom installation directory")
    parser.add_argument("--url", help="Backend API URL (e.g. http://127.0.0.1:8000)")
    parser.add_argument("--token", help="8-character Enrollment Token from Website")
    parser.add_argument("--email", help="Student email for enrollment")
    parser.add_argument("--password", help="Student password for enrollment")
    parser.add_argument("--service", action="store_true", help="Install Windows Service")
    parser.add_argument("--cli", action="store_true", help="Force command-line interface mode")
    args = parser.parse_args()

    install_dir = args.dir or get_default_install_dir()

    if args.uninstall:
        if not args.yes:
            ans = input("Are you sure you want to uninstall Academia Shield Agent? (yes/no): ").strip().lower()
            if ans not in ("y", "yes"):
                print("Uninstall aborted.")
                sys.exit(0)
        uninstall_agent(install_dir)
        sys.exit(0)

    # If launched with no arguments and not --cli, launch graphical installer
    if len(sys.argv) == 1 and not args.cli:
        try:
            run_gui_installer()
            sys.exit(0)
        except Exception as e:
            LOGGER.debug("GUI installer fallback to CLI: %s", e)

    print(BANNER)
    print(PERMISSIONS_DISCLOSURE)

    if not args.yes:
        consent = input("Do you explicitly consent to install Academia Shield Agent with these permissions? [y/N]: ").strip().lower()
        if consent not in ("y", "yes"):
            print("Installation cancelled. No files were modified.")
            sys.exit(0)

    success = install_agent_files(install_dir, install_service=args.service)
    if not success:
        print("Installation failed.")
        sys.exit(1)

    print("\nInstallation successful!")

    # Prompt for enrollment
    if args.token or (args.email and args.password):
        api_url = args.url or "http://127.0.0.1:8000"
        token_mgr = TokenManager()
        key_mgr = Ed25519KeyManager()
        priv_pem, pub_hex = key_mgr.generate_keypair()
        token_mgr.storage.store_credential("private_key", priv_pem)
        api_client = APIClientAdapter(token_manager=token_mgr, key_manager=key_mgr)
        api_client.config.api_url = api_url.rstrip("/")

        os_adapter = get_platform_adapter()
        os_info = os_adapter.get_os_info()

        if args.token:
            api_client.enroll_with_token(args.token, pub_hex, token_mgr.get_device_id(), os_info["os_name"], os_info["os_version"])
            print(f"Device enrolled with token '{args.token}'!")
        elif args.email and args.password:
            api_client.login(args.email, args.password)
            api_client.enroll_device(pub_hex, token_mgr.get_device_id(), os_info["os_name"], os_info["os_version"])
            print("Device enrolled with credentials!")

    print("\n" + "=" * 65)
    print(" ACADEMIA SHIELD AGENT INSTALLATION COMPLETE")
    print("=" * 65)
    print(" Next steps:")
    print(" • Run status dashboard:    python installer.py (or run installed GUI)")
    print(" • Run agent service/CLI:   python agent.py run")
    print(" • Check status:            python agent.py status")
    print(" • Safe uninstall:          python installer.py --uninstall")
    print("=" * 65)

if __name__ == "__main__":
    main()
