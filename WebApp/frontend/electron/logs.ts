import { appendFileSync, existsSync, mkdirSync, readdirSync, renameSync, statSync, unlinkSync } from 'fs'
import { basename, dirname, join } from 'path'

// The OS's per-app log folder (electron app.getPath('logs')) is passed in by
// main.ts rather than imported, so this module has no `electron` dependency and
// its pure logic (rotation, the page-line check) is testable under node --test.

// The app's log: one JSON object a line in frontend.log, as the backend
// writes backend.log (backend/app/core/logs.py), in the same folder: WebApp/logs
// while developing, `logDir` from kanat-config.json when installed
// (C:\ProgramData\Kanat\logs on the range PC). The Logs tab reads these files.
//
// Only this, the main process, writes it: the pages hand their lines over IPC
// (preload.ts), as they may not touch files.

const LOG_FILE = 'frontend.log'
// Rotated as backend.log is: once a day, keeping this many past days (~a week).
// Rotated files are frontend.log.YYYY-MM-DD (UTC), matching the backend's.
const BACKUP_DAYS = 7

export type LogLevel = 'debug' | 'info' | 'warning' | 'error'

// A line from a page, or from the main process itself
export interface LogEntry {
  level: LogLevel
  message: string
  logger?: string                    // what logged it: "app" for the pages, "electron" for the main process
  page?: string                      // the page shown, for a page's line
  time?: string
  context?: Record<string, unknown>  // the line's own fields: camera, session_id...
}

// The fields every line has, which a context may not overwrite
const OWN = new Set(['time', 'level', 'service', 'logger', 'message', 'page'])
const LEVELS = new Set<unknown>(['debug', 'info', 'warning', 'error'])
// A page's line is cut to these: a page cannot fill the disk with one
const MAX_MESSAGE = 2000
const MAX_CONTEXT = 8000

let file: string | null = null

// The log folder: kanat-config.json's logDir if set; else WebApp/logs while
// developing (beside backend.log), and the OS's log folder for this app once
// packaged without one
export function resolveLogDir(configured: string | undefined, isDev: boolean, osLogDir: string): string {
  if (configured) return configured
  // dist-electron/main.js -> WebApp/logs
  return isDev ? join(__dirname, '../../logs') : osLogDir
}

// Logs to `dir`, or, when it cannot be written (made by an installer for
// another user, say), to the OS's log folder for this app, said on the
// console and in that log. Returns the folder written to, or null for the
// console only.
export function startFileLog(dir: string, osLogDir: string): string | null {
  for (const candidate of [dir, osLogDir]) {
    try {
      mkdirSync(candidate, { recursive: true })
      appendFileSync(join(candidate, LOG_FILE), '', 'utf8')   // writable, or throws
      file = join(candidate, LOG_FILE)
      if (candidate !== dir) mainLog.warning('The log folder cannot be written: logging here instead', { configured: dir })
      return candidate
    } catch (err) {
      console.error(`Logging to ${candidate} failed:`, err)
    }
  }
  return null
}

// A page's line as it came over IPC, checked: a page's code is not trusted
// to send the right shape. Null for one that is not a log line.
export function fromPage(entry: unknown): LogEntry | null {
  if (typeof entry !== 'object' || entry === null) return null
  const { level, message, page, time, context } = entry as Record<string, unknown>
  if (!LEVELS.has(level) || typeof message !== 'string') return null
  let fields: Record<string, unknown> | undefined
  if (typeof context === 'object' && context !== null) {
    const json = JSON.stringify(context)
    fields = json.length <= MAX_CONTEXT ? (context as Record<string, unknown>) : { context_cut: json.slice(0, MAX_CONTEXT) }
  }
  return {
    level: level as LogLevel,
    message: message.slice(0, MAX_MESSAGE),
    page: typeof page === 'string' ? page.slice(0, 200) : undefined,
    time: typeof time === 'string' ? time.slice(0, 40) : undefined,
    context: fields,
  }
}

export function writeLog(entry: LogEntry) {
  const fields = Object.fromEntries(Object.entries(entry.context ?? {}).filter(([key]) => !OWN.has(key)))
  const line = JSON.stringify({
    time: entry.time ?? new Date().toISOString(),
    level: entry.level,
    service: 'frontend',
    logger: entry.logger ?? 'app',
    message: entry.message,
    ...(entry.page ? { page: entry.page } : {}),
    ...fields,
  })
  // With no file yet, or none to write, the line is not lost: on the console
  if (!file) {
    console.error(line)
    return
  }
  try {
    rotateIfNewDay(file)
    appendFileSync(file, line + '\n', 'utf8')
  } catch (err) {
    console.error('Writing the log failed:', err, line)
  }
}

// The main process's own lines: start, a page that crashed, its own errors
export const mainLog = {
  info: (message: string, context?: Record<string, unknown>) => writeLog({ level: 'info', logger: 'electron', message, context }),
  warning: (message: string, context?: Record<string, unknown>) => writeLog({ level: 'warning', logger: 'electron', message, context }),
  error: (message: string, context?: Record<string, unknown>) => writeLog({ level: 'error', logger: 'electron', message, context }),
}

// The UTC day (YYYY-MM-DD) of a date, as the rotated files are named
export function utcDay(date: Date): string {
  return date.toISOString().slice(0, 10)
}

// On the first write of a new day, roll frontend.log to frontend.log.<its day>
// and drop days beyond BACKUP_DAYS. The file's mtime dates its last write, so a
// file last written days ago is labelled with that day, and a day the app never
// ran leaves no file (nothing to drop) — like the backend's TimedRotatingFileHandler.
export function rotateIfNewDay(path: string) {
  if (!existsSync(path)) return
  const day = utcDay(statSync(path).mtime)
  if (day === utcDay(new Date())) return
  const rotated = `${path}.${day}`
  if (existsSync(rotated)) return   // already have that day's file; keep appending
  renameSync(path, rotated)
  pruneOldDays(path)
}

// Keep only the newest BACKUP_DAYS rotated files (dates sort lexicographically)
function pruneOldDays(path: string) {
  const prefix = basename(path) + '.'
  let rotated: string[]
  try {
    rotated = readdirSync(dirname(path)).filter(f => f.startsWith(prefix) && /\d{4}-\d{2}-\d{2}$/.test(f))
  } catch {
    return
  }
  rotated.sort()   // oldest first
  for (const f of rotated.slice(0, Math.max(0, rotated.length - BACKUP_DAYS))) {
    try {
      unlinkSync(join(dirname(path), f))
    } catch {
      // the file may be gone already, or in use; next day tries again
    }
  }
}
