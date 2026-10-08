import { Session } from '../types'
import { apiFetch, BASE_URL } from './client'

export function getSessions(): Promise<Session[]> {
  return apiFetch<Session[]>('/sessions')
}

export function getSession(id: string): Promise<Session> {
  return apiFetch<Session>(`/sessions/${id}`)
}

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

export function deleteSession(id: string): Promise<void> {
  return apiFetch<void>(`/sessions/${id}`, { method: 'DELETE' })
}

export function exportUrl(id: string, format: 'pdf' | 'csv' | 'excel'): string {
  return `${BASE_URL}/sessions/${id}/export/${format}`
}
