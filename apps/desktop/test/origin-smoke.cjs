// A local-only smoke test: no production API, credentials, agent, or hosts access.
const assert = require('node:assert/strict');
const http = require('node:http');
const { app, BrowserWindow, protocol } = require('electron');

protocol.registerSchemesAsPrivileged([
  { scheme: 'academia', privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

app.whenReady().then(async () => {
  let seenOrigin = '';
  const server = http.createServer((request, response) => {
    seenOrigin = String(request.headers.origin || '');
    response.writeHead(200, { 'Access-Control-Allow-Origin': seenOrigin });
    response.end('ok');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  protocol.handle('academia', () => new Response(
    `<script>window.probe = fetch('http://127.0.0.1:${port}/').then(r => r.text())</script>`,
    { headers: { 'content-type': 'text/html' } },
  ));
  const window = new BrowserWindow({ show: false, webPreferences: { sandbox: true, nodeIntegration: false, contextIsolation: true } });
  try {
    await window.loadURL('academia://academia-shield/index.html');
    assert.equal(await window.webContents.executeJavaScript('window.probe'), 'ok');
    assert.equal(seenOrigin, 'academia://academia-shield');
    console.log('Desktop origin smoke test passed');
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  } finally {
    window.destroy();
    server.close();
    app.quit();
  }
}).catch(error => { console.error(error); app.quit(); process.exitCode = 1; });
