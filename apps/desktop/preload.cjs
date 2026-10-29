const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('academiaDesktop', Object.freeze({
  enrollAgent: (claim) => ipcRenderer.invoke('agent:enroll', claim),
}));
