import { open } from 'fs/promises'
import { join } from 'path'

// Reads the app's JSON-line logs for the Logs tab, so the app shows them
// itself without Grafana. Only the main process touches the files; the page
// asks for the lines over IPC (ipc.ts, preload.ts).
//
// The backend writes backend.log, the Detection Service detection.log and the
// app frontend.log, all one JSON object a line in the same folder
// (core/logs.py, detection, electron/logs.ts). Rotated files (.YYYY-MM-DD, a
// week of past days) are in the folder too; "Open folder" reaches them, this does not.

const APP_LOGS = ['backend.log', 'frontend.log', 'detection.log']
// Only the tail of each file is read, so a 10 MB log does not have to be loaded
// whole on every refresh. Enough for thousands of recent lines.
const TAIL_BYTES = 512 * 1024
// The most lines handed to the page at once, newest kept
const MAX_LINES = 5000

export interface LogLine {
  time: string
  level: string
  service: string
  logger?: string
  message: string
  // Every other field the line carried (page, request_id, camera, ...)
  fields: Record<string, unknown>
}

// The last `bytes` of a file, with `partial` true when the read began mid-line
// (so the first line is a fragment the caller drops). Async, so reading does not
// block the main process's event loop while the Logs tab refreshes.
async function tail(path: string, bytes: number): Promise<{ text: string; partial: boolean }> {
  let fh
  try {
    fh = await open(path, 'r')
  } catch {
    return { text: '', partial: false } // the file does not exist yet
  }
  try {
    const { size } = await fh.stat()
    const start = Math.max(0, size - bytes)
    const length = size - start
    if (length <= 0) return { text: '', partial: false }
    const buf = Buffer.alloc(length)
    await fh.read(buf, 0, length, start)
    // A read that did not start at 0 begins mid-line, and may begin mid-UTF-8
    // character; the fragment's line is dropped by the caller
    return { text: buf.toString('utf8'), partial: start > 0 }
  } catch {
    return { text: '', partial: false }
  } finally {
    await fh.close()
  }
}

// One JSON line parsed into a LogLine, or null for a blank or unparseable line
function parse(line: string): LogLine | null {
  const text = line.trim()
  if (!text) return null
  let obj: Record<string, unknown>
  try {
    obj = JSON.parse(text)
  } catch {
    return null
  }
  if (typeof obj.message !== 'string') return null
  const { time, level, service, logger, message, ...fields } = obj
  return {
    time: typeof time === 'string' ? time : '',
    level: typeof level === 'string' ? level : 'info',
    service: typeof service === 'string' ? service : 'unknown',
    logger: typeof logger === 'string' ? logger : undefined,
    message,
    fields,
  }
}

// An ISO timestamp as epoch ms for sorting, handling both the "+00:00" the
// backend writes and the "Z" the app writes; an unparseable one sinks to the end
function when(time: string): number {
  const ms = Date.parse(time)
  return isNaN(ms) ? -Infinity : ms
}

// The newest log lines across the app's files, newest first. Reads only each
// file's tail, so it is cheap enough to call on a timer.
export async function readLogs(dir: string | undefined, limit = MAX_LINES): Promise<LogLine[]> {
  if (!dir) return []
  const chunks = await Promise.all(APP_LOGS.map((name) => tail(join(dir, name), TAIL_BYTES)))
  const lines: LogLine[] = []
  for (const { text, partial } of chunks) {
    if (!text) continue
    const raw = text.split('\n')
    for (let i = partial ? 1 : 0; i < raw.length; i++) {
      const parsed = parse(raw[i])
      if (parsed) lines.push(parsed)
    }
  }
  lines.sort((a, b) => when(b.time) - when(a.time))
  return lines.slice(0, limit)
}
