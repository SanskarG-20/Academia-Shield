# Device-Bound Agent Security Remediation Design

## Goal

Replace the current global/shared-secret agent policy path with device-bound enrollment and policy delivery, protect Socket.IO telemetry, and make session and cached-policy expiry authoritative without changing unrelated product workflows.

## Scope

This design addresses the critical and high-severity findings from the 2026-08-24 audit only:

- policy isolation between students, batches, sessions, and devices;
- one-time device enrollment and revocation;
- Socket.IO authentication and room authorization;
- automatic session expiry;
- agent cached-policy expiry and fail-safe restoration;
- API authorization regressions directly affected by those changes.

No real credentials, live MongoDB database, real email service, Windows hosts file, or DNS configuration will be used in automated verification.

## Current-State Root Causes

1. `apps/api/src/controllers/agentController.ts` loads every `Active` session in `getAgentConfig`; the authenticated caller is not used for policy selection.
2. `services/agent/comms/http_client.py` authenticates with an optional global secret and asks for config using a hostname/device ID. Neither establishes a student/device binding.
3. `apps/api/src/services/socketService.ts` accepts anonymous sockets and permits unvalidated room joins.
4. `apps/api/src/controllers/sessionController.ts` has no authoritative expiry job; `Active` sessions remain active after `endTime`.
5. `services/agent/comms/http_client.py` returns a cached active policy during outages without a policy validity deadline.
6. `services/agent/agent.py` lets a browser-originated local pairing call set an SAP ID, but SAP ID is not an authenticated device identity and must not drive authorization.

## Architecture

### Identity boundaries

There are three identities with distinct credentials:

| Caller | Credential | Server-derived identity | Allowed purpose |
|---|---|---|---|
| Professor / student browser | Existing user JWT | `req.user` / socket user | User dashboard and role-authorized operations |
| Newly installed local agent | Short-lived one-time enrollment claim | Claim's `studentId` | Exchange once for a device credential |
| Enrolled agent | Random long-lived device credential | `Device` document resolved from credential hash | Config, reports, heartbeats, and agent socket channel |

The API never uses a submitted SAP ID, student ID, batch ID, session ID, domain list, or public device ID as proof of authorization. They may be parsed for request shaping only after the authenticated identity is resolved, but ownership and policy selection are derived from database state.

### Database schema changes

#### `Device` (new: `apps/api/src/models/Device.ts`)

```ts
{
  deviceId: string,                 // public random UUID, unique; never authorization
  credentialHash: string,           // SHA-256 hash of random server-issued credential
  studentId: ObjectId,              // current paired student; atomically replaced on re-pair
  enrolledAt: Date,
  lastSeenAt?: Date,
  revokedAt?: Date,
  createdAt: Date,
  updatedAt: Date
}
```

Indexes: `deviceId` unique; `credentialHash` unique; `{ studentId, revokedAt }` for targeted device notifications. `credentialHash` is the only long-lived credential value held by MongoDB. A revoked device remains retained for auditability but is denied immediately by authentication.

#### `EnrollmentClaim` (new: `apps/api/src/models/EnrollmentClaim.ts`)

```ts
{
  claimHash: string,                // SHA-256 hash; raw claim is never stored
  studentId: ObjectId,              // authenticated student that initiated pairing
  expiresAt: Date,                  // 5-minute TTL index
  usedAt?: Date,
  usedByDeviceId?: string,
  createdAt: Date,
  updatedAt: Date
}
```

The raw 256-bit claim exists only in the authenticated browser request/response and the loopback handoff to the local agent. It is not placed in `localStorage`, logs, or a persisted frontend state. Claim consumption uses one conditional atomic update: `usedAt` must be absent and `expiresAt` must be in the future. A used, expired, or absent claim is rejected.

`Session` does not need an additional field: `status`, `startTime`, and `endTime` are the authoritative lifecycle state. Expiry sets `status` to `Completed` and is idempotent.

## API Changes

### Enrollment endpoints

| Method and path | Caller | Behavior |
|---|---|---|
| `POST /api/agent/enrollment-claims` | Student JWT | Creates a five-minute one-time claim for the authenticated student and returns the raw claim once. |
| `POST /api/agent/enroll` | Unenrolled local agent | Atomically consumes the claim, creates or re-pairs the submitted public device ID, generates the device credential, stores only its hash, and returns `{ deviceId, deviceCredential }` directly to the agent. |

The consuming endpoint does not accept a student ID or SAP ID. Re-pairing the same `deviceId` atomically overwrites `Device.studentId`, clears any prior revocation only when a new valid claim is presented, and rotates the device credential; the previous student is no longer associated with that device.

