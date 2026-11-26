import { BulletHole } from '../types'

// A Bullet Hole's offset from its Target's centre, stored in mm, shown in cm
export function cmLabel(b: Pick<BulletHole, 'x_mm' | 'y_mm'>): string {
  if (b.x_mm == null || b.y_mm == null) return '—'
  const sign = (mm: number) => {
    // Rounded first, so a hole a hair left of centre reads +0.00, not -0.00
    const cm = mm / 10
    const s = cm.toFixed(2)
    return s.startsWith('-') && Number(s) !== 0 ? s : `+${s.replace('-', '')}`
  }
  return `${sign(b.x_mm)}, ${sign(b.y_mm)} cm`
}

// Which Target a hole is on, as the exports name it
// ("No target": a manual one, or a Miss stored before #422)
export function targetLabel(b: Pick<BulletHole, 'target_index'>): string {
  return b.target_index != null ? `Target ${b.target_index + 1}` : 'No target'
}

// Targets in index order, then the holes on no Target
function targetOrder(b: Pick<BulletHole, 'target_index'>): number {
  return b.target_index ?? Number.MAX_SAFE_INTEGER
}

// A board's holes, one section per Target, each in rank order (ranks unchanged)
export function byTarget(bullets: BulletHole[]): { label: string; bullets: BulletHole[] }[] {
  const sections = new Map<number, BulletHole[]>()
  for (const b of [...bullets].sort((a, b) => a.rank - b.rank)) {
    const key = targetOrder(b)
    sections.set(key, [...(sections.get(key) ?? []), b])
  }
  return [...sections.entries()].sort(([a], [b]) => a - b).map(([, bs]) => ({ label: targetLabel(bs[0]), bullets: bs }))
}
