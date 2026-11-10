import type { LogLine } from '../../electron/logreader'
import { API_URL } from '../utils/config'

export type { LogLine }

// The newest log lines across backend.log, frontend.log and detection.log, read
// by the app's main process (electron/logreader.ts) and shown in the Logs tab.
// Empty outside Electron (a plain browser), where there are no files to read.
export async function readLogs(limit?: number): Promise<LogLine[]> {
  return (await window.kanatLog?.read(limit)) ?? []
}

// The backend zips the whole log folder (all services, every rotated day) for
// support. Opened with target="_blank" so Electron saves it (window.ts), as the
// session exports are.
export function logsExportUrl(): string {
  return `${API_URL}/logs/export`
}
