// Upload the clean baseline frame grabbed from a camera's live video, stored
// by the backend against the Run it was captured for.
import { API_URL } from '../utils/config'
import { ApiError } from './client'

// The camera's baseline-image URL, for the Run taken at `takenAt`
function imageUrl(sessionId: string, alias: string, takenAt: string): string {
  const base = `${API_URL}/sessions/${encodeURIComponent(sessionId)}/cameras/${encodeURIComponent(alias)}/baseline-image`
  return `${base}?taken_at=${encodeURIComponent(takenAt)}`
}

// The blob, POSTed as the raw body (like the debug overlay upload). Its type
// (image/png or image/jpeg) tells the backend the format. `takenAt` names the
// Run, so a frame uploaded after a retake made a newer Run is never stored on it.
export async function uploadBaselineImage(sessionId: string, alias: string, takenAt: string, blob: Blob): Promise<void> {
  const res = await fetch(
    imageUrl(sessionId, alias, takenAt),
    {
      method: 'POST',
      headers: { 'Content-Type': blob.type || 'image/png' },
      body: blob,
    },
  )
  // 409: the Run already has its baseline image (captured from another tab),
  // which is kept; nothing more to send
  if (res.status === 409) return
  // fetch resolves on HTTP errors too; throw so the caller can log the failure
  if (!res.ok) throw new ApiError(`baseline image upload failed: HTTP ${res.status}`, res.status)
}

// The stored baseline frame of the camera's Run taken at `takenAt`, or null
// when none was captured (404). Other failures throw.
export async function getBaselineImage(sessionId: string, alias: string, takenAt: string): Promise<Blob | null> {
  const res = await fetch(imageUrl(sessionId, alias, takenAt))
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`baseline image fetch failed: HTTP ${res.status}`)
  return res.blob()
}

// How many times one captured frame is sent before giving up
const MAX_UPLOAD_ATTEMPTS = 5

// Runs whose frame is being sent or is done with (sent, refused, or given up),
// by `${sessionId}:${alias}:${takenAt}`: a Run's frame is captured and sent once
// per app run, whatever the live view does meanwhile
const started = new Set<string>()

export function baselineUploadStarted(sessionId: string, alias: string, takenAt: string): boolean {
  return started.has(`${sessionId}:${alias}:${takenAt}`)
}

// Send a captured frame for its Run, retrying the same frame with backoff after
// a network or server failure, up to MAX_UPLOAD_ATTEMPTS; a refusal (4xx) is
// final. Independent of any component, so ending the session or leaving the
// page does not abandon it. `onStored` runs once the frame is stored.
export function uploadBaselineWithRetry(
  sessionId: string,
  alias: string,
  takenAt: string,
  blob: Blob,
  onStored: () => void,
): void {
  const key = `${sessionId}:${alias}:${takenAt}`
  if (started.has(key)) return
  started.add(key)
  const attempt = (n: number) => {
    uploadBaselineImage(sessionId, alias, takenAt, blob)
      .then(onStored)
      .catch(err => {
        console.warn('baseline image upload failed', err)
        const refused = err instanceof ApiError && err.status >= 400 && err.status < 500
        if (!refused && n < MAX_UPLOAD_ATTEMPTS) setTimeout(() => attempt(n + 1), 2000 * 2 ** (n - 1))
      })
  }
  attempt(1)
}
