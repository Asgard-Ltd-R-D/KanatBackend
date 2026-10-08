import { app, BrowserWindow, ipcMain, session } from 'electron'
import { readFileSync } from 'fs'
import { join } from 'path'

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

function readApiUrl(): string {
  try {
    const cfg = JSON.parse(
      readFileSync(join(app.getPath('userData'), 'kanat-config.json'), 'utf8'),
    )
    if (typeof cfg.apiUrl === 'string') return cfg.apiUrl
  } catch {
    // no config file — use default
  }
  return 'http://localhost:8000'
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#020617',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: join(__dirname, 'preload.js'),
    },
    titleBarStyle: 'default',
    show: false,
  })

  win.once('ready-to-show', () => {
    win.show()
  })

  if (isDev) {
    win.loadURL('http://localhost:5173')
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadFile(join(__dirname, '../dist/index.html'))
  }
}

app.whenReady().then(() => {
  const apiUrl = readApiUrl()

  ipcMain.on('kanat-get-api-url', (event) => {
    event.returnValue = apiUrl
  })

  if (!isDev) {
    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          'Content-Security-Policy': [
            `default-src 'self' ${apiUrl} https://fonts.googleapis.com https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob:; script-src 'self' 'unsafe-eval'`,
          ],
        },
      })
    })
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
