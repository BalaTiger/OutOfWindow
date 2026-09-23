const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('migrationExport', {
  write: (name, bytes, append = false) => ipcRenderer.invoke('migration:write', name, bytes, append),
});