### Enrolled-agent endpoints

`GET /api/agent/config`, `POST /api/agent/report`, and `POST /api/agent/heartbeat` use a replacement `deviceAuth` middleware. It resolves the credential from `Authorization: Device <credential>`, hashes it, loads a non-revoked device, and places only the resolved device document on `req.device`.

- Config derives `studentId` from `req.device.studentId`, then selects only sessions that are `Active`, unexpired, joined by that student, and accessible through that student's batches.
- Rule domains/applications are loaded only through those selected sessions. Client-provided policy domains never affect the returned policy.
- Activity and heartbeat attribution derive the student from `req.device`; their request bodies no longer contain trusted `sapId` or student identity fields.
- The response includes `issuedAt`, `expiresAt` (minimum selected session end time), `deviceId`, and session IDs. It never returns the device credential.
- An unpaired, revoked, missing, invalid, or expired-credential caller receives `401`; an enrolled device with no eligible session receives a valid inactive policy with an immediate/short expiry.

The browser will no longer poll or post to `/api/agent/*`. Its current `getAgentConfig` and `reportAgentHeartbeat` use will be removed, eliminating browser impersonation of an agent.

### Session ownership validation

`createSession` will verify that every referenced rule belongs to the requesting professor and every referenced batch belongs to the requesting professor before creating the session. The existing owner checks for status updates/deletion remain. An active-session deletion will emit the same targeted policy refresh as a normal end, so agents restore promptly and polling remains a fallback.

### Session expiration service

`apps/api/src/services/sessionExpiryService.ts` will expose an idempotent `expireOverdueSessions(now)` routine. It updates each `Active` session whose `endTime <= now` to `Completed` with a conditional database mutation, and invokes targeted policy-change notifications exactly for records transitioned by that invocation.

It runs:

1. after MongoDB connects at server startup;
2. on a fixed server interval;
3. before session list/policy reads that affect enforcement.

This layered approach tolerates a missed interval, a backend restart, delayed agent reconnection, and a professor browser closing. It supports overlapping sessions because eligible policies are merged only for the device's own multiple active sessions, and their policy expiry is the earliest end time.

## Frontend Enrollment Flow

The student browser remains responsible only for initiating an enrollment handoff:

1. After authenticated student login/dashboard load, call `POST /api/agent/enrollment-claims` with the existing JWT.
2. Immediately POST that one-time claim to `http://127.0.0.1:49494/enroll` from the approved Academia Shield origin.
3. The local agent exchanges the claim directly with the API and persists its own returned device credential.
4. The browser receives only a pairing success/failure status from the local agent; it neither sees nor stores the long-lived device credential.

The former `/identify` SAP-ID handoff is removed. Browser pages no longer request global agent config or submit agent heartbeats. Existing student session joining still uses the student JWT and the server verifies membership before changing `joinedStudentIds`.

## Agent Enrollment and Policy Flow

1. A newly installed agent starts without credentials and only exposes a loopback, origin-checked `/enroll` handoff endpoint.
2. It generates a public random `deviceId` if none has been persisted.
3. It sends the browser-delivered claim and its public device ID to `/api/agent/enroll`.
4. It receives a credential only on that agent-to-API connection. The API stores a SHA-256 hash; the agent stores the raw value in its data directory with restrictive file permissions/ACLs.
5. Every subsequent config/report/heartbeat/socket request uses the device credential. The agent never sends SAP ID as identity.
6. Successful re-enrollment replaces the local credential only after the API exchange succeeds; a failed exchange retains the current credential and policy state until normal expiry.

The installer does not write a global shared agent secret. A freshly installed agent is explicitly “un-enrolled” until paired with a student.

## Socket.IO Authentication and Authorization

### Handshake

`apps/api/src/services/socketService.ts` will use `io.use` authentication middleware:

- Browser presents its user JWT in `socket.auth.token` and is classified as professor or student.
- Agent presents its device credential in `socket.auth.deviceCredential` and is resolved as a non-revoked device.
- Missing, malformed, expired, or revoked credentials reject the connection.
- The server records a credential expiry time for JWT sockets and disconnects them at expiry. Reconnection with the old credential fails. The frontend disconnects its socket on logout and supplies the current JWT at creation.

### Rooms and event delivery

