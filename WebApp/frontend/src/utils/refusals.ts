// The same refusal again within this is counted, not logged: a page that
// polls, or retries, while the backend refuses would write a line a second
const REPEAT_MS = 60_000
const last = new Map<string, { at: number; repeats: number }>()

// Whether this refusal (its method, path, status and reason) is logged, and
// how many like it were not since the last one that was
export function refusalToLog(key: string, now = Date.now()): { log: boolean; repeats: number } {
  const seen = last.get(key)
  if (seen && now - seen.at < REPEAT_MS) {
    seen.repeats++
    return { log: false, repeats: 0 }
  }
  last.set(key, { at: now, repeats: 0 })
  return { log: true, repeats: seen?.repeats ?? 0 }
}
