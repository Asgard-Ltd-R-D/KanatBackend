import { Camera, CameraInput } from '../types'
import { apiFetch } from './client'

export function getCameras(): Promise<Camera[]> {
  return apiFetch<Camera[]>('/cameras')
}

export function createCamera(data: CameraInput): Promise<Camera> {
  return apiFetch<Camera>('/cameras', { method: 'POST', body: JSON.stringify(data) })
}

export function updateCamera(id: string, data: CameraInput): Promise<Camera> {
  return apiFetch<Camera>(`/cameras/${id}`, { method: 'PUT', body: JSON.stringify(data) })
}

export function deleteCamera(id: string): Promise<void> {
  return apiFetch<void>(`/cameras/${id}`, { method: 'DELETE' })
}
