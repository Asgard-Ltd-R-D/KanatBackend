import { BulletHole } from '../types'

// How a Bullet Hole's location and offset are shown

export function locationLabel(b: BulletHole): string {
  if (b.target_index !== null) return `Target ${b.target_index + 1}`
  // Model always computes target assignment; null means explicitly outside targets.
  // Manual bullets never supply target_index, so null means location is unknown.
  return b.source === 'model' ? 'Miss' : '—'
}

export function mmLabel(b: BulletHole): string {
  if (b.x_mm == null || b.y_mm == null) return '—'
  const sign = (n: number) => (n >= 0 ? `+${n.toFixed(1)}` : n.toFixed(1))
  return `${sign(b.x_mm)}, ${sign(b.y_mm)} mm`
}
