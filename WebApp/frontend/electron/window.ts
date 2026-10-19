import { BrowserWindow } from 'electron'
import { join } from 'path'
import { APP_ORIGIN } from './protocol'

export function createWindow(isDev: boolean) {
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
    win.loadURL(`${APP_ORIGIN}/index.html`)
  }
}
