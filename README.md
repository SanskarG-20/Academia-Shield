# Academia Shield

**Academia Shield** is a classroom session and policy platform for educators. Professors define **rules** (domains and applications), organize **batches**, and run **sessions**. While a session is active, a lightweight **Python agent** on student machines polls the API and applies restrictions by updating the OS **hosts** file—giving you a practical demo of centralized policy with local enforcement.

---

## Table of contents

- [Repository layout](#repository-layout)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Running the stack](#running-the-stack)
- [Demo account](#demo-account)
- [Classroom / LAN setup](#classroom--lan-setup)
- [Python agent](#python-agent)
- [API overview](#api-overview)
- [Scripts](#scripts)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Roadmap](#roadmap)

---

## Repository layout

This repo is an **npm workspaces** monorepo:

```text
.
├── apps/
│   ├── web/                 # React + Vite + TypeScript SPA (`@academia-shield/web`)
│   │   ├── public/          # Static assets (served as-is)
│   │   ├── src/
│   │   │   ├── components/  # UI + layout
│   │   │   ├── pages/       # Route screens
│   │   │   ├── lib/         # API client and shared clients
│   │   │   ├── App.tsx
│   │   │   ├── main.tsx     # Entry (mounted from index.html)
│   │   │   ├── types.ts
│   │   │   └── constants.ts # Mock / demo data used by some views
│   │   ├── index.html
│   │   └── vite.config.ts
│   └── api/                 # Express + MongoDB API (`@academia-shield/api`)
│       └── src/             # routes, controllers, models, middleware, scripts
├── services/
│   └── agent/               # Python hosts-file agent (stdlib)
├── scripts/
│   └── demo/                # Optional API walkthrough script (`demo_flow.py`)
├── package.json             # Workspace root (orchestrates dev/build)
└── README.md
```

Install once at the **repository root**; dependencies for `apps/web` and `apps/api` are linked via workspaces.

---

## Features

- **Professor dashboard** — sessions, rules, batches, logs, and live monitoring (role-gated in the UI).
- **Student flows** — SAP ID + OTP email verification, profile and batch join paths.
- **Policy engine (server)** — active sessions within their time window drive merged block lists for the agent.
- **Desktop agent** — cross-platform Python (stdlib), configurable poll interval, hosts-file apply/remove with a tagged block section.
- **Optional AI** — session summaries can use the Google GenAI SDK when `GEMINI_API_KEY` is set in the frontend environment (see [Vite env](https://vitejs.dev/guide/env-and-mode.html)).

---

## Architecture

```mermaid
flowchart LR
  subgraph clients [Clients]
    WEB[React SPA]
    AGENT[Python agent]
  end
  subgraph server [Backend]
    API[Express API :5000]
  end
  DB[(MongoDB)]
  WEB -->|REST + JWT| API
  AGENT -->|GET /api/agent/config| API
  API --> DB
  AGENT --> HOSTS[OS hosts file]
```

**Control plane:** the web app talks to the API with JWTs for authenticated routes.  
**Enforcement plane:** the agent calls **unauthenticated** `GET /api/agent/config` on a timer, then adds or removes `0.0.0.0` (or equivalent) entries for listed domains.

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite 6, React Router 7, Tailwind CSS (CDN), Lucide, Recharts |
| Backend | Node.js, Express 4, TypeScript, Mongoose, Helmet, Morgan, CORS |
| Database | MongoDB (e.g. Atlas) |
| Auth | JWT (30-day expiry), bcrypt password hashing |
| Real-time | Socket.IO wired on the server (push-based blocking is a roadmap item) |
| Agent | Python 3, standard library only |

---

## Prerequisites

- **Node.js** 18+ and npm
- **MongoDB** connection string (Atlas or self-hosted)
- **Python 3** (for `services/agent/` and optional `scripts/demo/`)
- **Administrator / root** on student machines when running the agent (hosts file access)
- For student OTP email: SMTP-capable credentials (see `apps/api/.env.example`)

---

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/SanskarG-20/IPD---Academia-Shield.git
cd IPD---Academia-Shield

npm install
```

### 2. Environment files

Copy the API example and fill in real values:

```bash
cp apps/api/.env.example apps/api/.env
```

For optional Gemini features in the UI, copy the web example (or create `apps/web/.env`):

```bash
cp apps/web/.env.example apps/web/.env
# set GEMINI_API_KEY=...
```

### 3. Seed demo data

```bash
npm run seed
```

You should see output confirming the demo professor, rules, and a sample session.

### 4. Smoke-test the API

```bash
npm run dev:api
```

Open `http://localhost:5000/api/agent/config` — a typical idle response includes `blocking_active: false` and empty `domains` / `apps` arrays.

---

## Configuration

### Backend (`apps/api/.env`)

| Variable | Purpose |
| --- | --- |
| `MONGO_URI` | MongoDB connection string |
| `JWT_SECRET` | Secret for signing JWTs |
| `PORT` | API port (default `5000`) |
| `CLIENT_URL` | Allowed browser origin context (e.g. `http://localhost:3000`) |
| `EMAIL_*` | Nodemailer transport for student OTP emails |

Never commit `.env`. Use `apps/api/.env.example` as the template.

### Frontend API base URL

In **`apps/web/src/lib/api.ts`**, set `BASE_URL` to your API origin:

- Local: `http://localhost:5000`
- LAN / hotspot: `http://<professor-machine-ip>:5000`

### Agent

In **`services/agent/agent.py`**, set `SERVER_IP` (and optionally `SERVER_PORT`) to match the machine running the API.

---

## Running the stack

| Mode | Command | Notes |
| --- | --- | --- |
| API + Web (one terminal) | `npm run dev` | Runs API and Vite together via `concurrently` |
| API only | `npm run dev:api` | Default `PORT` from `apps/api/.env` (5000) |
| Web only | `npm run dev:web` | Vite — `apps/web/vite.config.ts`, port 3000 |
| Agent | `python services/agent/agent.py` | Use `sudo` (macOS/Linux) or elevated shell (Windows) |

Optional:

```bash
python scripts/demo/demo_flow.py
```

---

## Demo account

After `npm run seed`:

- **Email:** `demo@professor.com`  
- **Password:** `password123`
- **Student SAP ID:** `600000001234`
- **Student OTP (when `STUDENT_OTP_MODE=mock`):** `123456`

---

## Single-machine demo flow

Use this mode to test professor, student, and agent together on one laptop.

1. Start backend + frontend:

```bash
npm run dev
```

2. Seed demo records:

```bash
npm run seed
```

3. Open professor login in a normal browser window and sign in with `demo@professor.com / password123`.
4. Open student login in an Incognito/Private window and sign in with SAP ID `600000001234` and OTP `123456`.
5. Student joins class code `CE-SY-2024`.
6. Professor creates or opens a session and clicks **Start** so status becomes `Active`.
7. Run the local agent:

```bash
python services/agent/agent.py
```

8. Open `youtube.com` or `instagram.com` to verify block, then end session to verify unblock.

Notes:
- `TEST_MODE=true` in `apps/api/.env` allows local agent polling without strict device allowlisting.
- Use separate browser contexts (normal + incognito) to keep professor and student JWT/localStorage independent.

---

## Classroom / LAN setup

1. On the professor machine, note the hotspot or LAN IPv4 address (Windows: `ipconfig`; macOS: `ifconfig` / `ipconfig getifaddr en0`).
2. Set **`apps/web/src/lib/api.ts`** → `BASE_URL` to `http://<that-ip>:5000`.
3. Set **`services/agent/agent.py`** → `SERVER_IP` to the same IP.
4. Ensure the API is reachable from student devices (firewall rules as needed).

---

## Python agent

- **Poll interval:** 30 seconds by default (`POLL_INTERVAL` in `agent.py`).
- **Cache:** writes `last_config.json` when the server is unreachable so the last known policy can still be applied conservatively (see agent logs).
- **Hosts file:** uses a marker comment (e.g. `# academia-shield`) so blocks can be removed cleanly when sessions end.

---

## API overview

Base path: `/api`

| Area | Prefix | Auth |
| --- | --- | --- |
| Authentication | `/api/auth` | Mixed (login vs OTP) |
| Batches | `/api/batches` | JWT |
| Sessions | `/api/sessions` | JWT |
| Rules | `/api/rules` | JWT |
| Logs | `/api/logs` | JWT |
| Agent config | `/api/agent` | **None** (by design; protect at network layer if needed) |

Health: `GET /` on the API root returns a short status string.

---

## Scripts

### Workspace root (`package.json`)

| Script | Description |
| --- | --- |
| `npm run dev` | API + web in parallel |
| `npm run dev:api` | API only (`@academia-shield/api`) |
| `npm run dev:web` | Vite dev server (`@academia-shield/web`) |
| `npm run build` | Build web, then compile API to `apps/api/dist/` |
| `npm run build:web` / `npm run build:api` | Individual package builds |
| `npm run preview` | Preview Vite production build |
| `npm run seed` | Run `seedDemo.ts` in the API package |
| `npm run start:api` | Run compiled API (`node apps/api/dist/server.js` after `build:api`) |

### Per package

| Location | Typical commands |
| --- | --- |
| `apps/web` | `npm run dev`, `npm run build`, `npm run preview` |
| `apps/api` | `npm run dev`, `npm run build`, `npm start`, `npm run seed` |

---

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Agent `PermissionError` | Run elevated (Administrator / `sudo`). |
| Agent cannot reach server | `SERVER_IP`, firewall, and that the API is bound to `0.0.0.0` if accessing from other hosts. |
| Browser errors / failed fetches | `BASE_URL` in `apps/web/src/lib/api.ts` must match the API URL students and professors use. |
| MongoDB errors | `MONGO_URI`, Atlas IP allowlist, and cluster user permissions. |
| Port already in use | Change `PORT` in `apps/api/.env` and update clients accordingly. |
| Student OTP email fails in local demo | Set `STUDENT_OTP_MODE=mock` and use `MOCK_STUDENT_OTP` from `apps/api/.env`. |
| Professor/student sessions collide | Use normal window for professor and Incognito/Private window for student. |
| Session marked Active but agent shows standby | Ensure the session was started from UI and check `GET /api/agent/config` for `active: true`. |
| Blocked domain still opens | Flush DNS (`ipconfig /flushdns` on Windows) and retry in a fresh tab/private window. |

---

## Limitations

- **Hosts-based blocking** requires local admin rights and can be reversed by a user with sufficient privileges.
- **Polling latency** means enforcement updates are not instantaneous compared to a push model.
- **Agent endpoint** is public; treat network placement and segmentation accordingly for production.

---

## Roadmap

- DNS-level enforcement to reduce reliance on local admin.
- Push-based updates (e.g. WebSocket) to replace or complement polling.
- Browser extension and stronger application-level controls.
- Deeper analytics and optional AI-assisted anomaly detection.

---

## Contributing

Issues and pull requests are welcome. Please keep changes focused, match existing code style, and avoid committing secrets or local `.env` files.

---

## License

The workspace root `package.json` is **private**. Add a root `LICENSE` file if you intend to open-source the project.
