# Device-bound lab sessions: implementation specification

## Current repository and scope

`main` is the source of truth: Express/TypeScript and MongoDB in `apps/api`, React/Vite in `apps/web`, and the Python desktop agent in `services/agent`. The separate FastAPI stack on `harsh` is not merged. Existing professor login, batch-code joining, session forms, rules, and activity UI remain in place.

## User flow

1. A professor signs in with email and password, creates a batch, and shares its join code. A student signs in and joins that batch.
2. The professor creates a session with a start and end time, a batch, and a blocklist rule set containing blocked domains and exact executable names. The backend starts and completes the session from its clock, independently of any browser. A student explicitly joins an active session in a batch they belong to.
3. The student requests a ten-minute enrollment claim in the web app. The claim is shown to the student for manual entry in the local agent. The browser never receives a device credential. A fresh agent has no credential and cannot fetch policy. The claim is consumed atomically once.
4. The backend issues a unique random device credential. The agent stores it in the OS credential store. The backend stores only its SHA-256 hash. Re-pairing with an existing authenticated credential revokes its previous record and creates a new record for the new student. Student self-service can revoke their own device.
5. Each agent request authenticates with the device credential. Policy is derived from that device's student, active joined session, batch membership, professor-owned rule set, and current time. Agent-supplied student ID, SAP ID, batch ID, session ID, domains, and device ID are never accepted as authorization. The returned policy identifies the device and has `issuedAt` and `expiresAt`; expiry is no later than the session end or five minutes after issuance.
6. The agent applies only valid policies. On invalid, expired, revoked, or absent policy it removes its managed hosts entries, restores saved legacy DNS state, and stops application close requests and activity tracking. Offline cache has an explicit expiry and is accepted only for the same local credential and within its validity window. Reports and activity derive student/session on the server from the credential. Application rules request a normal close of matching user GUI windows and do not force-terminate processes.
7. Socket.IO authenticates the handshake. Session and live-log rooms contain peer telemetry and are restricted to the owning professor; agents join only their authenticated device room. Students cannot join peer telemetry rooms. Token expiry disconnects the socket; room joins recheck authorization.

## Database schema

- `Device`: `studentId` reference, `credentialHash` (unique), `createdAt`, `lastSeenAt`, `revokedAt`. The identifier is the MongoDB `_id`; it is a lookup key, never proof of identity. One active credential belongs to one student.
- `EnrollmentClaim`: `studentId` reference, `claimHash` (unique), `expiresAt`, `consumedAt`, `createdAt`. A TTL index deletes old records for hygiene; queries still check `expiresAt` and `consumedAt` explicitly.
- Existing `Session`, `Batch`, `Rule`, `ActivityEvent`, and `Log` schemas remain the authority for membership, schedule, rules, telemetry, and dashboard data. Add indexes only where policy lookup needs them.

## API

- `POST /api/agent/enrollment-claims` (student JWT): issue one claim, invalidating any outstanding claim for that student. Return the raw claim once.
- `POST /api/agent/enroll` (claim, optional old device credential): atomically consume claim and issue a new credential. Return the credential only to the local agent call.
- `GET /api/agent/devices` and `DELETE /api/agent/devices/:id` (student JWT): list/revoke own devices, without credential values.
- `GET /api/agent/config`, `POST /api/agent/report`, `POST /api/agent/heartbeat`, `POST /api/agent/activity` (device credential): return or write only for authenticated device identity.
- `GET /api/agent/overview` (user JWT): limited browser display data. It does not return device credentials or impersonate an agent.
- Existing session endpoints retain their public shape, with stronger ownership/membership checks and schedule reconciliation.
- `POST /api/logs` is removed: browser clients cannot forge agent activity. Browser students join through `/api/sessions/:id/join`; telemetry and enforcement reports require a device credential.

## Session expiration

At startup and every few seconds, the backend reconciles `Upcoming` sessions whose start is due and `Active` sessions whose end has passed. Updates are conditional, so repeated sweeps and restarts are idempotent. Every policy read also checks the time window; a delayed sweep cannot leak an expired policy. The agent independently checks expiry while offline. Manual completion and cancellation remain immediate.

## Restoration

The hosts engine owns a marker-delimited section and removes only that section during restoration, preserving unrelated hosts changes and original bytes. It refuses ambiguous markers or a hosts file without a final newline. Windows replacement uses an atomic API that preserves the original file's ACLs and attributes. New DNS redirection is disabled; legacy DNS backup recovery remains available. Startup cleanup checks both modes even if the configured engine changed; a failed cleanup stops new enforcement. A separate minute-based Windows recovery task restores settings after the cached policy expires if the main agent exits. Tests use temporary hosts paths and fake task/process/network adapters; no test edits real Windows network configuration.

## Exact file map

Create: `apps/api/src/models/Device.ts`, `apps/api/src/models/EnrollmentClaim.ts`, `apps/api/src/middleware/deviceAuth.ts`, `apps/api/src/services/devicePolicy.ts`, `apps/api/src/services/sessionClock.ts`, `apps/api/src/controllers/enrollmentController.ts`, `apps/api/test/device-bound.test.js`, `apps/web/src/components/DeviceEnrollmentPanel.tsx`, `services/agent/credentials.py`, `services/agent/enroll.py`, `services/agent/enforcement/apps.py`, `services/agent/tests/test_device_policy.py`.

Modify: `apps/api/.env.example`, `apps/api/src/app.ts`, `apps/api/src/server.ts`, `apps/api/src/routes/agentRoutes.ts`, `apps/api/src/routes/logRoutes.ts`, `apps/api/src/controllers/agentController.ts`, `apps/api/src/controllers/activityController.ts`, `apps/api/src/controllers/logController.ts`, `apps/api/src/controllers/ruleController.ts`, `apps/api/src/controllers/sessionController.ts`, `apps/api/src/services/socketService.ts`, `apps/api/src/controllers/authController.ts`, `apps/api/src/models/Session.ts`, `apps/api/package.json`, `apps/web/src/components/CreateSessionModal.tsx`, `apps/web/src/lib/api.ts`, `apps/web/src/lib/socket.ts`, `apps/web/src/pages/Dashboard.tsx`, `apps/web/src/pages/Rules.tsx`, `apps/web/src/pages/Sessions.tsx`, `apps/web/src/pages/StudentSession.tsx`, `services/agent/.env.development`, `services/agent/.env.production`, `services/agent/activity/base.py`, `services/agent/activity/windows.py`, `services/agent/agent.py`, `services/agent/config.py`, `services/agent/comms/http_client.py`, `services/agent/comms/socket_client.py`, `services/agent/env_loader.py`, `services/agent/logger.py`, `services/agent/requirements.txt`, `services/agent/enforcement/__init__.py`, `services/agent/enforcement/hosts.py`, `services/agent/enforcement/dns.py`, `README.md`.

Delete: `apps/api/src/middleware/agentAuth.ts`, which accepted a global shared secret or no credential.

Packaging: modify `.github/workflows/build-agent.yml` and `services/agent/AcademiaShield.spec` to bundle the enrollment/keyring modules and remove SAP-ID setup instructions from the release notes.

## Test strategy and limits

Use mocks and local fixtures, never real credentials. API tests cover cross-student and cross-device policy isolation, claim expiry and one-time consumption, revocation, unauthorized API/session access, Socket.IO connection/room authorization, and scheduled end. Python tests cover expired policy/cache rejection, app-process decisions, and restoration with temporary files and mock adapters. Build/typecheck and focused automated tests run without live professor-to-agent execution. Live end-to-end testing remains pending user authorization.
