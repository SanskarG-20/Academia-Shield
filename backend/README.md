# Academia Shield Production Backend (FastAPI v2.1.0)

Production-oriented academic session monitoring and centralized policy platform API built with Python, FastAPI, PostgreSQL, SQLAlchemy ORM, Alembic migrations, Pydantic validation, JWT authentication with token rotation, and bcrypt password hashing.

---

## Prerequisites

- **Python**: 3.9+ (Python 3.10+ recommended)
- **PostgreSQL**: 14+ (or SQLite for local development/testing)
- **Pip**: `pip install -r requirements.txt`

---

## Environment Configuration

Copy `.env.example` to `.env` in the `backend/` directory:

```bash
cp .env.example .env
```

### Key Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL or SQLite connection string | `sqlite:///./academia_shield_v2.db` |
| `JWT_SECRET` | Secret key used for JWT signing (Min 32 characters in production) | `super_secret_jwt_key_...` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Short-lived access token TTL in minutes | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Rotating refresh token TTL in days | `30` |
| `CORS_ORIGINS` | JSON list or comma-separated allowed frontend origins | `["http://localhost:3000","http://localhost:5173"]` |
| `PORT` | API server listen port | `8000` |

---

## Database Migrations (Alembic)

Run database migrations to initialize tables and indexes:

```bash
# Run migrations up to head
alembic -c alembic.ini upgrade head

# Generate a new migration revision
alembic -c alembic.ini revision --autogenerate -m "description"
```

---

## Running Development Server

```bash
# Install dependencies
pip install -r requirements.txt

# Start FastAPI server with live reload
python app/main.py
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI documentation is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## Running Tests

```bash
# Run pytest test suite against isolated test database
python -m pytest tests
```

---

## Endpoint Summary (`/api/v1`)

### Authentication (`/api/v1/auth`)
- `POST /api/v1/auth/register` — Account registration (student, professor, admin).
- `POST /api/v1/auth/login` — Login with institutional credentials; issues access & refresh tokens.
- `POST /api/v1/auth/refresh` — Rotate refresh token and obtain new access token.
- `POST /api/v1/auth/logout` — Revoke device session refresh token.
- `GET /api/v1/auth/me` — Authenticated user profile.

### System & Server Time (`/api/v1/system`)
- `GET /api/v1/system/time` — Returns backend server timezone-aware UTC datetime and clock-skew tolerance (`120` seconds).

### Classes & Academic Sessions (`/api/v1/classes`, `/api/v1/sessions`)
- `POST /api/v1/classes` — Create class (Professor/Admin).
- `GET /api/v1/classes` — List enrolled or owned classes.
- `GET /api/v1/classes/{class_id}` — Get class details.
- `POST /api/v1/classes/{class_id}/students` — Enroll student in class.
- `DELETE /api/v1/classes/{class_id}/students/{student_id}` — Remove student.
- `POST /api/v1/classes/{class_id}/sessions` — Create scheduled session (supports `none`, `daily`, `weekly` recurrence).
- `GET /api/v1/classes/{class_id}/sessions` — List sessions for class.
- `GET /api/v1/sessions/{session_id}` — Get single session details.
- `PATCH /api/v1/sessions/{session_id}` — Update session parameters (Professor/Admin owner only).
- `POST /api/v1/sessions/{session_id}/start` — Start active session (increments policy version).
- `POST /api/v1/sessions/{session_id}/end` — End active session (increments policy version).
- `POST /api/v1/sessions/{session_id}/cancel` — Cancel active session (increments policy version).

### Policy Rule Sets (`/api/v1/classes/{class_id}/rule-sets`, `/api/v1/rule-sets`, `/api/v1/application-rules`)
- `POST /api/v1/classes/{class_id}/rule-sets` — Create policy rule set (SHA-256 integrity hash calculation).
- `POST /api/v1/rule-sets/{rule_set_id}/domain-rules` — Add domain rule (`block`, `allow`, `log`).
- `POST /api/v1/rule-sets/{rule_set_id}/application-rules` — Create application process rule (`log`, `warn`, `close`).
- `GET /api/v1/rule-sets/{rule_set_id}/application-rules` — List application rules for a rule set (Professor/Admin only).
- `PATCH /api/v1/application-rules/{rule_id}` — Update application rule parameters or enable/disable state.
- `DELETE /api/v1/application-rules/{rule_id}` — Delete application rule.

#### Allowed Enforcement Actions
- `log`: Log process events without taking visible user action.
- `warn`: Display an OS notification to the student warning that the application is restricted.
- `close`: Display notification and gracefully request application termination (requires non-protected target executable).

#### Protected Processes List
System-critical operating system processes, security tools, and agent runtimes cannot be targeted for `close` enforcement:
- `explorer.exe` (Windows Shell)
- `svchost.exe` (Service Host)
- `csrss.exe` (Client Server Runtime)
- `smss.exe` (Session Manager)
- `services.exe` (Services Control Manager)
- `lsass.exe` (Local Security Authority)
- `winlogon.exe` (Windows Logon)
- `systemd` (Linux Init)
- `python.exe` / `python` (Python Runtime / Agent)
- `academia_shield_agent.exe` (Academia Shield Local Agent)

### Agent API (`/api/v1/agent`)
- `POST /api/v1/agent/devices/register` — Register student device with Ed25519 public key.
- `POST /api/v1/agent/heartbeat` — Report agent health and active window telemetry.
- `GET /api/v1/agent/policies/active` — Fetch active session policy for authenticated student device.
- `POST /api/v1/agent/telemetry/events` — Batched telemetry event ingestion with idempotency (`event_id`).

### Professor Dashboard (`/api/v1/dashboard`)
- `GET /api/v1/dashboard/live` — Live telemetry overview of active classroom sessions.
- `GET /api/v1/dashboard/violations` — Historical policy violation audit trail.
- `GET /api/v1/dashboard/agent-status` — Enrolled agent device health list.

---

## Role Permissions Matrix

| Endpoint Area | Admin | Professor | Student | Agent |
| --- | :---: | :---: | :---: | :---: |
| Auth / Profile | Yes | Yes | Yes | Yes |
| Create/Manage Classes | Yes | Yes (Owned) | No | No |
| Create/Manage Sessions | Yes | Yes (Owned) | No | No |
| Create/Manage Rule Sets | Yes | Yes (Owned) | No | No |
| Register Agent Device | Yes | Yes | Yes | Yes |
| Fetch Active Policy | Yes | Yes | Yes (Enrolled) | Yes |
| Submit Telemetry | Yes | Yes | Yes | Yes |
| Dashboard & Audit Logs | Yes | Yes | No | No |

---

## Production Deployment & HTTPS Notes

- **Reverse Proxy**: Always deploy behind a reverse proxy (e.g. Nginx, Caddy, Traefik, or AWS ALB) terminating SSL/TLS certificates.
- **Strict Headers**: Enable `X-Forwarded-Proto` and `X-Forwarded-For` in your reverse proxy.
- **Production Secrets**: Set `JWT_SECRET` to a cryptographically secure random 64-character string and `SHOW_DOCS=false`.
