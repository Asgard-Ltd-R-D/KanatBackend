import { GRAFANA_URL } from '../utils/config'

// Whether Grafana answers. It sends no CORS headers, so the answer is opaque:
// getting one at all says it is up.
export async function isGrafanaUp(): Promise<boolean> {
  try {
    await fetch(`${GRAFANA_URL}/api/health`, { mode: 'no-cors', signal: AbortSignal.timeout(2000) })
    return true
  } catch {
    return false
  }
}
