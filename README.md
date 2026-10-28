# Academia Shield

Academic integrity monitoring platform for institution-owned or explicitly consented devices. Enforces policy-driven application and DNS restrictions during verified batch sessions with full transparency, no stealth behavior, and privacy-minimized telemetry.

## Architecture

```
frontend/     → React + TypeScript SPA
backend/      → FastAPI + PostgreSQL + SQLAlchemy + Alembic
agent/        → Python local desktop agent (Windows)
scripts/      → CI tooling
docs/         → Documentation
```

## Quick Start (Development)

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 15+

### Backend Setup

```bash
cd backend
cp .env.example .env                  # Edit with your PostgreSQL credentials
pip install -r requirements.txt
alembic upgrade head                  # Run database migrations
uvicorn app.main:app --reload         # Start on http://localhost:8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev                           # Start on http://localhost:5173
```

### Agent Setup & Single-File Installer

```bash
# Build standalone Windows installer executable (dist/AcademiaShieldInstaller.exe)
python agent/build_installer.py

# Run installer GUI
dist\AcademiaShieldInstaller.exe

# Or run via CLI
python -m agent.cli.main enroll --url http://localhost:8000 --email student@univ.edu --password <password>
python -m agent.cli.main run
```

For complete packaging, code signing, and testing details, see [docs/WINDOWS_INSTALLER_GUIDE.md](docs/WINDOWS_INSTALLER_GUIDE.md).

## Running Tests

```bash
# All test suites (backend + agent + security)
python scripts/run_ci_tests.py

# Individual suites
python -m pytest backend/tests/ -v
python -m pytest agent/tests/ -v
python -m pytest backend/tests/test_e2e_security_reliability.py -v
```

## Production Deployment

### HTTPS / TLS Configuration

> **All production deployments MUST use HTTPS.** Never expose the API over plain HTTP.

1. **Reverse Proxy (Recommended)**: Deploy behind Nginx or Caddy with a valid TLS certificate (Let's Encrypt or institutional CA).
2. **Environment Variables**:
   ```
   CORS_ORIGINS=https://yourdomain.edu
   JWT_SECRET=<cryptographically-random-256-bit-key>
   DATABASE_URL=postgresql://user:password@host:5432/academia_shield
   ```
3. **HSTS Header**: Configure `Strict-Transport-Security: max-age=31536000; includeSubDomains` in your reverse proxy.

### PostgreSQL Backup & Recovery

```bash
# Daily automated backup
pg_dump -U postgres -Fc academia_shield > /backups/academia_$(date +%Y%m%d).dump

# Point-in-time restore
pg_restore -U postgres -d academia_shield /backups/academia_20260812.dump
```

- Enable WAL archiving for continuous backup.
- Store backups encrypted and off-site.
- Test restore procedures quarterly.

### Database Migrations

```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Verify migration state
alembic current

# Generate new migration after model changes
alembic revision --autogenerate -m "description"
```

### Structured Logging & Secret Redaction

The backend uses `SecretRedactingFormatter` which automatically strips:
- Passwords (`password=...`)
- JWT tokens (`access_token=...`, `refresh_token=...`)
- Authorization headers (`Authorization: Bearer ...`)
- Database connection strings containing credentials

**Log configuration**:
```
LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR
```

Logs are written to stdout in structured format. In production, pipe to your log aggregator (ELK, Datadog, CloudWatch).

## Agent Administration

### Elevated DNS Configuration (Windows)

The DNS blocking engine runs on an unprivileged port (5353) by default. To redirect system DNS through the local resolver, an administrator must **explicitly** run:

```powershell
# Apply local DNS resolver (requires elevated admin prompt)
python -m agent.cli.main setup-dns

# Restore original DNS settings
python -m agent.cli.main setup-dns --restore

# Target a specific network adapter
python -m agent.cli.main setup-dns --adapter "Wi-Fi"
```

**Important**: DNS settings are automatically restored when:
- The batch session ends
- The agent stops or logs out
- The agent is uninstalled
- The administrator runs `--restore`

### Agent Uninstall

```bash
python -m agent.cli.main logout       # Revoke tokens, wipe local credentials
python -m agent.cli.main uninstall    # Remove all local agent data
```

This removes:
- Locally stored refresh tokens and device keys
- SQLite telemetry queue
- Cached policy data
- DNS configuration backups (after restoring originals)

## Security Guarantees

### What the agent NEVER does

- ❌ Keystroke logging or keylogging
- ❌ Screenshot capture or screen recording
- ❌ Browser content, history, or cookie inspection
- ❌ Process memory dumps or command-line argument capture
- ❌ File content scanning or window text extraction
- ❌ Silent/stealth DNS, firewall, registry, or hosts-file modifications
- ❌ Anti-debugging, anti-tamper, or hidden persistence
- ❌ Enforcement outside a verified active batch session

### What the agent DOES (with consent)

- ✅ Monitors running process names (executable name only) during active sessions
- ✅ Applies policy-driven DNS blocking for specific domains
- ✅ Logs privacy-minimized telemetry: PID, executable name, domain, action, timestamp
- ✅ Shows visible OS notifications before any enforcement action
- ✅ Provides grace period before graceful process termination
- ✅ Protects system-critical processes from termination (Explorer, security tools, accessibility tools)
- ✅ Disables all enforcement when session expires or policy becomes invalid

### Protected Processes (Never Terminated)

| Category | Examples |
|----------|---------|
| Windows Core | `explorer.exe`, `svchost.exe`, `csrss.exe`, `lsass.exe`, `winlogon.exe` |
| Security Tools | `MsMpEng.exe`, `SecurityHealthService.exe` |
| Accessibility | `narrator.exe`, `osk.exe`, `magnify.exe` |
| Agent | `academia_shield_agent.exe`, `python.exe` |

## Privacy Notice

Academia Shield is designed for use on **institution-owned or explicitly consented devices only**.

### Data Collected During Active Sessions

| Data Point | Purpose | Retention |
|-----------|---------|-----------|
| Executable name | Policy rule matching | Session duration + audit log |
| Domain name (DNS) | DNS policy enforcement | Session duration + audit log |
| PID | Process identification | Not persisted after session |
| Timestamp | Event ordering | Audit log retention policy |
| Device ID | Device enrollment | Until device unenrolled |

### Data NOT Collected

- No browsing history, URLs, or page content
- No file names, file contents, or document metadata
- No keystrokes, clipboard content, or input data
- No screenshots, camera, or microphone data
- No personal communications or messaging content
- No process command-line arguments or environment variables

### Student Rights

- Students can view their own telemetry events
- Students can unenroll their device at any time
- Students can request data deletion
- All monitoring is transparently disclosed before enrollment
- No enforcement occurs outside scheduled batch sessions

## API Documentation

When the backend is running, interactive API docs are available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Health Check**: `GET /api/v1/health`