| Room/event | Server authorization |
|---|---|
| `join_session` | Professor only, and only for a session owned by that professor. |
| `join_live_logs` | Professor only; joins a private `professor:<id>` room. |
| Agent policy wakeup | Device is automatically joined to `device:<resolved-device-id>` only. |
| Student socket | No protected telemetry/log room is granted. |
| Student telemetry/logs | Emitted only to the owning professor's room and session-monitor room, never a global room. |

The server emits targeted `policy_changed` events to devices paired to students who already joined an affected session. This improves responsiveness; the authenticated config poll is still the authoritative fallback. No global `session_started`, global `session_ended`, or global `live_logs` broadcasts remain.

## Cached Policy Validity and Restoration

The normalized policy cache will contain and validate:

```json
{
  "deviceId": "public-device-id",
  "issuedAt": "ISO timestamp",
  "expiresAt": "ISO timestamp",
  "active": true,
  "sessionIds": ["..."],
  "blockedDomains": ["..."],
  "blockedApps": ["..."]
}
```

The agent accepts a cached active policy only if all fields are structurally valid, its device ID equals the enrolled local device ID, and the local time precedes `expiresAt`. A stale/invalid/mismatched policy is treated as inactive. During API or socket outages, the agent can enforce only until that explicit deadline; at or after it, it calls `restore_rules()` and reports no false success. Thus an outage cannot indefinitely lock a student device.

An expired configuration never survives a restart because startup evaluates cache validity before enforcement. An un-enrolled agent always restores any marker-owned hosts block / DNS redirect instead of applying cached rules.

## Hosts and DNS Restoration

The existing hosts engine keeps its marker-scoped strategy: back up before modifying, remove only the managed markers, and restore on normal shutdown. The remediation calls that same `restore_rules()` path on inactive, expired, malformed, wrong-device, unenrolled, or failed policy states.

The DNS engine keeps its existing backup/restore path and is likewise invoked on every safe-inactive state. Its current single-server restore limitation will be fixed by retaining and restoring the full DNS server list rather than only the first server. Tests mock enforcement engines; they never write the real hosts file, execute `netsh`, bind port 53, or alter DNS.

## Exact File-Level Change Map

### Create

- `apps/api/src/models/Device.ts` — enrolled device schema and indexes.
- `apps/api/src/models/EnrollmentClaim.ts` — short-lived, one-time enrollment claim schema and TTL index.
- `apps/api/src/middleware/deviceAuth.ts` — credential hash lookup and revoked-device rejection.
- `apps/api/src/services/agentPolicyService.ts` — database-derived policy selection and response construction.
- `apps/api/src/services/sessionExpiryService.ts` — idempotent automatic session completion.
- `apps/api/src/services/deviceNotificationService.ts` — targeted device policy-refresh Socket.IO notifications.
- `apps/api/src/services/__tests__/agentPolicyService.test.ts` — policy isolation and expired-session unit tests.
- `apps/api/src/services/__tests__/sessionExpiryService.test.ts` — idempotent expiry unit tests.
- `apps/api/src/services/__tests__/enrollmentService.test.ts` — one-time/expired/re-pair/revocation tests.
- `apps/api/src/services/__tests__/socketAuthorization.test.ts` — authenticated room authorization tests with fake sockets.
- `services/agent/credentials.py` — safe device ID/credential persistence with platform-specific permissions.
- `services/agent/tests/test_cached_policy.py` — cached policy validity, wrong-device, expiry, and no-real-enforcement tests.
- `services/agent/tests/test_enrollment.py` — enrollment handoff/request tests with mock HTTP.

### Modify

