# Academia Shield REST & Real-Time WebSocket API Specification

## 1. Authentication & Enrollment

### `POST /api/v1/auth/login`
Authenticate user identity with institutional credentials.
- **Request Body**: `{ "email": "professor@school.edu", "password": "password123" }`
- **Response**: `{ "access_token": "...", "refresh_token": "...", "user": { "id": "...", "role": "professor" } }`

### `POST /api/v1/agent/devices/enroll`
Enroll student endpoint using single-use enrollment token or active student session.
- **Request Body**:
  ```json
  {
    "enrollment_token": "ENROLL-A1B2C3",
    "device_name": "STUDENT-LAPTOP",
    "device_identifier": "LAPTOP-UH977J6D",
    "public_key": "3a8f... (Ed25519 hex)",
    "platform": "windows",
    "agent_version": "2.3.0"
  }
  ```

---

## 2. Session Management & Quick Join

### `POST /api/v1/batches/{batch_id}/sessions`
Create a new classroom session. Generates a unique 6-character session code (`CG-XXXXXX`).
- **Response**:
  ```json
  {
    "id": "8b99682c-54ea-46c5-9ced-4aeeb77e6e8b",
    "title": "Computer Networks Lab",
    "session_code": "CG-9F2K1A",
    "status": "scheduled",
    "is_active": false,
    "start_at_utc": "2026-08-20T10:00:00Z",
    "end_at_utc": "2026-08-20T12:00:00Z"
  }
  ```

### `POST /api/v1/sessions/join-by-code`
Student quick-joins a classroom session using the 6-character code.
- **Request Body**: `{ "session_code": "CG-9F2K1A" }`
- **Response**: `{ "id": "...", "title": "...", "is_joined": true, "status": "active" }`

### `POST /api/v1/sessions/{session_id}/pause` & `POST /api/v1/sessions/{session_id}/resume`
Temporarily suspend or resume policy enforcement during a class break.

---

## 3. Student Assistance & Unlock Requests

### `POST /api/v1/sessions/{session_id}/unlock-requests`
Student submits assistance or unlock request to the instructor.
- **Request Body**:
  ```json
  {
    "issue_type": "unlock_request",
    "description": "Need access to github.com for coursework submission."
  }
  ```

### `POST /api/v1/sessions/{session_id}/unlock-requests/{request_id}/resolve`
Instructor resolves or approves student request.
- **Request Body**: `{ "status": "approved", "resolution_notes": "Granted temporary allowance." }`

---

## 4. Policy Delivery & Telemetry

### `GET /api/v1/agent/policies/active`
Agent queries active signed policy bundle for the enrolled device.
- **Response**:
  ```json
  {
    "policy_active": true,
    "policy_version": 2,
    "rules": {
      "blocked_domains": ["instagram.com", "chatgpt.com"],
      "blocked_apps": ["notepad.exe", "discord.exe"],
      "usb_storage_restricted": true
    },
    "signature": "c8f1... (Ed25519 Signature)"
  }
  ```

### `POST /api/v1/agent/telemetry/events`
Batch upload privacy-minimized audit events and violation incidents.

---

## 5. IT Administrator Governance

### `GET /api/v1/admin/institution` & `PUT /api/v1/admin/institution`
Configure institutional policies: `allow_usb_blocking`, `fail_safe_grace_seconds`, `max_session_duration_minutes`.

### `GET /api/v1/admin/audit-logs`
Fetch queryable, immutable system audit logs for administrative compliance review.
