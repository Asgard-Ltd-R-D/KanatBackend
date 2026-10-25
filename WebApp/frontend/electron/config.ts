import { app } from 'electron'
import { readFileSync } from 'fs'
import { join } from 'path'

// Read at startup from kanat-config.json in the app's userData folder, so a
// deployed install is reconfigured by editing that file, not by rebuilding.
export interface KanatConfig {
  apiUrl: string      // WebApp backend
  mediaUrl: string    // MediaMTX WebRTC server (WHEP)
  grafanaUrl: string  // Grafana, the Logs tab (WebApp/docker-compose.yml)
  // The folder of frontend.log, shared with the backend's backend.log
  // (electron/logs.ts). Unset: WebApp/logs while developing, the OS's log
  // folder for this app once installed. The installer sets /var/log/kanat.
  logDir?: string
}

const DEFAULT_CONFIG: KanatConfig = {
  apiUrl: 'http://localhost:8000',
  mediaUrl: 'http://localhost:8889',
  grafanaUrl: 'http://127.0.0.1:3300',
}

export function readConfig(): KanatConfig {
  const config = { ...DEFAULT_CONFIG }
  try {
    const cfg = JSON.parse(
      readFileSync(join(app.getPath('userData'), 'kanat-config.json'), 'utf8'),
    )
    if (typeof cfg.apiUrl === 'string') config.apiUrl = cfg.apiUrl
    if (typeof cfg.mediaUrl === 'string') config.mediaUrl = cfg.mediaUrl
    if (typeof cfg.grafanaUrl === 'string') config.grafanaUrl = cfg.grafanaUrl
    if (typeof cfg.logDir === 'string' && cfg.logDir.trim()) config.logDir = cfg.logDir.trim()
  } catch {
    // no config file — use defaults
  }
  return config
}
