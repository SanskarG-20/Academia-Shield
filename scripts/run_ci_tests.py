"""
Unified CI Test Runner for Academia Shield.

Runs all backend tests, agent tests, and security tests with non-zero exit on failure.

Usage:
    python scripts/run_ci_tests.py
"""

import subprocess
import sys
import os

import tempfile
import shutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.path.join(ROOT_DIR, ".pytest-runtime")
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"

def get_suites(temp_root: str):
    return [
        {
            "name": "Frontend Type Check",
            "cmd": [NPM_COMMAND, "run", "typecheck", "-w", "@academia-shield/web"],
            "cwd": ROOT_DIR,
        },
        {
            "name": "Backend Tests",
            "cmd": [
                sys.executable, "-m", "pytest", "backend/tests/", "-v", "--tb=short",
                "--basetemp", os.path.join(temp_root, "backend"),
            ],
            "cwd": ROOT_DIR
        },
        {
            "name": "Agent Tests",
            "cmd": [
                sys.executable, "-m", "pytest", "agent/tests/", "-v", "--tb=short",
                "--basetemp", os.path.join(temp_root, "agent"),
            ],
            "cwd": ROOT_DIR
        },
        {
            "name": "E2E Security & Reliability Tests",
            "cmd": [sys.executable, "-m", "pytest",
                    "backend/tests/test_e2e_security_reliability.py",
                    "backend/tests/test_security_redaction_and_migrations.py",
                    "-v", "--tb=short", "--basetemp", os.path.join(temp_root, "e2e")],
            "cwd": ROOT_DIR
        }
    ]

def run_suite(suite: dict, temp_root: str) -> bool:
    print(f"\n{'='*70}")
    print(f" Running: {suite['name']}")
    print(f"{'='*70}\n")
    test_env = os.environ.copy()
    # Keep temporary files inside the project so restricted runners do not
    # depend on a writable user-profile temp directory.
    test_env.update({"TMP": temp_root, "TEMP": temp_root, "TMPDIR": temp_root})
    result = subprocess.run(suite["cmd"], cwd=suite["cwd"], env=test_env)
    passed = result.returncode == 0
    status = "PASSED" if passed else "FAILED"
    print(f"\n  [{status}] {suite['name']}")
    return passed

def main():
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    temp_root = tempfile.mkdtemp(prefix="run_", dir=RUNTIME_DIR)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("=" * 70)
    print(" ACADEMIA SHIELD -- CI TEST RUNNER")
    print("=" * 70)

    suites = get_suites(temp_root)
    results = []
    try:
        for suite in suites:
            passed = run_suite(suite, temp_root)
            results.append((suite["name"], passed))
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    print(f"\n{'='*70}")
    print(" CI RESULTS SUMMARY")
    print(f"{'='*70}")
    all_passed = True
    for name, passed in results:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon}  {name}")
        if not passed:
            all_passed = False

    print(f"\n{'='*70}")
    if all_passed:
        print(" ALL SUITES PASSED")
        print(f"{'='*70}\n")
        sys.exit(0)
    else:
        print(" SOME SUITES FAILED")
        print(f"{'='*70}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
