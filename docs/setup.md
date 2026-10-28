# Academia Shield - Setup & Development Guide

This guide describes how to run the Academia Shield workspace (frontend, backend, agent, database).

## Project Structure

```text
.
├── frontend/    # React + TypeScript + Vite SPA
├── backend/     # FastAPI + PostgreSQL + SQLAlchemy + Alembic
│   ├── app/     # Application logic & API routers
│   ├── tests/   # pytest backend suite
│   └── alembic/ # Database migration scripts
├── agent/       # Python desktop client agent
└── docs/        # Architectural & developer documentation
```

## Quick Start Guide

### 1. Backend Setup (FastAPI)

1. Change directory to `backend/`:
   ```bash
   cd backend
   ```

2. Create `.env` file from template:
   ```bash
   cp .env.example .env
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run database migrations:
   ```bash
   alembic -c alembic.ini upgrade head
   ```

5. Start backend development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

6. Verify backend health endpoint:
   - Visit: `http://localhost:8000/api/v1/health` or `http://localhost:8000/health`

---

### 2. Frontend Setup (React + TypeScript)

1. Change directory to `frontend/`:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start dev server:
   ```bash
   npm run dev
   ```

4. Open browser at `http://localhost:5173`.

---

### 3. Local PostgreSQL Setup (Optional)

If running PostgreSQL locally:
1. Ensure PostgreSQL service is running on port 5432.
2. Create database: `CREATE DATABASE academia_shield;`
3. Update `.env` in `backend/`:
   ```env
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=yourpassword
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=academia_shield
   ```
4. Run `alembic upgrade head`.

*(Note: SQLite fallback `sqlite:///./academia_shield_v2.db` works out of the box for quick local testing if PostgreSQL is not installed.)*
