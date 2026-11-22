// How a Session's live events change the Session the app holds: the backend pushes a
// Bullet Hole's creation or deletion, and this shows it on screen at once, before the
// refetch that confirms it. Pure, so node --test checks it: npm test

import type { BulletHole, LiveEvent, Session } from '../types'

// A new hole joins its board's log. When the backend says it moved other holes (it
// was seen before them: `renumbered`), the ones of its board from its rank on move
// down a rank, as the backend did; a hole already held (a retried POST) is replaced.
export function upsertBullet(session: Session, bullet: BulletHole, renumbered = false): Session {
  const held = session.bullet_holes ?? []
  const isNew = !held.some((b) => b.id === bullet.id)
  const moved = held
    .filter((b) => b.id !== bullet.id)
    // Ranks run per board, so only the new hole's own board moves
    .map((b) => (renumbered && isNew && b.camera_alias === bullet.camera_alias && b.rank >= bullet.rank ? { ...b, rank: b.rank + 1 } : b))
  return { ...session, bullet_holes: [...moved, bullet].sort((a, b) => a.rank - b.rank) }
}

// As the backend does: the bullets after the deleted one move up a rank
export function removeBullet(session: Session, bulletId: string): Session {
  const bullets = session.bullet_holes ?? []
  const gone = bullets.find((b) => b.id === bulletId)
  if (!gone) return session
  return {
    ...session,
    bullet_holes: bullets
      .filter((b) => b.id !== bulletId)
      // Ranks run per board, so only the deleted bullet's own board moves up
      .map((b) =>
        b.camera_alias === gone.camera_alias && b.rank > gone.rank ? { ...b, rank: b.rank - 1 } : b
      ),
  }
}

export function applyEvent(session: Session, event: LiveEvent): Session {
  switch (event.type) {
    case 'bullet_created':
      return upsertBullet(session, event.bullet, event.renumbered)
    case 'bullet_deleted':
      return removeBullet(session, event.bullet_id)
    case 'session_updated':
      return { ...session, name: event.name, status: event.status, ended_at: event.ended_at }
    case 'detection_updated': {
      // Upsert the board named by camera_alias, keeping the others
      const others = (session.detections ?? []).filter(d => d.camera_alias !== event.camera_alias)
      return { ...session, detections: [...others, { camera_alias: event.camera_alias, detection: event.detection }] }
    }
    case 'run_moved':
      // The new place is carried by the refetch (reconcile) this event triggers
      return session
  }
}
