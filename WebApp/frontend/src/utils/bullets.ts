import { BulletHole } from '../types'

// How an offset in millimetres is shown (a Group's MPI)

export function mmLabel(b: Pick<BulletHole, 'x_mm' | 'y_mm'>): string {
  if (b.x_mm == null || b.y_mm == null) return '—'
  const sign = (n: number) => (n >= 0 ? `+${n.toFixed(1)}` : n.toFixed(1))
  return `${sign(b.x_mm)}, ${sign(b.y_mm)} mm`
}
