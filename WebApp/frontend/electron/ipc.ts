import { ipcMain, shell } from 'electron'
import { GET_CONFIG, OPEN_LOG_FOLDER, READ_LOGS, VERIFY_LOGS_PASSWORD, WRITE_LOG } from './channels'
import { KanatConfig, publicConfig } from './config'
import { fromPage, writeLog } from './logs'
import { passwordMatches } from './logsAuth'
import { readLogs } from './logreader'

export function registerIpcHandlers(config: KanatConfig) {
  // Whether the Logs tab's data may be served this session: not until the
  // password unlocks it, so a locked tab cannot be read around from the renderer
  // (devtools). Open from the start when no password is configured (developing).
  let logsUnlocked = !config.logsPasswordHash

  ipcMain.on(GET_CONFIG, (event) => {
    // The password hash stays in the main process; a page gets only whether the
    // Logs tab is protected
    event.returnValue = publicConfig(config)
  })
  // A page's log line, written to frontend.log once checked
  ipcMain.on(WRITE_LOG, (_event, entry: unknown) => {
    const line = fromPage(entry)
    if (line) writeLog(line)
  })
  // The Logs tab's "Open folder": the system's file manager on the log folder
  ipcMain.handle(OPEN_LOG_FOLDER, () => {
    if (!logsUnlocked) return 'Locked'
    return config.logDir ? shell.openPath(config.logDir) : 'No log folder'
  })
  // The Logs tab's viewer: the newest lines across the log files, newest first
  ipcMain.handle(READ_LOGS, (_event, limit: unknown) =>
    logsUnlocked ? readLogs(config.logDir, typeof limit === 'number' ? limit : undefined) : [],
  )
  // Unlocking the Logs tab: checked here so the hash never leaves the main
  // process. With no hash configured (developing), it is already unlocked.
  ipcMain.handle(VERIFY_LOGS_PASSWORD, (_event, password: unknown) => {
    const ok = !config.logsPasswordHash || passwordMatches(password, config.logsPasswordHash)
    if (ok) logsUnlocked = true
    return ok
  })
}
