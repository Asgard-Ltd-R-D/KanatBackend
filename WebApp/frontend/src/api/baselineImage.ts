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
