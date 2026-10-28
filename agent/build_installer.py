"""
Release Build Pipeline for Academia Shield Windows Installer Executable.

Produces:
dist/
  AcademiaShieldInstaller.exe
  AcademiaShieldInstaller.exe.sha256
  release-manifest.json
  release-manifest.sig

Steps:
1. Package agent source & modules into a single-file executable using PyInstaller.
2. Calculate SHA-256 package hash -> AcademiaShieldInstaller.exe.sha256
3. Generate signed release manifest -> release-manifest.json & release-manifest.sig
4. Authenticode digital code signing hook (if certificate available)
5. Deploy release to backend/installers/windows/ for direct download
"""

import sys
import os
import shutil
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any

AGENT_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(AGENT_ROOT)
DIST_DIR = os.path.join(AGENT_ROOT, "dist")
BUILD_DIR = os.path.join(AGENT_ROOT, "build")

# Import backend cryptographic signing if available
try:
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))
    from app.core.security import sign_release_manifest, get_server_public_key
except Exception:
    sign_release_manifest = None
    get_server_public_key = None

VERSION = "2.3.0"
PLATFORM_NAME = "windows"
MIN_OS = "Windows 10 Build 19041+ (x64 / ARM64)"

def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest().lower()

def sign_manifest_fallback(manifest_dict: Dict[str, Any]) -> str:
    """Fallback Ed25519 signing if backend module not directly loaded."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    seed = hashlib.sha256(b"ACADEMIA_SHIELD_SERVER_ED25519_production-jwt-secret-key-change-in-env-2026").digest()
    priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
    canonical = json.dumps({k: v for k, v in manifest_dict.items() if k != "signature"}, sort_keys=True).encode("utf-8")
    h = hashlib.sha256(canonical).hexdigest()
    return priv_key.sign(h.encode("utf-8")).hex()

def try_authenticode_sign(file_path: str) -> bool:
    """
    Attempt Authenticode code signing using signtool.exe or PowerShell Set-AuthenticodeSignature.
    Falls back gracefully if no code-signing certificate is installed.
    """
    if sys.platform != "win32":
        return False
    print("\n[Authenticode] Checking for code signing certificate...")
    # Check if a test/production certificate is available in Cert:\CurrentUser\My
    ps_cmd = f"""
    $cert = Get-ChildItem Cert:\\CurrentUser\\My -CodeSigningCert | Select-Object -First 1
    if ($cert) {{
        Set-AuthenticodeSignature -FilePath '{file_path}' -Certificate $cert -TimestampServer 'http://timestamp.digicert.com'
        Write-Output 'AUTHENTICODE_SIGNED'
    }} else {{
        Write-Output 'NO_CERTIFICATE_FOUND'
    }}
    """
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=15)
        if "AUTHENTICODE_SIGNED" in res.stdout:
            print("Authenticode digital signature applied successfully.")
            return True
        else:
            print("Notice: No Authenticode certificate in local certificate store. Code signing skipped.")
            return False
    except Exception as e:
        print(f"Authenticode signing check note: {e}")
        return False

def build():
    print("=" * 70)
    print(" ACADEMIA SHIELD WINDOWS INSTALLER RELEASE BUILD PIPELINE")
    print(f" Target Version: {VERSION} | Platform: {PLATFORM_NAME}")
    print("=" * 70)

    os.makedirs(DIST_DIR, exist_ok=True)
    os.makedirs(BUILD_DIR, exist_ok=True)

    # 1. Package AcademiaShieldInstaller.exe using PyInstaller
    installer_entry = os.path.join(AGENT_ROOT, "installer.py")
    agent_data_param = f"{os.path.join(AGENT_ROOT, 'agent')};agent"

    cmd_pyinstaller = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name", "AcademiaShieldInstaller",
        f"--add-data={agent_data_param}",
        "--paths", AGENT_ROOT,
        installer_entry
    ]

    print("\n[1/5] Compiling self-contained single-file installer...")
    print(f"Command: {' '.join(cmd_pyinstaller)}")
    subprocess.check_call(cmd_pyinstaller, cwd=AGENT_ROOT)

    installer_exe = os.path.join(DIST_DIR, "AcademiaShieldInstaller.exe")
    if not os.path.isfile(installer_exe):
        raise FileNotFoundError(f"Expected compiled binary not found at: {installer_exe}")

    exe_size_mb = os.path.getsize(installer_exe) / (1024 * 1024)
    print(f"Executable built: {installer_exe} ({exe_size_mb:.2f} MB)")

    # 2. Authenticode code signing hook
    print("\n[2/5] Authenticode Code Signing...")
    try_authenticode_sign(installer_exe)

    # 3. Compute SHA-256 package hash
    print("\n[3/5] Generating SHA-256 Package Hash...")
    pkg_hash = compute_sha256(installer_exe)
    hash_file = os.path.join(DIST_DIR, "AcademiaShieldInstaller.exe.sha256")
    with open(hash_file, "w", encoding="utf-8") as f:
        f.write(f"{pkg_hash} *AcademiaShieldInstaller.exe\n")
    print(f"SHA-256 Hash: {pkg_hash}")
    print(f"Saved: {hash_file}")

    # 4. Generate & Sign Release Manifest
    print("\n[4/5] Generating Signed Release Manifest...")
    download_url = f"http://127.0.0.1:8000/installers/windows/AcademiaShieldInstaller.exe"
    release_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_data = {
        "platform": PLATFORM_NAME,
        "version": VERSION,
        "download_url": download_url,
        "sha256": pkg_hash,
        "release_date": release_date,
        "min_os_version": MIN_OS
    }

    if sign_release_manifest:
        signature = sign_release_manifest(manifest_data)
    else:
        signature = sign_manifest_fallback(manifest_data)

    manifest_data["signature"] = signature

    manifest_json_path = os.path.join(DIST_DIR, "release-manifest.json")
    with open(manifest_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    sig_file_path = os.path.join(DIST_DIR, "release-manifest.sig")
    with open(sig_file_path, "w", encoding="utf-8") as f:
        f.write(signature)

    print(f"Release Manifest saved: {manifest_json_path}")
    print(f"Signature saved: {sig_file_path}")

    # 5. Deploy release to backend/installers/windows/ and root dist/
    print("\n[5/5] Deploying release to Backend Web Server & root dist/ directory...")
    backend_installers_win = os.path.join(PROJECT_ROOT, "backend", "installers", "windows")
    root_dist_dir = os.path.join(PROJECT_ROOT, "dist")
    os.makedirs(backend_installers_win, exist_ok=True)
    os.makedirs(root_dist_dir, exist_ok=True)

    for item in ["AcademiaShieldInstaller.exe", "AcademiaShieldInstaller.exe.sha256", "release-manifest.json", "release-manifest.sig"]:
        src = os.path.join(DIST_DIR, item)
        dst_backend = os.path.join(backend_installers_win, item)
        dst_root = os.path.join(root_dist_dir, item)
        shutil.copy2(src, dst_backend)
        shutil.copy2(src, dst_root)
        print(f" - Copied {item} -> {dst_backend} & {dst_root}")

    # Also keep versioned alias
    shutil.copy2(installer_exe, os.path.join(backend_installers_win, f"AcademiaShieldSetup-{VERSION}.exe"))

    print("\n" + "=" * 70)
    print(" RELEASE PIPELINE COMPLETED SUCCESSFULLY!")
    print(" Output directory: dist/")
    print(" - dist/AcademiaShieldInstaller.exe")
    print(" - dist/AcademiaShieldInstaller.exe.sha256")
    print(" - dist/release-manifest.json")
    print(" - dist/release-manifest.sig")
    print("=" * 70)

if __name__ == "__main__":
    build()
