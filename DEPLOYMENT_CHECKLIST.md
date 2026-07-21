# 📋 Quick Deployment Checklist

## Pre-Deployment

- [ ] All code committed to GitHub
- [ ] MongoDB Atlas account created & cluster ready
- [ ] Vercel account created
- [ ] Render account created

## Configuration

- [ ] `apps/api/.env.production` created with:
  - [ ] `MONGODB_URI` (from Atlas)
  - [ ] `JWT_SECRET` (32+ chars)
  - [ ] `FRONTEND_URL` (your Vercel URL)
  - [ ] `EMAIL_USER` & `EMAIL_PASS` (optional)

- [ ] `apps/web/.env.production` created with:
  - [ ] `VITE_API_URL` (your Render API URL)
  - [ ] `VITE_GEMINI_API_KEY` (optional)

- [ ] `services/agent/.env.production` created with:
  - [ ] `API_URL` (your Render API URL)
  - [ ] `POLL_INTERVAL=30` (production value)

- [ ] `.gitignore` updated to exclude `.env.production` files

## Render Deployment

- [ ] Create Render account
- [ ] Connect GitHub repository
- [ ] Deploy using `render.yaml` blueprint
  - [ ] Or manually create Web Service:
    - [ ] Build Command: `npm install && npm run build`
    - [ ] Start Command: `cd apps/api && npm start`
    - [ ] Set all environment variables

- [ ] Get API URL: `https://academia-shield-api.onrender.com`

## Vercel Deployment

- [ ] Create Vercel account
- [ ] Import GitHub repository
- [ ] Set build settings:
  - [ ] Build Command: `npm run build -w @academia-shield/web`
  - [ ] Output Directory: `apps/web/dist`
  - [ ] Environment Variable: `VITE_API_URL`

- [ ] Get Frontend URL: `https://your-project.vercel.app`

- [ ] Update Render `FRONTEND_URL` env var with Vercel URL
- [ ] Redeploy Render to update CORS

## Testing

- [ ] API Health Check: `curl https://academia-shield-api.onrender.com`
- [ ] Frontend loads: Open Vercel URL in browser
- [ ] Login works (test with demo account)
- [ ] Create session
- [ ] WebSocket connected (check browser console)
- [ ] Agent can fetch config: `python services/agent/agent.py`

## Agent Distribution

### Windows
- [ ] Run `cd services/agent && build_windows.bat`
- [ ] Creates `dist/AcademiaShield.exe`
- [ ] (Optional) Install as service: `install_windows_service.bat`

### macOS/Linux
- [ ] Run `cd services/agent && bash build_unix.sh`
- [ ] Creates `dist/academia-shield-agent`

## Post-Deployment

- [ ] Monitor Render logs for errors
- [ ] Test agent connection on student machine
- [ ] Verify live logs appear in professor dashboard
- [ ] Verify blocking works (hosts file updated)

## Performance

- [ ] Upgrade Render plan if cold starts are an issue
- [ ] Add MongoDB indexes for frequently queried fields
- [ ] Monitor WebSocket connections
- [ ] Review agent poll intervals for student load

---

**Final Verification:**
```bash
# Test API
curl -I https://academia-shield-api.onrender.com

# Test agent
NODE_ENV=production python services/agent/agent.py

# View Render logs
# From Render dashboard → Logs tab
```

✅ All done! Your Academia Shield is live!
