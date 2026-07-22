# Academia Shield — Deployment Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Vercel (Frontend)                       │
│             https://academia-shield.vercel.app               │
│              React SPA + Socket.IO Client                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                    REST + WebSocket
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   Render (Backend)                          │
│          https://academia-shield-api.onrender.com           │
│         Express API + Socket.IO + MongoDB Driver            │
└────────────────────────┬────────────────────────────────────┘
                         │
                    Database Connection
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  MongoDB Atlas (Cloud)                       │
│            mongodb+srv://user:pass@cluster.mongodb.net       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│           Student Machines (Python Agent)                    │
│  • Polls API every 30 seconds: GET /api/agent/config        │
│  • Reports activity: POST /api/agent/report                 │
│  • Modifies OS hosts file to enforce policies               │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1: Prepare Environment Files

### Frontend (.env.production)
Location: `apps/web/.env.production`
```env
VITE_API_URL=https://academia-shield-api.onrender.com
VITE_GEMINI_API_KEY=optional-gemini-api-key
```

### Backend (.env.production)
Location: `apps/api/.env.production`
```env
NODE_ENV=production
PORT=5000
MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@cluster.mongodb.net/academia-shield?retryWrites=true&w=majority
JWT_SECRET=your-very-secure-jwt-secret-min-32-chars
EMAIL_USER=your-email@gmail.com
EMAIL_PASS=your-app-password
FRONTEND_URL=https://academia-shield.vercel.app
```

### Agent (.env.production)
Location: `services/agent/.env.production`
```env
TEST_MODE=false
API_URL=https://academia-shield-api.onrender.com
POLL_INTERVAL=30
REQUEST_TIMEOUT=10
RETRY_ATTEMPTS=5
ENFORCEMENT_MODE=HOSTS
SOCKET_ENABLED=false
STUDENT_SAP_ID=
```

---

## Step 2: Deploy to Render (Backend)

### Option A: Using render.yaml (Recommended)

1. Commit `render.yaml` to your repository
2. Go to [render.com](https://render.com)
3. Click **New → Blueprint**
4. Select your GitHub repository
5. Render will auto-detect and deploy from `render.yaml`

### Option B: Manual Deployment

1. Go to [render.com](https://render.com) → **New → Web Service**
2. **Configuration:**
   - **Name:** `academia-shield-api`
   - **Environment:** `Node`
   - **Build Command:** `npm install && npm run build`
   - **Start Command:** `cd apps/api && npm start`
   - **Instance Type:** Free (upgradeable)

3. **Set Environment Variables:**
   - Copy all vars from `.env.production` to Render dashboard
   - Save and deploy

4. **Get API URL:** `https://academia-shield-api.onrender.com`

---

## Step 3: Deploy to Vercel (Frontend)

1. Go to [vercel.com](https://vercel.com) → **Add New → Project**
2. Import your GitHub repository
3. **Build Settings:**
   - **Framework:** Vite
   - **Build Command:** `npm run build -w @academia-shield/web`
   - **Output Directory:** `apps/web/dist`

4. **Environment Variables:**
   - Add `VITE_API_URL=https://academia-shield-api.onrender.com`

5. Deploy! You'll get `https://your-project.vercel.app`

6. **Update Backend CORS:**
   - Go back to Render → Set `FRONTEND_URL=https://your-vercel-app.vercel.app`
   - Manually redeploy

---

## Step 4: Distribute Python Agent to Students

### Option 1: Direct Python Script (Simplest)
```bash
cd services/agent
# Copy .env.production to .env and distribute both files
python agent.py
```

### Option 2: PyInstaller Executable (Windows)
```bash
cd services/agent
pip install pyinstaller

# Create single executable
pyinstaller --onefile --windowed agent.py

# Output: dist/agent.exe
```

### Option 3: Batch Installer (Windows Service)
Update and share `services/agent/install_windows.bat`

---

## Step 5: Verify Deployment

### Test API Health
```bash
curl https://academia-shield-api.onrender.com
# Should return: "Academia Shield API is running..."
```

### Test Frontend
Open `https://your-vercel-app.vercel.app` in browser

### Test Agent Connection
```bash
NODE_ENV=production python services/agent/agent.py
# Should log: "Config fetched successfully"
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Vercel build fails** | Check `npm run build -w @academia-shield/web` locally |
| **CORS errors** | Ensure `FRONTEND_URL` env var is set on Render |
| **WebSocket timeouts** | Render free tier may drop idle connections; upgrade to paid |
| **Agent can't reach API** | Check `API_URL` in agent `.env.production` |
| **MongoDB connection limit** | Atlas free tier = 3 connections; upgrade if needed |

---

## Performance Tips

1. **Render Paid Plans** — Free tier sleeps after 15 min; upgrade to avoid cold starts
2. **MongoDB Indexes** — Ensure indexes on `sessionId`, `studentId` for fast queries
3. **WebSocket Heartbeat** — Add ping/pong to keep connection alive
4. **Agent Caching** — Agent caches last config locally; offline-first design

---

## File Structure Post-Deployment

```
IPD---Academia-Shield/
├── render.yaml              ← Render deployment config
├── apps/
│   ├── api/
│   │   ├── .env.production  ← Backend secrets (NOT in git)
│   │   └── ...
│   └── web/
│       ├── .env.production  ← Frontend config
│       ├── vercel.json      ← Vercel settings
│       └── ...
└── services/agent/
    ├── .env.production      ← Agent config (NOT in git)
    ├── .env.development     ← For local testing
    └── agent.py
```

---

**Next Steps:**
1. Update `.env.production` files with real credentials
2. Commit to GitHub
3. Push to Render & Vercel
4. Test the full flow: Login → Create Session → Agent connects

