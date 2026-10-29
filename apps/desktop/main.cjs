const { app, BrowserWindow, ipcMain, net, protocol, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const APP_ORIGIN = 'academia://academia-shield';
const AGENT_NAME = 'AcademiaShield.exe';
protocol.registerSchemesAsPrivileged([
  { scheme: 'academia', privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

function webRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'web')
    : path.resolve(__dirname, '../web/dist');
}

function installedAgent() {
  return path.join(process.env.ProgramData || 'C:\\ProgramData', 'AcademiaShield', AGENT_NAME);
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(`${APP_ORIGIN}/`)) {
      event.preventDefault();
      if (url === 'https://github.com/SanskarG-20/Academia-Shield/releases/tag/nightly') {
        void shell.openExternal(url);
      }
    }
  });
  void window.loadURL(`${APP_ORIGIN}/index.html`);
}

app.whenReady().then(() => {
  protocol.handle('academia', (request) => {
    const url = new URL(request.url);
    if (url.protocol !== 'academia:' || url.host !== 'academia-shield') {
      return new Response('Forbidden', { status: 403 });
    }
    const root = webRoot();
    const relative = decodeURIComponent(url.pathname).replace(/^\/+/, '') || 'index.html';
    const file = path.resolve(root, relative);
    if (file !== root && !file.startsWith(root + path.sep)) return new Response('Forbidden', { status: 403 });
    if (!fs.existsSync(file) || !fs.statSync(file).isFile()) return new Response('Not found', { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });

  ipcMain.handle('agent:enroll', async (event, claim) => {
    if (event.senderFrame?.url?.split('#')[0] !== `${APP_ORIGIN}/index.html`) {
      return { ok: false, error: 'Unauthorized desktop request' };
    }
    if (typeof claim !== 'string' || !/^[A-Za-z0-9_-]{32}$/.test(claim)) {
      return { ok: false, error: 'Invalid enrollment code' };
    }
    const agentPath = installedAgent();
    if (!fs.existsSync(agentPath)) return { ok: false, error: 'Agent is not installed on this computer' };
    return new Promise((resolve) => {
      const child = spawn(agentPath, ['enroll', '--stdin'], {
        windowsHide: true,
        stdio: ['pipe', 'ignore', 'ignore'],
      });
      const timer = setTimeout(() => child.kill(), 30_000);
      child.stdin.on('error', () => {});
      child.on('error', () => { clearTimeout(timer); resolve({ ok: false, error: 'Unable to launch the installed agent' }); });
      child.on('close', code => {
        clearTimeout(timer);
        resolve(code === 0
          ? { ok: true }
          : { ok: false, error: 'Enrollment failed or the code expired' });
      });
      child.stdin.end(`${claim}\n`);
    });
  });

  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
