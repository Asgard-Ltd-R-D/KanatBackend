import type { PublicConfig } from '../../electron/config'
import type { LogEntry } from '../../electron/logs'
import type { LogLine } from '../../electron/logreader'

declare global {
  interface Window {
    kanat: PublicConfig
    // The app's log (electron/preload.ts); absent outside Electron
    kanatLog?: {
      write: (entry: LogEntry) => void
      openFolder: () => Promise<string>
      // The newest log lines across the files, for the Logs tab's viewer
      read: (limit?: number) => Promise<LogLine[]>
      // Checks the engineer password that unlocks the Logs tab (against the
      // baked hash, in the main process). True when no password is configured.
      verifyPassword: (password: string) => Promise<boolean>
    }
  }
}

export {}
