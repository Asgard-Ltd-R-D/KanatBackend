import { API_URL } from '../utils/config'
import { log } from '../utils/logger'
import { refusalToLog } from '../utils/refusals'

// A request the backend answered with an error status
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

// Since when the backend has not answered, so losing it and getting it back
// are logged once each, not on every poll
let unreachableSince: number | null = null
// Polled every few seconds; the sidebar's status shows their failures
const QUIET_PATHS = ['/status']
export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const method = options?.method ?? 'GET'
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    })
  } catch (err) {
    // A poll that only took too long: the backend is slow, not gone, and the
    // sidebar shows it; the next one says whether it answers
    const timedOut = err instanceof DOMException && (err.name === 'TimeoutError' || err.name === 'AbortError')
    if (timedOut && QUIET_PATHS.includes(path)) throw err
    if (unreachableSince === null) {
      unreachableSince = Date.now()
      log.warning('Backend not reachable', { method, path, error: String(err) })
    }
    throw err
  }
  if (unreachableSince !== null) {
    log.info('Backend reachable again', { down_s: Math.round((Date.now() - unreachableSince) / 1000) })
    unreachableSince = null
  }

  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body.detail ?? body.message ?? message
    } catch {
      // ignore parse error
    }
    const text = typeof message === 'string' ? message : 'invalid request'
    const refusal = QUIET_PATHS.includes(path) ? null : refusalToLog(`${method} ${path} ${res.status} ${text}`)
    if (refusal?.log) {
      log.warning(`${method} ${path} refused: ${text}`, {
        method,
        path,
        status: res.status,
        detail: message,
        ...(refusal.repeats ? { repeats_not_logged: refusal.repeats } : {}),
      })
    }
    throw new ApiError(message, res.status)
  }

  if (res.status === 204) return undefined as T
  return res.json()
}
