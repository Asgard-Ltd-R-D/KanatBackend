import { test } from 'node:test'
import assert from 'node:assert/strict'
import { findMoment, summarize } from './recordings.ts'
import type { CameraRecording } from '../types'

// Two 60s parts that meet exactly (contiguous), then a third after a 5s gap
const rec = (over: Partial<CameraRecording> = {}): CameraRecording => ({
  alias: 'lane1',
  spans: [
    { start: '2026-10-22T10:00:00.000Z', duration_s: 60 },  // part 0: 10:00:00 – 10:01:00
    { start: '2026-10-22T10:01:00.000Z', duration_s: 60 },  // part 1: 10:01:00 – 10:02:00 (contiguous)
    { start: '2026-10-22T10:02:05.000Z', duration_s: 60 },  // part 2: 10:02:05 – 10:03:05 (5s gap before)
  ],
  ...over,
})

test('a moment finds the part it falls in', () => {
  assert.deepEqual(findMoment([rec()], '2026-10-22T10:01:30.000Z'), { alias: 'lane1', part: 1, offsetS: 30 })
})

test('preroll crosses a contiguous part boundary into the earlier part', () => {
  // 2s into part 1, with 5s preroll: should land 3s before the end of part 0
  const moment = findMoment([rec()], '2026-10-22T10:01:02.000Z', 5)
  assert.deepEqual(moment, { alias: 'lane1', part: 0, offsetS: 57 })
})

test('preroll does not cross a real gap between parts', () => {
  // 2s into part 2, 5s preroll: the 5s gap before it is not contiguous, so it
  // clamps to the start of part 2 (offset 0), not into part 1
  const moment = findMoment([rec()], '2026-10-22T10:02:07.000Z', 5)
  assert.deepEqual(moment, { alias: 'lane1', part: 2, offsetS: 0 })
})

test('a moment no camera was recording returns null', () => {
  assert.equal(findMoment([rec()], '2026-10-22T10:02:02.000Z'), null)  // in the 5s gap
  assert.equal(findMoment([], '2026-10-22T10:01:30.000Z'), null)       // no recordings
})

test('summarize gives the span from the first start to the last end, and total recorded', () => {
  const s = summarize(rec())
  assert.equal(s.from, '2026-10-22T10:00:00.000Z')
  assert.equal(s.to, '2026-10-22T10:03:05.000Z')
  assert.equal(s.recordedS, 180)
})
