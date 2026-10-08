import { BulletHole, BulletCreatePayload } from '../types'
import { apiFetch } from './client'

export function createBullet(
  sessionId: string,
  data: BulletCreatePayload,
): Promise<BulletHole> {
  return apiFetch<BulletHole>(`/sessions/${sessionId}/bullets`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function deleteBullet(
  sessionId: string,
  bulletId: string,
): Promise<void> {
  return apiFetch<void>(`/sessions/${sessionId}/bullets/${bulletId}`, {
    method: 'DELETE',
  })
}
