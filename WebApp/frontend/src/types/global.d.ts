import type { KanatConfig } from '../../electron/config'
import type { LogEntry } from '../../electron/logs'

declare global {
  interface Window {
    kanat: KanatConfig
    // The app's log (electron/preload.ts); absent outside Electron
    kanatLog?: {
      write: (entry: LogEntry) => void
      openFolder: () => Promise<string>
    }
  }
}

export {}
