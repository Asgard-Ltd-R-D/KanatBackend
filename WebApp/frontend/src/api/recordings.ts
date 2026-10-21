import { CameraRecording, RecordingSpan } from '../types'
import { apiFetch } from './client'
import { API_URL } from '../utils/config'

export function getRecordings(sessionId: string): Promise<CameraRecording[]> {
  return apiFetch<CameraRecording[]>(`/sessions/${sessionId}/recordings`)
}

// One recorded span as an MP4, for a <video> element
export function recordingVideoUrl(sessionId: string, alias: string, span: RecordingSpan): string {
  const query = new URLSearchParams({ start: span.start, duration_s: String(span.duration_s) })
  return `${API_URL}/sessions/${sessionId}/recordings/${encodeURIComponent(alias)}/video?${query}`
}
