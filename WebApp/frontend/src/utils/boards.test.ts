import { test } from 'node:test'
import assert from 'node:assert/strict'
import { boardsOf } from './boards.ts'
import type { BulletHole, Camera, Run, Session } from '../types'

function camera(alias: string, enabled = true): Camera {
  return { id: alias, alias, mcast_ip: '224.0.0.1', mcast_port: 5000, iface: null, enabled, created_at: '', status: 'live' }
}

function run(camera_alias: string): Run {
  return { camera_alias, taken_at: '', watched_until: '', baseline_view: {} as unknown as Run['baseline_view'], places: [] }
}

function hole(camera_alias: string | null, rank: number): BulletHole {
  return {
    id: `b${rank}`, session_id: 's', camera_alias, rank, first_seen_at: '', position_x: 0, position_y: 0,
    target_index: null, x_mm: null, y_mm: null, source: 'model', created_at: '',
  }
}

function session(partial: Partial<Session>): Session {
  return {
    id: 's', name: 'S', status: 'active', started_at: '', ended_at: null, created_at: '', ...partial,
  }
}

test('every enabled camera is a board, in camera order, "none" when it has no detection entry yet', () => {
  const boards = boardsOf(session({ detections: [{ camera_alias: 'camB', detection: { state: 'watching', reason: null, detail: null } }] }), [camera('camA'), camera('camB')])
  assert.deepEqual(boards.map(b => b.alias), ['camA', 'camB'])
  assert.equal(boards[0].detection.state, 'none')
  assert.equal(boards[1].detection.state, 'watching')
})

test('a disabled camera is not a board unless it still has holes', () => {
  const boards = boardsOf(session({ bullet_holes: [hole('camA', 1)] }), [camera('camA', false)])
  assert.deepEqual(boards.map(b => b.alias), ['camA'])
  assert.equal(boards[0].camera, undefined) // no enabled camera backs it
  assert.equal(boards[0].bullets.length, 1)
})

test('holes and groupings are matched to their board by camera_alias', () => {
  const boards = boardsOf(
    session({
      bullet_holes: [hole('camA', 1), hole('camB', 2), hole('camA', 3)],
      groupings: [{ camera_alias: 'camA', grouping: { groups: [], misses: 1, without_position: 0 } }],
    }),
    [camera('camA'), camera('camB')],
  )
  assert.deepEqual(boards.find(b => b.alias === 'camA')?.bullets.map(h => h.rank), [1, 3])
  assert.deepEqual(boards.find(b => b.alias === 'camB')?.bullets.map(h => h.rank), [2])
  assert.equal(boards.find(b => b.alias === 'camA')?.grouping?.misses, 1)
})

test('a board a run watched stays available with no holes even if its camera is gone', () => {
  const boards = boardsOf(session({ status: 'completed', runs: [run('camC')] }), [camera('camA')])
  assert.deepEqual(boards.map(b => b.alias), ['camA', 'camC'])
  assert.equal(boards.find(b => b.alias === 'camC')?.bullets.length, 0)
  assert.equal(boards.find(b => b.alias === 'camC')?.camera, undefined) // no enabled camera backs it
})

test('holes on no board become a last board with alias null, only when present', () => {
  assert.deepEqual(boardsOf(session({ bullet_holes: [hole('camA', 1)] }), [camera('camA')]).map(b => b.alias), ['camA'])
  const boards = boardsOf(session({ bullet_holes: [hole('camA', 1), hole(null, 2)] }), [camera('camA')])
  assert.deepEqual(boards.map(b => b.alias), ['camA', null])
  assert.equal(boards[1].bullets[0].rank, 2)
})
