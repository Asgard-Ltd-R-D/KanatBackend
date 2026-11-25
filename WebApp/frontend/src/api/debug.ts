// TEMPORARY debug capture (delete before production). Start/stop a recording
// and upload the app-view blob the renderer recorded. The backend writes the
// raw camera stream, the logs and this blob into one timestamped folder.
import { API_URL } from '../utils/config'
import { apiFetch } from './client'

export interface StartedRecording {
  id: string
  folder: string
}

export function startRecording(camera?: string): Promise<StartedRecording> {
  return apiFetch<StartedRecording>('/debug/recordings', {
    method: 'POST',
    body: JSON.stringify({ camera: camera ?? null }),
  })
}

// The recorded blob, POSTed as the raw body (not multipart, so the backend
// needs no extra dependency). Its type tells the backend WebM from MP4.
export async function uploadOverlay(recordingId: string, blob: Blob): Promise<void> {
  const res = await fetch(`${API_URL}/debug/recordings/${recordingId}/overlay`, {
    method: 'POST',
    headers: { 'Content-Type': blob.type || 'application/octet-stream' },
    body: blob,
  })
  // fetch resolves on HTTP errors too; throw so the caller's failure path runs
  // (keeps the recording instead of reporting it saved without the app view)
  if (!res.ok) throw new Error(`overlay upload failed: HTTP ${res.status}`)
}

export function stopRecording(recordingId: string): Promise<{ folder: string }> {
  return apiFetch<{ folder: string }>(`/debug/recordings/${recordingId}/stop`, { method: 'POST' })
}

// Best-effort stop for window close/reload, where async calls don't get to run:
// sendBeacon hands the request to the OS so the backend still finalises (ffmpeg
// closed, logs sliced). The overlay can't be uploaded on unload; the backend's
// own lease is the backstop if even this doesn't fire (a crash).
export function beaconStop(recordingId: string): void {
  try {
    navigator.sendBeacon(`${API_URL}/debug/recordings/${recordingId}/stop`)
  } catch {
    // nothing more we can do on the way out
  }
}
