import { app } from 'electron'
import { readFileSync } from 'fs'
import { join } from 'path'

// Read at startup from kanat-config.json in the app's userData folder, so a
// deployed install is reconfigured by editing that file, not by rebuilding.
export interface KanatConfig {
  apiUrl: string    // WebApp backend
  mediaUrl: string  // MediaMTX WebRTC server (WHEP)
}

const DEFAULT_CONFIG: KanatConfig = {
  apiUrl: 'http://localhost:8000',
  mediaUrl: 'http://localhost:8889',
}

export function readConfig(): KanatConfig {
  const config = { ...DEFAULT_CONFIG }
  try {
    const cfg = JSON.parse(
      readFileSync(join(app.getPath('userData'), 'kanat-config.json'), 'utf8'),
    )
    if (typeof cfg.apiUrl === 'string') config.apiUrl = cfg.apiUrl
    if (typeof cfg.mediaUrl === 'string') config.mediaUrl = cfg.mediaUrl
  } catch {
    // no config file — use defaults
  }
  return config
}
