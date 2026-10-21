import { SystemStatus } from '../types'
import { apiFetch } from './client'

// A backend that does not answer within this long is reported as offline
const TIMEOUT_MS = 2000

export function getStatus(): Promise<SystemStatus> {
  return apiFetch<SystemStatus>('/status', { signal: AbortSignal.timeout(TIMEOUT_MS) })
}
