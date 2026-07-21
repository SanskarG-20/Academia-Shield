# ✅ Deployment Configuration Summary

Your **Academia Shield** project is now configured for production deployment on **Vercel + Render**. Here's what has been set up:

---

## 📁 Files Created/Updated

### Frontend Configuration
- ✅ `apps/web/.env.production` — Vercel environment variables
- ✅ `apps/web/.env.development` — Local development environment
- ✅ `apps/web/vercel.json` — Vercel deployment config
- ✅ `apps/web/src/lib/api.ts` — Updated to read `VITE_API_URL` from environment
- ✅ `apps/web/vite.config.ts` — Fixed environment variable loading

### Backend Configuration
- ✅ `apps/api/.env.production` — Render environment variables
- ✅ `apps/api/src/app.ts` — CORS configured for Vercel + localhost
- ✅ `apps/api/src/server.ts` — Socket.IO CORS configured for production
- ✅ `render.yaml` — Render deployment blueprint (git-based deployment)

### Agent Configuration
- ✅ `services/agent/.env.production` — Production agent config
- ✅ `services/agent/.env.development` — Development agent config
- ✅ `services/agent/agent.py` — Auto-loads environment files
- ✅ `services/agent/config.py` — Supports `API_URL` parsing + HTTPS
- ✅ `services/agent/comms/http_client.py` — HTTPS support added
- ✅ `services/agent/env_loader.py` — Helper for env file loading
- ✅ `services/agent/build_windows.bat` — PyInstaller build for Windows
- ✅ `services/agent/build_unix.sh` — PyInstaller build for macOS/Linux
- ✅ `services/agent/install_windows_service.bat` — Windows Service installer

### Documentation
- ✅ `DEPLOYMENT.md` — Complete deployment guide
- ✅ `DEPLOYMENT_CHECKLIST.md` — Step-by-step checklist
- ✅ `scripts/deploy-setup.js` — Interactive setup script

---

## 🚀 Quick Start

### 1. Fill in Secrets
Edit these files with your actual values:
```bash
apps/api/.env.production           # Add MongoDB URI, JWT secret, email
apps/web/.env.production           # Add Render API URL
services/agent/.env.production     # Add Render API URL
```

### 2. Build & Test Locally
```bash
npm install
npm run build
npm run seed              # Seed demo data
npm run dev              # Test locally
```

### 3. Deploy Backend to Render
**Option A: Git-based (automatic)**
- Push to GitHub
- Render detects `render.yaml` and deploys automatically

**Option B: Manual**
- Create new Web Service on Render
- Connect GitHub repo
- Set build/start commands from `render.yaml`

### 4. Deploy Frontend to Vercel
```bash
vercel               # Deploy using Vercel CLI
# Or use Vercel dashboard to import GitHub repo
```

### 5. Build & Distribute Agent
```bash
cd services/agent
build_windows.bat      # Creates dist/AcademiaShield.exe
# OR
bash build_unix.sh     # Creates dist/academia-shield-agent
```

---

## 🔌 Architecture

```
┌──────────────────────────────────────┐
│      Vercel (React Frontend)         │
│  https://your-app.vercel.app         │
└────────────┬─────────────────────────┘
             │ REST + WebSocket
             ↓
┌──────────────────────────────────────┐
│  Render (Express.js Backend)         │
│  https://api.onrender.com            │
└────────────┬─────────────────────────┘
             │ MongoDB Driver
             ↓
┌──────────────────────────────────────┐
│  MongoDB Atlas (Cloud Database)      │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│  Python Agent (Student Machines)     │
│  • Polls API every 30s               │
│  • Enforces policies (hosts file)    │
│  • Reports violations                │
└──────────────────────────────────────┘
```

---

## 🔐 Environment Variable Reference

### Backend (`apps/api/.env.production`)
| Variable | Example | Required |
|----------|---------|----------|
| `NODE_ENV` | `production` | ✅ |
| `PORT` | `5000` | ✅ |
| `MONGODB_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/db` | ✅ |
| `JWT_SECRET` | `your-32-char-secret-key` | ✅ |
| `FRONTEND_URL` | `https://your-app.vercel.app` | ✅ |
| `EMAIL_USER` | `your-email@gmail.com` | ❌ |
| `EMAIL_PASS` | `app-password` | ❌ |

### Frontend (`apps/web/.env.production`)
| Variable | Example | Required |
|----------|---------|----------|
| `VITE_API_URL` | `https://api.onrender.com` | ✅ |
| `VITE_GEMINI_API_KEY` | `your-key` | ❌ |

### Agent (`services/agent/.env.production`)
| Variable | Example | Required |
|----------|---------|----------|
| `API_URL` | `https://api.onrender.com` | ✅ |
| `TEST_MODE` | `false` | ✅ |
| `POLL_INTERVAL` | `30` | ✅ |
| `STUDENT_SAP_ID` | `SAP123456` | ❌ |

---

## ✨ Features Configured

- ✅ **CORS** — Frontend can call backend API
- ✅ **WebSocket** — Real-time live logs & telemetry
- ✅ **HTTPS** — Agent supports production HTTPS endpoints
- ✅ **Environment Management** — Separate dev/prod configs
- ✅ **Build Automation** — `npm` workspaces for monorepo
- ✅ **Service Distribution** — Windows Service installer included

---

## 📖 Resources

- 📄 [DEPLOYMENT.md](./DEPLOYMENT.md) — Complete guide
- ✅ [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md) — Verification steps
- 🛠️ [scripts/deploy-setup.js](./scripts/deploy-setup.js) — Auto setup tool

---

## ⚠️ Important Notes

1. **Never commit `.env.production` files** — Add to `.gitignore`
2. **Render free tier** — App sleeps after 15 min; consider upgrading
3. **MongoDB Atlas free** — Allows only 3 connections; monitor usage
4. **WebSocket** — May need heartbeat for long-lived connections on Render
5. **Agent Distribution** — PyInstaller executables are platform-specific

---

## 🎯 Next Steps

1. **Configure secrets** → Fill in `.env.production` files
2. **Test locally** → `npm run dev` and verify everything works
3. **Deploy backend** → Push to GitHub, Render auto-deploys
4. **Deploy frontend** → Import repo into Vercel
5. **Build agent** → Run `build_windows.bat` or `build_unix.sh`
6. **Verify** → Test login, create session, check live logs
7. **Distribute** → Share `.exe` or executable with students

---

**You're ready to deploy! 🚀**

Questions? Check [DEPLOYMENT.md](./DEPLOYMENT.md) or [README.md](./README.md)
