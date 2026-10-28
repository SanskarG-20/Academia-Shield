# Academia Shield Quality Assurance & Safety Test Plan

## 1. Scope
This document outlines the test suite and verification procedures for the Academia Shield classroom governance platform, covering Role-Based Access Control, session state machine, domain and application blocking, USB non-destructive restrictions, fail-safe watchdog auto-unblock, and student assistance workflows.

---

## 2. Test Matrix & Automated Test Suites

| Category | Test Suite File | Coverage Goal | Status |
| :--- | :--- | :--- | :--- |
| **Authentication & RBAC** | `backend/tests/test_auth.py` | Admin, Professor, Student access separation; token expiry; invalid credentials | ✅ Passed |
| **Session State Machine** | `backend/tests/test_sessions.py` | Create, Start, Pause, Resume, End; Quick Join by Code; batch enrollment | ✅ Passed |
| **Cryptographic Policy Signing** | `agent/tests/test_crypto_and_policy_verification.py` | Ed25519 signature validation; tampering detection; policy version ordering | ✅ Passed |
| **Domain Blocking Enforcement** | `agent/tests/test_blocking_enforcement.py` | Windows hosts file management; loopback mapping; DNS cache flushing | ✅ Passed |
| **Application Process Control** | `agent/tests/monitoring/test_process_monitor.py` | Target executable detection; safe termination; protected process safety list | ✅ Passed |
| **USB Storage Policy** | `agent/tests/test_safety_and_enforcement.py` | Windows GPO RemovableStorageDevices; USBSTOR service; input peripheral safety | ✅ Passed |
| **Fail-Safe Offline Recovery** | `agent/tests/test_state_machine_and_restoration.py` | 120s offline grace period trigger; automatic unblock; state cleanup | ✅ Passed |
| **End-to-End Reliability** | `backend/tests/test_e2e_security_reliability.py` | Full session lifecycle; telemetry ingestion; immutable audit logging | ✅ Passed |

---

## 3. Manual Safety & Verification Procedures

### Test Case 1: Fail-Safe Offline Grace Period
1. Start an active classroom session with `instagram.com` and `notepad.exe` blocked.
2. Verify that `instagram.com` cannot be loaded in the browser.
3. Disconnect student network adapter (or stop backend server).
4. **Expected Result**: After 120 seconds, the agent logs a fail-safe alert, restores the hosts file and DNS, and unblocks websites automatically.

### Test Case 2: USB Peripheral Safety
1. Start an active session with USB restriction enabled.
2. Insert a USB mass storage pen drive -> Verify access is denied.
3. Move USB mouse / type on USB keyboard.
4. **Expected Result**: Mouse and keyboard function completely uninterrupted with 0 latency.

### Test Case 3: Student Assistance / Unlock Workflow
1. Student clicks **"Request Assistance / Unlock"** in the workspace panel and submits a coursework exemption request.
2. Professor receives real-time notification on the dashboard and approves.
3. **Expected Result**: Audit log records approval and student is notified in real time.
