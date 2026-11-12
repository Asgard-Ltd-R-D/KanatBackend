import { Session } from '../types'
import { apiFetch } from './client'
import { API_URL } from '../utils/config'

export function getSessions(): Promise<Session[]> {
  return apiFetch<Session[]>('/sessions')
}

export function getSession(id: string): Promise<Session> {
  return apiFetch<Session>(`/sessions/${id}`)
}

// A Session spans every currently-enabled camera (one board each); no camera is chosen
export function createSession(name: string): Promise<Session> {
  return apiFetch<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function updateSession(
  id: string,
  patch: { name?: string; status?: 'active' | 'completed' },
): Promise<Session> {
  return apiFetch<Session>(`/sessions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

// A new Run from a fresh baseline for one board (camera alias), after its Target
// Sheet is re-hung: the Session stays active, and that board's detection reads
// "starting" until it is ready
export function retakeBaseline(id: string, camera: string): Promise<Session> {
  return apiFetch<Session>(`/sessions/${id}/baseline/${encodeURIComponent(camera)}`, { method: 'POST' })
}

export function deleteSession(id: string): Promise<void> {
  return apiFetch<void>(`/sessions/${id}`, { method: 'DELETE' })
}

export function exportUrl(id: string, format: 'pdf' | 'csv' | 'excel'): string {
  return `${API_URL}/sessions/${id}/export/${format}`
}
