const { app, BrowserWindow, ipcMain, Menu, Tray, nativeImage, screen } = require('electron');
const path = require('path');
const fs = require('fs');

const runtimePath = path.join(__dirname, '..', '.runtime');
fs.mkdirSync(runtimePath, { recursive: true });
app.setPath('userData', runtimePath);
app.commandLine.appendSwitch('disk-cache-dir', path.join(runtimePath, 'cache'));

let mainWindow;
let tray;
let clickThrough = false;
let desktopMode = true;

function updateWindowMode() {
  if (!mainWindow) return;
  mainWindow.setAlwaysOnTop(desktopMode, desktopMode ? 'floating' : 'normal');
  mainWindow.setSkipTaskbar(desktopMode);
  mainWindow.setIgnoreMouseEvents(clickThrough, { forward: true });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1040,
    height: 690,
    minWidth: 760,
    minHeight: 510,
    frame: false,
    transparent: true,
    roundedCorners: false,
    hasShadow: false,
    show: false,
    backgroundColor: '#00000000',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) mainWindow.loadURL(devUrl);
  else mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  mainWindow.once('ready-to-show', () => {
    const workArea = screen.getPrimaryDisplay().workArea;
    const bounds = mainWindow.getBounds();
    mainWindow.setPosition(workArea.x + workArea.width - bounds.width - 26, workArea.y + workArea.height - bounds.height - 26);
    updateWindowMode();
    mainWindow.showInactive();
  });
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) { event.preventDefault(); mainWindow.hide(); }
  });
}

function createTray() {
  const icon = nativeImage.createFromDataURL('data:image/svg+xml;base64,' + Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" rx="7" fill="#18231f"/><path d="M6 6h20v20H6zM9 9v14h14V9zm6 0v14m-6-7h14" fill="none" stroke="#d6e7da" stroke-width="2"/></svg>`).toString('base64'));
  tray = new Tray(icon.resize({ width: 16, height: 16 }));
  tray.setToolTip('Out of Window · 桌面窗景');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '显示 / 隐藏窗景', click: () => mainWindow?.isVisible() ? mainWindow.hide() : mainWindow.showInactive() },
    { label: '鼠标穿透', type: 'checkbox', checked: clickThrough, click: (item) => { clickThrough = item.checked; updateWindowMode(); mainWindow?.webContents.send('desktop:state', { clickThrough, desktopMode }); } },
    { label: '桌面挂件模式', type: 'checkbox', checked: desktopMode, click: (item) => { desktopMode = item.checked; updateWindowMode(); mainWindow?.webContents.send('desktop:state', { clickThrough, desktopMode }); } },
    { type: 'separator' },
    { label: '退出', click: () => { app.isQuitting = true; app.quit(); } },
  ]));
  tray.on('click', () => mainWindow?.isVisible() ? mainWindow.hide() : mainWindow.showInactive());
}

app.whenReady().then(() => {
  createWindow();
  createTray();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => { app.isQuitting = true; });

ipcMain.on('window:minimize', () => mainWindow?.minimize());
ipcMain.on('window:maximize', () => mainWindow?.isMaximized() ? mainWindow.unmaximize() : mainWindow?.maximize());
ipcMain.on('window:close', () => mainWindow?.close());
ipcMain.on('window:toggle-click-through', () => {
  clickThrough = !clickThrough; updateWindowMode();
  mainWindow?.webContents.send('desktop:state', { clickThrough, desktopMode });
});
ipcMain.on('window:toggle-desktop-mode', () => {
  desktopMode = !desktopMode; updateWindowMode();
  mainWindow?.webContents.send('desktop:state', { clickThrough, desktopMode });
});
ipcMain.on('window:resize-widget', (_event, compact) => {
  if (!mainWindow) return;
  mainWindow.setSize(compact ? 760 : 1040, compact ? 510 : 690, true);
});

const weatherFallback = {
  location: { city: '上海', region: '上海', country: '中国', latitude: 31.23, longitude: 121.47, timezone: 'Asia/Shanghai' },
  weather: { temperature: 22, apparentTemperature: 22, weatherCode: 1, isDay: 0, precipitation: 0, cloudCover: 35, windSpeed: 8 },
  fallback: true,
};

async function fetchJson(url, timeout = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { signal: controller.signal, headers: { 'User-Agent': 'OutOfWindow/0.1' } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

ipcMain.handle('world:live-context', async () => {
  try {
    const geo = await fetchJson('https://ipwho.is/?fields=success,city,region,country,latitude,longitude,timezone');
    if (!geo.success || !Number.isFinite(geo.latitude)) throw new Error('IP geolocation unavailable');
    const params = new URLSearchParams({
      latitude: String(geo.latitude), longitude: String(geo.longitude),
      current: 'temperature_2m,apparent_temperature,is_day,precipitation,weather_code,cloud_cover,wind_speed_10m',
      timezone: 'auto', forecast_days: '1',
    });
    const forecast = await fetchJson(`https://api.open-meteo.com/v1/forecast?${params}`);
    const current = forecast.current;
    return {
      location: {
        city: geo.city || geo.region || geo.country,
        region: geo.region || '', country: geo.country || '',
        latitude: geo.latitude, longitude: geo.longitude,
        timezone: geo.timezone?.id || forecast.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
      },
      weather: {
        temperature: current.temperature_2m,
        apparentTemperature: current.apparent_temperature,
        weatherCode: current.weather_code,
        isDay: current.is_day,
        precipitation: current.precipitation,
        cloudCover: current.cloud_cover,
        windSpeed: current.wind_speed_10m,
      },
      fallback: false,
    };
  } catch (error) {
    return { ...weatherFallback, error: error.message };
  }
});
