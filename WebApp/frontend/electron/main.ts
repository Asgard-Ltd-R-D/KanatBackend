import { app, BrowserWindow, ipcMain } from 'electron'
import { join } from 'path'
import { GET_CONFIG } from './channels'
import { readConfig } from './config'
import { APP_ORIGIN, registerAppScheme, serveApp } from './protocol'

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

registerAppScheme()

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
    win.loadURL(`${APP_ORIGIN}/index.html`)
  }
}

app.whenReady().then(() => {
  const config = readConfig()

  ipcMain.on(GET_CONFIG, (event) => {
    event.returnValue = config
  })

  if (!isDev) serveApp(config)

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
