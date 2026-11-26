// Upload the clean baseline frame grabbed from a camera's live video, stored
// by the backend against that camera's latest Run.
import { API_URL } from '../utils/config'

// The blob, POSTed as the raw body (like the debug overlay upload). Its type
// (image/png or image/jpeg) tells the backend the format.
export async function uploadBaselineImage(sessionId: string, alias: string, blob: Blob): Promise<void> {
  const res = await fetch(
    `${API_URL}/sessions/${encodeURIComponent(sessionId)}/cameras/${encodeURIComponent(alias)}/baseline-image`,
    {
      method: 'POST',
      headers: { 'Content-Type': blob.type || 'image/png' },
      body: blob,
    },
  )
  // fetch resolves on HTTP errors too; throw so the caller can log the failure
  if (!res.ok) throw new Error(`baseline image upload failed: HTTP ${res.status}`)
}

// The stored baseline frame of a camera's latest Run, or null when none was
// captured (404). Other failures throw.
export async function getBaselineImage(sessionId: string, alias: string): Promise<Blob | null> {
  const res = await fetch(
    `${API_URL}/sessions/${encodeURIComponent(sessionId)}/cameras/${encodeURIComponent(alias)}/baseline-image`,
  )
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`baseline image fetch failed: HTTP ${res.status}`)
  return res.blob()
}
