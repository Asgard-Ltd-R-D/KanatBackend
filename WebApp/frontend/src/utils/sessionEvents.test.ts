import { test } from 'node:test'
import assert from 'node:assert/strict'
import { applyEvent, removeBullet, upsertBullet } from './sessionEvents.ts'

// Only what the functions read: the rest of a hole or a Session is not their concern
const hole = (id: string, rank: number, camera_alias: string | null = 'lane1') =>
  ({ id, rank, camera_alias, first_seen_at: '2026-11-22T10:00:00Z' }) as never
const session = (holes: unknown[]) => ({ id: 's1', name: 'Range', bullet_holes: holes }) as never
const ranks = (s: { bullet_holes?: { id: string; rank: number }[] }) =>
  (s.bullet_holes ?? []).map((b) => `${b.id}:${b.rank}`)

test('a new hole that moved none of the others is added at its rank', () => {
  const next = upsertBullet(session([hole('a', 1), hole('b', 2)]), hole('c', 3))
  assert.deepEqual(ranks(next), ['a:1', 'b:2', 'c:3'])
})

test('a hole seen before the others moves their ranks down, so none shows twice', () => {
  // The backend ranked the new hole 1, and moved a and b to 2 and 3
  const next = upsertBullet(session([hole('a', 1), hole('b', 2)]), hole('c', 1), true)
  assert.deepEqual(ranks(next), ['c:1', 'a:2', 'b:3'])
})

test('a hole slotted between two others moves only the ones from its rank on', () => {
  const next = upsertBullet(session([hole('a', 1), hole('b', 2), hole('c', 3)]), hole('d', 2), true)
  assert.deepEqual(ranks(next), ['a:1', 'd:2', 'b:3', 'c:4'])
})

test('only the new hole\'s own board moves', () => {
  const held = session([hole('a', 1), hole('x', 1, 'lane2'), hole('y', 2, 'lane2')])
  const next = upsertBullet(held, hole('c', 1), true)
  assert.deepEqual((next as { bullet_holes: { id: string; rank: number; camera_alias: string }[] }).bullet_holes
    .filter((b) => b.camera_alias === 'lane2').map((b) => `${b.id}:${b.rank}`), ['x:1', 'y:2'])
  assert.deepEqual(ranks(next).filter((r) => r.startsWith('a') || r.startsWith('c')), ['c:1', 'a:2'])
})

test('a hole already held (a retried post) is replaced and moves nothing, renumbered or not', () => {
  const held = session([hole('a', 1), hole('b', 2)])
  assert.deepEqual(ranks(upsertBullet(held, hole('a', 1), true)), ['a:1', 'b:2'])
})

test('a delete moves the later holes of its board up, as the backend does', () => {
  const next = removeBullet(session([hole('a', 1), hole('b', 2), hole('c', 3)]), 'b')
  assert.deepEqual(ranks(next), ['a:1', 'c:2'])
})

test('a bullet_created event carries its renumbering to the Session', () => {
  const next = applyEvent(session([hole('a', 1)]), { type: 'bullet_created', bullet: hole('c', 1), renumbered: true })
  assert.deepEqual(ranks(next), ['c:1', 'a:2'])
  const plain = applyEvent(session([hole('a', 1)]), { type: 'bullet_created', bullet: hole('c', 2) })
  assert.deepEqual(ranks(plain), ['a:1', 'c:2'])
})
