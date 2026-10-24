import { Session } from '../types'
import { apiFetch } from './client'
import { API_URL } from '../utils/config'

export function getSessions(): Promise<Session[]> {
  return apiFetch<Session[]>('/sessions')
}

export function getSession(id: string): Promise<Session> {
  return apiFetch<Session>(`/sessions/${id}`)
}

// cameraId: the camera whose stream detection watches, or null for none
export function createSession(name: string, record: boolean, cameraId: string | null): Promise<Session> {
  return apiFetch<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ name, record, camera_id: cameraId }),
  })
}

export function updateSession(
  id: string,
  patch: { name?: string; status?: 'active' | 'completed'; record?: boolean },
): Promise<Session> {
  return apiFetch<Session>(`/sessions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export function deleteSession(id: string): Promise<void> {
  return apiFetch<void>(`/sessions/${id}`, { method: 'DELETE' })
}

export function exportUrl(id: string, format: 'pdf' | 'csv' | 'excel'): string {
  return `${API_URL}/sessions/${id}/export/${format}`
}
