const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('outOfWindow', {
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  toggleClickThrough: () => ipcRenderer.send('window:toggle-click-through'),
  toggleDesktopMode: () => ipcRenderer.send('window:toggle-desktop-mode'),
  resizeWidget: (compact) => ipcRenderer.send('window:resize-widget', compact),
  onWindowState: (callback) => ipcRenderer.on('window:state', (_event, state) => callback(state)),
  onDesktopState: (callback) => ipcRenderer.on('desktop:state', (_event, state) => callback(state)),
  getLiveContext: () => ipcRenderer.invoke('world:live-context'),
});
