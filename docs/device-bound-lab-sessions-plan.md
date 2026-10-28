# Device-bound lab sessions implementation plan

**Goal:** Deliver professor-scheduled, batch-scoped website/application enforcement and student activity reporting through an enrolled local agent.

**Architecture:** Keep the current Express/MongoDB/React/Python stack. A one-time student claim enrolls an agent; a distinct device credential authenticates every subsequent agent request. Backend database state determines policy and telemetry scope. Backend and agent clocks each enforce expiry.

**Spec:** `docs/device-bound-lab-sessions-spec.md`

## Work sequence and exact files

### 1. Device and claim identity

Create `apps/api/src/models/Device.ts` and `apps/api/src/models/EnrollmentClaim.ts`. Create `apps/api/src/middleware/deviceAuth.ts` to parse a random device credential, hash it, find an active device, and attach its student ID. Create `apps/api/src/controllers/enrollmentController.ts` for student claim issue, one-use consumption, device list, and revocation. Modify `apps/api/src/routes/agentRoutes.ts` to apply student JWT to claim/device routes and device middleware to agent routes. Verify expired/used claims and revoked credentials are rejected using deterministic model mocks.

### 2. Server-derived policy and session clock

Create `apps/api/src/services/sessionClock.ts` for idempotent scheduled start and end transitions. Create `apps/api/src/services/devicePolicy.ts` to query only sessions joined by the authenticated student in their batches, verify professor ownership of the selected rule, and return a device-bound response with a maximum five-minute expiry. Modify `apps/api/src/controllers/agentController.ts`, `apps/api/src/controllers/activityController.ts`, and `apps/api/src/controllers/sessionController.ts` to use device identity and reject out-of-window/unauthorized data. Modify `apps/api/src/models/Session.ts` only for lookup indexes. Modify `apps/api/src/server.ts` to run the clock at startup and periodically. Verify cross-student, cross-device, revoked, and expired policy paths.

### 3. Socket authentication

Modify `apps/api/src/services/socketService.ts` to authenticate browser JWT/device credentials on connect, authorize session and professor live-log rooms using `Session`/`Student`/`Device`, and remove client-originated telemetry broadcasts. Modify `apps/web/src/lib/socket.ts` and `services/agent/comms/socket_client.py` to send credentials in the handshake and rejoin on reconnect. Verify missing/invalid/expired credentials and arbitrary room requests are rejected.

### 4. Agent enrollment, expiry, enforcement

Create `services/agent/credentials.py` to store/load/delete device credentials via the OS credential store and `services/agent/enroll.py` for CLI claim exchange. Create `services/agent/enforcement/apps.py` for exact executable-name checks and normal GUI close requests with protected-process exclusions. Modify `services/agent/agent.py` to start un-enrolled, prompt for a claim with `enroll`, apply website/app policy, and restore on invalid/expired policy. Modify `services/agent/config.py`, `services/agent/comms/http_client.py`, `services/agent/enforcement/hosts.py`, `services/agent/enforcement/dns.py`, and `services/agent/requirements.txt` for device authentication, bounded cache, and safe restoration. Verify with temporary files and fake process/network adapters only. The later device-safety audit adds a recovery task and disables new DNS redirection.

### 5. Student flow and documentation

Modify `apps/web/src/lib/api.ts` to call browser overview and enrollment/device APIs; remove local `/identify` pairing. Modify `apps/web/src/pages/StudentSession.tsx` to display a one-time enrollment claim, device status, and revocation. Modify `README.md` with local installation and enrollment commands. Modify `apps/api/src/app.ts` for the needed headers and `apps/api/src/controllers/authController.ts` to prevent production OTP downgrade.

### 6. Verification

Create `apps/api/test/device-bound.test.js` and `services/agent/tests/test_device_policy.py`; add `apps/api/package.json` test command. Run API/web builds, unit/mocked tests, Python syntax checks, and a secrets/status review. Do not run live end-to-end tests or touch real Windows hosts/DNS during tests.

The final file-level record is in `docs/device-bound-lab-sessions-spec.md`. It also includes the batch/rule guards, local claim prompt, UI status text, and removal of the old shared-secret middleware and settings.
