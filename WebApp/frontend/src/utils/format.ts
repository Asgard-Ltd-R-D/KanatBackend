// How times and lengths are written across the app

// A moment as a wall-clock time, e.g. 14:05:09
export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// The time between two moments, or from one until now: 12m 4s, and from an
// hour on 1h 5m 4s (never 65m 4s)
export function formatDuration(startedAt: string, endedAt: string | null): string {
  const ms = (endedAt ? new Date(endedAt).getTime() : Date.now()) - new Date(startedAt).getTime()
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`
}

// A length in seconds as m:ss, e.g. 2:05
export function formatLength(seconds: number): string {
  const total = Math.round(seconds) // round first, so 119.6 is 2:00, not 1:60
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
