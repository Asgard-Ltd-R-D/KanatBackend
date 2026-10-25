import { app, BrowserWindow, shell } from 'electron'
import { join } from 'path'
import { KanatConfig } from './config'
import { mainLog } from './logs'
import { APP_ORIGIN } from './protocol'

// The sidebar's logo (public/icon.svg, rendered to icon.png): Vite copies
// public/ into dist/ for the packaged app
export const APP_ICON = join(__dirname, app.isPackaged ? '../dist/icon.png' : '../public/icon.png')

const DEV_URL = 'http://localhost:5173'

export function createWindow(isDev: boolean, config: KanatConfig) {
  const win = new BrowserWindow({
    title: 'KANAT',
    icon: APP_ICON, // the window's and taskbar's, on Windows and Linux
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#1e1f22', // slate-950 (tailwind.config.ts): no flash before the page paints
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

  // A page that crashed or froze cannot log it itself
  win.webContents.on('render-process-gone', (_event, details) =>
    mainLog.error('The app window crashed', { reason: details.reason, exit_code: details.exitCode }),
  )
  win.on('unresponsive', () => mainLog.warning('The app window stopped responding'))
  win.on('responsive', () => mainLog.info('The app window responds again'))

  // A link that opens a window (an export, "Open in Grafana", a link inside
  // the embedded Grafana): an export is downloaded here, with a Save dialog;
  // any other web page opens in the browser, not in a bare app window that
  // would carry the app's preload
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(`${config.apiUrl}/`)) win.webContents.downloadURL(url)
    else if (/^https?:\/\//.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  // The window itself only ever shows the app's own pages
  const home = isDev ? DEV_URL : APP_ORIGIN
  win.webContents.on('will-navigate', (event, url) => {
    if (url === home || url.startsWith(`${home}/`)) return
    event.preventDefault()
    mainLog.warning('A page tried to leave the app: kept', { url })
  })

  if (isDev) {
    win.loadURL(DEV_URL)
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadURL(`${APP_ORIGIN}/index.html`)
  }
}