- `apps/api/src/models/Session.ts` — add indexes supporting status/end-time expiry queries if absent.
- `apps/api/src/routes/agentRoutes.ts` — split student-authenticated claim creation, unauthenticated one-time consume, and device-authenticated endpoints.
- `apps/api/src/controllers/agentController.ts` — enrollment handlers; remove global config selection; derive policy/report/telemetry identity from `req.device`.
- `apps/api/src/controllers/sessionController.ts` — validate referenced ownership, invoke expiry, and notify affected devices on start/end/delete/join.
- `apps/api/src/controllers/logController.ts` — require an authorized student session member for browser-created logs and preserve agent attribution through device auth.
- `apps/api/src/services/socketService.ts` — handshake auth, expiry disconnect, authorized rooms, targeted emissions.
- `apps/api/src/server.ts` — initialise the expiry service after DB startup and stop it gracefully.
- `apps/api/src/app.ts` — mount any router changes without loosening CORS/authentication.
- `apps/api/src/middleware/agentAuth.ts` — remove after all callers move to `deviceAuth`; no legacy unauthenticated fallback remains.
- `apps/api/src/utils/apiResponse.ts` and `apps/api/src/utils/generateToken.ts` — only if current response/JWT helpers need typed support for the above interfaces; avoid changing their external user-token behavior.
- `apps/api/package.json` — add safe `node:test` scripts using existing TypeScript tooling; no test database or secret values.
- `apps/web/src/lib/api.ts` — replace browser agent config/heartbeat helpers with enrollment-claim and loopback-enrollment helpers; keep user JWT headers only for user routes.
- `apps/web/src/lib/socket.ts` — supply user JWT at handshake and disconnect on logout.
- `apps/web/src/components/layout/Sidebar.tsx` — disconnect the authenticated socket and clear token during logout.
- `apps/web/src/pages/Dashboard.tsx`, `apps/web/src/pages/Sessions.tsx`, `apps/web/src/pages/StudentSession.tsx` — initiate enrollment after authenticated student state is loaded; remove browser agent policy/heartbeat impersonation and global policy display.
- `apps/web/src/pages/LiveLogs.tsx`, `apps/web/src/components/SessionLiveMonitorModal.tsx` — use authenticated, professor-authorized socket streams only.
- `services/agent/config.py` — remove shared-secret configuration; define credential and enrollment state paths.
- `services/agent/comms/http_client.py` — device-auth headers, enrollment exchange, issued/expiry metadata, and cache validity checks.
- `services/agent/comms/socket_client.py` and `services/agent/comms/__init__.py` — device-auth socket handshake and targeted policy-refresh event.
- `services/agent/agent.py` — replace `/identify` with claim-only `/enroll`, treat un-enrolled/expired config as restore, and use persisted device identity.
- `services/agent/enforcement/dns.py` — preserve all DNS servers in the backup/restore sequence.
- `services/agent/env_loader.py`, `services/agent/.env.development`, `services/agent/.env.production`, `apps/api/.env.example`, `render.yaml`, and `README.md` — remove/describe shared-secret deployment configuration and document the enrollment process without containing a secret.

### Preserve unchanged

- `services/agent/enforcement/hosts.py` keeps marker-scoped hosts management; only its existing API is called from new safe-inactive paths.
- Current user JWT authentication, professor/student login, batch join, rules CRUD, and UI layout remain in place unless directly affected above.
- The five pre-existing modified agent files remain preserved and will be incorporated only where required by this approved remediation.

## Test Strategy

### API/service tests (no database or secrets)

Use Node's built-in test runner and dependency-injected/fake repositories to verify:

1. A device for Student A receives only Student A's joined, batch-authorized, unexpired sessions and merged rules.
2. Device A cannot obtain Student B policy by submitting Student B identifiers.
3. A claim is consumed once, rejects a second consumption, and rejects after expiry.
4. A revoked credential and a replaced credential are rejected.
5. Re-enrolling a device updates only its current `studentId` and rotates the credential.
6. Overdue `Active` sessions transition exactly once; manual completion is not overwritten.
7. Professor/student/device Socket.IO handshakes reject missing/bad/expired credentials.
8. Room joins reject another professor's session, student telemetry access, and anonymous clients; allowed professor monitor joins work.
9. User route authorization still rejects cross-professor/cross-student actions, rule mutations by students, and unauthorized session/log access.

### Python tests (safe temporary state)

Use `unittest`, temporary directories, mock HTTP responses, and a fake enforcement engine to verify:

1. Expired, malformed, wrong-device, and un-enrolled cached policies resolve to inactive.
2. A valid cached policy remains usable only before `expiresAt`.
3. Expiry causes `restore_rules()` exactly once and no hosts/DNS system call is made.
4. Enrollment stores a credential in the temporary data directory and requests configuration using device authentication.
5. Agent restart with an expired cache restores instead of applying blocking.

### Repository checks

Run production builds, API tests, Python tests, static scans for obsolete shared-secret references and accidental credential logging, and the existing syntax checks. Do not claim real frontend-to-backend-to-MongoDB or agent system-enforcement behavior until a separate safe runtime test is authorized.

## Non-Goals and Limits

- This does not introduce enterprise PKI, mTLS, a new identity provider, or a fleet-management console.
- A device credential is still a bearer credential; local OS compromise can expose it. Restrictive storage/ACLs and revocation mitigate but do not eliminate that device-level threat.
- Browser policy visibility is intentionally reduced rather than exposing raw agent policy globally. Students see their eligible sessions through normal user APIs; professors see telemetry only for their own sessions.
- Existing direct client-side Gemini integration is outside the present security-remediation scope and remains separately documented as a risk.
