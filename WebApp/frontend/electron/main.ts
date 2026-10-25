import { app, BrowserWindow, dialog } from 'electron'
import { join } from 'path'
import { readConfig } from './config'
import { registerIpcHandlers } from './ipc'
import { mainLog, resolveLogDir, startFileLog } from './logs'
import { registerAppScheme, serveApp } from './protocol'
import { APP_ICON, createWindow } from './window'

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

// Shown as KANAT; its data stays in the folder named after the package, where
// kanat-config.json and the window's saved settings already are
app.setPath('userData', join(app.getPath('appData'), 'kanat-webapp'))
app.setName('KANAT')

registerAppScheme()

// Logged, and still shown as Electron shows one without a handler: the
// operator sees the app is in trouble, and the line is on the console
// before the log file is open
process.on('uncaughtException', (err) => {
  mainLog.error('Uncaught error in the app\'s main process', { error: err.message, stack: err.stack })
  if (app.isReady()) dialog.showErrorBox('KANAT: an error occurred', err.stack ?? err.message)
})
process.on('unhandledRejection', (reason) =>
  mainLog.error('Unhandled failure in the app\'s main process', {
    error: String(reason),
    ...(reason instanceof Error ? { stack: reason.stack } : {}),
  }),
)

app.whenReady().then(() => {
  const config = readConfig()
  // Resolved here, so the Logs tab shows the folder actually written to
  config.logDir = startFileLog(resolveLogDir(config.logDir, isDev)) ?? undefined
  mainLog.info('App started', {
    version: app.getVersion(),
    electron: process.versions.electron,
    packaged: app.isPackaged,
    api_url: config.apiUrl,
    media_url: config.mediaUrl,
    grafana_url: config.grafanaUrl,
    log_dir: config.logDir,
  })

  // A packaged app takes its Dock icon from its bundle; `npm run dev` runs Electron's own
  if (process.platform === 'darwin') app.dock?.setIcon(APP_ICON)

  registerIpcHandlers(config)
  if (!isDev) serveApp(config)

  createWindow(isDev, config)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(isDev, config)
  })
})

app.on('child-process-gone', (_event, details) => {
  if (details.reason !== 'clean-exit') mainLog.error('A process of the app stopped', { type: details.type, reason: details.reason, exit_code: details.exitCode })
})

app.on('window-all-closed', () => {
  mainLog.info('App closing')
  if (process.platform !== 'darwin') app.quit()
})
