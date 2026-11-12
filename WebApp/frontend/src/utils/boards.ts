// A Session watches every enabled camera at once, each camera a board. A board
// gathers one camera's live detection, its Bullet Holes and its Group. Pure, so
// node --test checks it: npm test

import type { BulletHole, Camera, Detection, Grouping, Session } from '../types'

// A board of a Session: one enabled camera, or a camera since deleted that still
// has holes, or (alias null) the holes on no board
export interface Board {
  alias: string | null // the camera's alias, or null for the holes on no board
  camera?: Camera // the enabled camera, when the board still has one
  detection: Detection // "none" for a board with no detection entry yet
  grouping?: Grouping // present only once computed (a completed Session)
  bullets: BulletHole[] // this board's Bullet Holes
}

// A board with no detection entry yet
const NONE: Detection = { state: 'none', reason: null, detail: null }

// The Session's boards, driven by the enabled cameras merged with the Session's
// detections, groupings and holes by camera_alias: every enabled camera first
// (in camera order), then any other camera that still has a detection, Group or
// hole (one since deleted), and last the holes on no board, when there are any.
export function boardsOf(session: Session, cameras: Camera[] | undefined): Board[] {
  const enabled = (cameras ?? []).filter(c => c.enabled)
  const holes = session.bullet_holes ?? []
  const detections = session.detections ?? []
  const groupings = session.groupings ?? []
  const runs = session.runs ?? []

  const order = enabled.map(c => c.alias)
  const extra: string[] = []
  const add = (alias: string | null | undefined) => {
    if (alias != null && !order.includes(alias) && !extra.includes(alias)) extra.push(alias)
  }
  detections.forEach(d => add(d.camera_alias))
  groupings.forEach(g => add(g.camera_alias))
  holes.forEach(h => add(h.camera_alias))
  // A board a Run watched stays available even with no holes and its camera
  // since disabled or deleted, so a missed bullet can still be added to it
  runs.forEach(r => add(r.camera_alias))

  const boards: Board[] = [...order, ...extra].map(alias => ({
    alias,
    camera: enabled.find(c => c.alias === alias),
    detection: detections.find(d => d.camera_alias === alias)?.detection ?? NONE,
    grouping: groupings.find(g => g.camera_alias === alias)?.grouping,
    bullets: holes.filter(h => h.camera_alias === alias),
  }))

  // The holes on no board: shown only when there are any (or a Group for them)
  const noBoardHoles = holes.filter(h => h.camera_alias === null)
  const noBoardGrouping = groupings.find(g => g.camera_alias === null)?.grouping
  if (noBoardHoles.length > 0 || noBoardGrouping) {
    boards.push({ alias: null, detection: NONE, grouping: noBoardGrouping, bullets: noBoardHoles })
  }
  return boards
}
