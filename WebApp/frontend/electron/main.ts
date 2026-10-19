import { app, BrowserWindow } from 'electron'
import { readConfig } from './config'
import { registerIpcHandlers } from './ipc'
import { registerAppScheme, serveApp } from './protocol'
import { createWindow } from './window'

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

registerAppScheme()

app.whenReady().then(() => {
  const config = readConfig()
  registerIpcHandlers(config)
  if (!isDev) serveApp(config)

  createWindow(isDev)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow(isDev)
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
