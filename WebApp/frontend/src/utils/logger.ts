import type { LogLevel } from '../../electron/logs'

// The app's log. Each line goes to the console and to frontend.log, which
// the app's main process writes beside the backend's backend.log
// (electron/logs.ts): Grafana shows both, in the Logs tab. Outside Electron
// (the renderer alone in a browser) the console is all there is.
//
//   log.warning('Camera video lost', { camera: 'lane1', reason })

// The page shown, from the hash router: "/sessions/<id>", "/settings"...
const currentPage = () => window.location.hash.replace(/^#/, '') || '/'

const CONSOLE: Record<LogLevel, (...args: unknown[]) => void> = {
  debug: console.debug,
  info: console.info,
  warning: console.warn,
  error: console.error,
}

const describe = (value: unknown) =>
  value instanceof Error ? { error: value.message, stack: value.stack } : { error: String(value) }

// Only plain data crosses to the main process: an Error as its message and
// stack (JSON would make it {}), anything else that is not data (a function,
// a DOM node) as text rather than lose the line
function plain(context: Record<string, unknown>): Record<string, unknown> {
  try {
    return JSON.parse(JSON.stringify(context, (_key, value) => (value instanceof Error ? describe(value) : value)))
  } catch {
    return { context: String(context) }
  }
}

function write(level: LogLevel, message: string, context: Record<string, unknown> = {}) {
  CONSOLE[level](`[${level}] ${message}`, context)
  window.kanatLog?.write({ level, message, page: currentPage(), time: new Date().toISOString(), context: plain(context) })
}

export const log = {
  debug: (message: string, context?: Record<string, unknown>) => write('debug', message, context),
  info: (message: string, context?: Record<string, unknown>) => write('info', message, context),
  warning: (message: string, context?: Record<string, unknown>) => write('warning', message, context),
  error: (message: string, context?: Record<string, unknown>) => write('error', message, context),
}

// Errors nothing else caught
export function startLogging() {
  window.addEventListener('error', (event) =>
    log.error('Uncaught error in the app', {
      ...describe(event.error ?? event.message),
      source: event.filename,
      line: event.lineno,
    }),
  )
  window.addEventListener('unhandledrejection', (event) =>
    log.error('Unhandled failure in the app', describe(event.reason)),
  )
  log.info('App page loaded', { userAgent: navigator.userAgent })
}
