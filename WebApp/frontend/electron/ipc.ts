import { ipcMain, shell } from 'electron'
import { GET_CONFIG, OPEN_LOG_FOLDER, WRITE_LOG } from './channels'
import { KanatConfig } from './config'
import { fromPage, writeLog } from './logs'

export function registerIpcHandlers(config: KanatConfig) {
  ipcMain.on(GET_CONFIG, (event) => {
    event.returnValue = config
  })
  // A page's log line, written to frontend.log once checked
  ipcMain.on(WRITE_LOG, (_event, entry: unknown) => {
    const line = fromPage(entry)
    if (line) writeLog(line)
  })
  // The Logs tab's "Open folder": the system's file manager on the log folder
  ipcMain.handle(OPEN_LOG_FOLDER, () => (config.logDir ? shell.openPath(config.logDir) : 'No log folder'))
}
