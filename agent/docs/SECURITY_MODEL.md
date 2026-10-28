# Academia Shield Security Model & Guarantees

## Core Philosophy

Academia Shield Local Agent is built on the principle of **consent-based, auditable, and safe endpoint management**.

> [!IMPORTANT]
> **What Academia Shield Will NEVER Do:**
> - No stealth background installation
> - No hidden persistence
> - No keystroke logging (keylogging)
> - No background screen recording or screenshot scraping
> - No browser history harvesting
> - No arbitrary remote shell or remote command execution
> - No silent privilege escalation
> - No third-party custom kernel drivers
> - No persistent, irreversible system modifications

---

## Cryptographic Guarantees

### 1. Ed25519 Device Identity
- When a device enrolls, the agent generates an Ed25519 asymmetric key-pair locally using `cryptography`.
- The **private key never leaves the local device**. It is stored in OS-protected secure storage:
  - **Windows**: Windows Credential Manager / DPAPI
  - **macOS**: macOS Keychain Services
- Only the **public key** is transmitted to the backend database.

### 2. Signed Policy & Clock-Skew Verification
- Policies are cryptographically verified via canonical SHA-256 integrity hashes and backend Ed25519 digital signatures.
- Device clock skew is strictly checked against `server_time_utc`. If skew exceeds **120 seconds**, the policy is rejected to prevent replay or temporal bypass attacks.

### 3. Idempotent Offline Telemetry
- Every telemetry event is assigned a globally unique UUID4 `event_id`.
- If the agent loses network connectivity during a session, events buffer into a bounded local SQLite FIFO queue.
- Upon reconnection, events are submitted in idempotent batches; duplicate event submissions are safely de-duplicated by the backend without double-counting violations.

---

## Safety & Automatic Policy Restoration

Whenever any of the following occur:
- Scheduled session finishes
- Student leaves session (`agent.cli leave-session`)
- Student or admin runs `disable-enforcement`
- Agent crashes, terminates, or enters `ERROR`
- Agent is uninstalled

The agent executes the **Restoration Routine**:
1. Reverts adapter DNS strictly back to the pre-enforcement backup configuration (or DHCP).
2. Releases process inspection monitors.
3. Records a tamper-evident audit entry in `local_audit_log`.
4. Emits a `policy_restored` event to backend telemetry.
