import { app } from 'electron'
import { existsSync, readFileSync } from 'fs'
import { join } from 'path'

// Read at startup from kanat-config.json, so a deployed install is
// reconfigured by editing that file, not by rebuilding: the one in the app's
// userData folder (this user's), else, on Windows, the PC's in
// %ProgramData%\Kanat, which the installer writes for every user.
export interface KanatConfig {
  apiUrl: string      // WebApp backend
  mediaUrl: string    // MediaMTX WebRTC server (WHEP)
  // The folder of frontend.log, shared with the backend's backend.log and the
  // Detection Service's detection.log (electron/logs.ts); the Logs tab reads
  // them from here. Unset: WebApp/logs while developing, the OS's log folder
  // for this app once installed. The installer sets C:\ProgramData\Kanat\logs.
  logDir?: string
  // Salt:hash (scrypt) of the engineer password that unlocks the Logs tab; the
  // installer bakes it in. Stays in the main process (checked over IPC), never
  // sent to a page. Unset: the Logs tab is open (developing).
  logsPasswordHash?: string
}

// The config a page is given (preload): the password hash is stripped and
// replaced with whether the Logs tab is protected, so the hash never reaches a page.
export type PublicConfig = Omit<KanatConfig, 'logsPasswordHash'> & { logsProtected: boolean }

export function publicConfig(config: KanatConfig): PublicConfig {
  const { logsPasswordHash, ...rest } = config
  return { ...rest, logsProtected: !!logsPasswordHash }
}

// 127.0.0.1, not localhost: on Windows localhost tries IPv6 first, and waits
// for it to fail on every new connection
const DEFAULT_CONFIG: KanatConfig = {
  apiUrl: 'http://127.0.0.1:8000',
  mediaUrl: 'http://127.0.0.1:8889',
}

// The config files to read, the first found winning
function configFiles(): string[] {
  const files = [join(app.getPath('userData'), 'kanat-config.json')]
  if (process.platform === 'win32') files.push(join(process.env.ProgramData ?? 'C:\\ProgramData', 'Kanat', 'kanat-config.json'))
  return files
}

export function readConfig(): KanatConfig {
  const config = { ...DEFAULT_CONFIG }
  const file = configFiles().find((f) => existsSync(f))
  if (!file) return config   // no config file: the defaults
  try {
    // Without the byte order mark Notepad may save it with, which JSON refuses
    const cfg = JSON.parse(readFileSync(file, 'utf8').replace(/^\uFEFF/, ''))
    if (typeof cfg.apiUrl === 'string') config.apiUrl = cfg.apiUrl
    if (typeof cfg.mediaUrl === 'string') config.mediaUrl = cfg.mediaUrl
    if (typeof cfg.logDir === 'string' && cfg.logDir.trim()) config.logDir = cfg.logDir.trim()
    if (typeof cfg.logsPasswordHash === 'string' && cfg.logsPasswordHash.trim()) config.logsPasswordHash = cfg.logsPasswordHash.trim()
  } catch {
    // unreadable or not JSON: the defaults
  }
  return config
}
