import { test } from 'node:test'
import assert from 'node:assert/strict'
import { baselineMarksToDraw, holesOver, labelGroups, placeAt, runOf, templateToElement, type Point } from './overlay.ts'

const IDENTITY = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
const FULL_HD = { width: 1920, height: 1080 }

function near(actual: Point | undefined, expected: Point) {
  assert.ok(actual, 'no mapping')
  assert.ok(
    Math.abs(actual[0] - expected[0]) < 1e-9 && Math.abs(actual[1] - expected[1]) < 1e-9,
    `${actual} is not ${expected}`,
  )
}

test('the identity homography with no letterbox scales the picture to the element', () => {
  const toElement = templateToElement(IDENTITY, FULL_HD, FULL_HD, { width: 960, height: 540 })
  near(toElement?.([100, 200]), [50, 100])
})

test('a smaller video of the same picture is scaled from the picture, not the video', () => {
  const toElement = templateToElement(IDENTITY, FULL_HD, { width: 1280, height: 720 }, { width: 640, height: 360 })
  near(toElement?.([1920, 1080]), [640, 360])
})

test('a wider element pillar-boxes the picture: offset by half the bars', () => {
  const toElement = templateToElement(IDENTITY, FULL_HD, FULL_HD, { width: 1000, height: 540 })
  near(toElement?.([0, 0]), [20, 0])
  near(toElement?.([100, 200]), [70, 100])
})

test('a taller element letter-boxes the picture: offset by half the bars', () => {
  const toElement = templateToElement(IDENTITY, FULL_HD, FULL_HD, { width: 960, height: 740 })
  near(toElement?.([0, 0]), [0, 100])
  near(toElement?.([100, 200]), [50, 200])
})

test('a non-trivial homography goes through its perspective divide', () => {
  // (1000, 200) -> (2 * 1000 + 100, 2 * 200 + 50) / (0.001 * 1000 + 1) = (1050, 225) on the picture
  const H = [[2, 0, 100], [0, 2, 50], [0.001, 0, 1]]
  const toElement = templateToElement(H, FULL_HD, FULL_HD, { width: 960, height: 540 })
  near(toElement?.([1000, 200]), [525, 112.5])
})

test('a video whose proportions differ from the picture maps nothing', () => {
  assert.equal(templateToElement(IDENTITY, FULL_HD, { width: 1440, height: 1080 }, { width: 960, height: 540 }), null)
})

test('a video not loaded yet maps nothing', () => {
  assert.equal(templateToElement(IDENTITY, FULL_HD, { width: 0, height: 0 }, { width: 960, height: 540 }), null)
})

test('a Baseline Mark within 20 template px of a drawn Bullet Hole is dropped, one further away is kept', () => {
  const holes: Point[] = [[100, 100], [900, 500]]
  const marks: Point[] = [[112, 115], [100, 120], [900, 470]]
  // 19.2 px off the first hole: the hole stands for it. 20 px off it, and
  // 30 px off the second, they are other holes
  assert.deepEqual(baselineMarksToDraw(marks, holes), [[100, 120], [900, 470]])
})

test('with no Bullet Hole drawn every Baseline Mark is', () => {
  assert.deepEqual(baselineMarksToDraw([[1, 2]], []), [[1, 2]])
})

test('markers whose numbers would overlap share one label, one further away keeps its own', () => {
  assert.deepEqual(labelGroups([[0, 0], [10, 0], [100, 0]], 18), [[0, 1], [2]])
})

test('a chain of close markers shares one label, though its ends are further apart', () => {
  assert.deepEqual(labelGroups([[0, 0], [100, 0], [15, 0], [30, 0]], 18), [[0, 2, 3], [1]])
})

// A Run that kept its baseline's place at 10:00:00 and moved at 10:00:20,
// and whose latest Look the backend read was at 10:01:00
const BASELINE = { at: '2026-10-22T10:00:00Z', template_to_picture: IDENTITY }
const MOVED = { at: '2026-10-22T10:00:20Z', template_to_picture: [[1, 0, 5], [0, 1, 0], [0, 0, 1]] }
const RUN = { places: [BASELINE, MOVED], watched_until: '2026-10-22T10:01:00Z' }
const at = (iso: string) => Date.parse(iso)

test('the place at a moment is the last kept at or before it', () => {
  assert.equal(placeAt(RUN, at('2026-10-22T10:00:00Z')), BASELINE)
  assert.equal(placeAt(RUN, at('2026-10-22T10:00:19.999Z')), BASELINE)
  assert.equal(placeAt(RUN, at('2026-10-22T10:00:20Z')), MOVED)
  assert.equal(placeAt(RUN, at('2026-10-22T10:01:00Z')), MOVED)
})

test('there is no place before the first kept, nor after watched_until', () => {
  assert.equal(placeAt(RUN, at('2026-10-22T09:59:59.999Z')), null)
  assert.equal(placeAt(RUN, at('2026-10-22T10:01:00.001Z')), null)
})

// Two Runs of one Session: the first from 10:00, the second, after a restart,
// from 10:05
const run = (taken_at: string, baseline: number[][], last = baseline) => ({
  taken_at,
  baseline_view: { taken_at, picture: FULL_HD, template_to_picture: baseline, targets: [], baseline_marks: [] as Point[] },
  places: [{ at: taken_at, template_to_picture: baseline }, { at: taken_at, template_to_picture: last }],
  watched_until: taken_at,
  camera_alias: 'cam',
})
const FIRST = run('2026-10-22T10:00:00Z', IDENTITY)
const SECOND = run('2026-10-22T10:05:00Z', IDENTITY)

test('a Bullet Hole belongs to the latest Run started at or before its first_seen_at', () => {
  assert.equal(runOf([FIRST, SECOND], '2026-10-22T10:04:59.999Z'), FIRST)
  assert.equal(runOf([FIRST, SECOND], '2026-10-22T10:05:00Z'), SECOND)
  assert.equal(runOf([FIRST, SECOND], '2026-10-22T10:30:00Z'), SECOND)
})

test('a Bullet Hole from before the first Run belongs to the first Run', () => {
  assert.equal(runOf([FIRST, SECOND], '2026-10-22T09:59:00Z'), FIRST)
})

// The first Run last had its Target 10 px right of its baseline; the second
// registered to the other Target, at half the scale and in perspective
const EARLIER = run('2026-10-22T10:00:00Z', IDENTITY, [[1, 0, 10], [0, 1, 0], [0, 0, 1]])
const OTHER_TARGET = [[0.5, 0, 600], [0, 0.5, 100], [0.0001, 0, 1]]
const LATER = run('2026-10-22T10:05:00Z', OTHER_TARGET)
const hole = (first_seen_at: string, [position_x, position_y]: Point) => ({ first_seen_at, position_x, position_y })
const EARLIER_HOLES = [hole('2026-10-22T10:01:00Z', [200, 300]), hole('2026-10-22T10:02:00Z', [400, 300]), hole('2026-10-22T10:03:00Z', [300, 500])]

test('a Bullet Hole of an earlier Run that registered to the other Target lands where that Run placed it on the picture', () => {
  const [carried] = holesOver(LATER, [EARLIER, LATER], EARLIER_HOLES)
  // Where the earlier Run last placed it: (200 + 10, 300)
  near(templateToElement(OTHER_TARGET, FULL_HD, FULL_HD, FULL_HD)?.(carried), [210, 300])
})

test('over its own Run a Bullet Hole is not carried', () => {
  assert.deepEqual(holesOver(EARLIER, [EARLIER, LATER], EARLIER_HOLES), [[200, 300], [400, 300], [300, 500]])
})

// The camera crept between the two Runs: the later one's baseline saw each
// of the earlier one's Bullet Holes 30 template px right and 20 down of where
// the picture carries them, and one other hole far from all of them
const THROUGH_PICTURE = holesOver(LATER, [EARLIER, LATER], EARLIER_HOLES)
const CREPT_LATER = run('2026-10-22T10:05:00Z', OTHER_TARGET)
CREPT_LATER.baseline_view.baseline_marks = [...THROUGH_PICTURE.map(([x, y]): Point => [x + 30, y + 20]), [THROUGH_PICTURE[0][0] + 500, THROUGH_PICTURE[0][1]]]

test('an earlier Run\'s Bullet Hole lands on the later Run\'s Baseline Mark of it, though the camera crept between the Runs', () => {
  const carried = holesOver(CREPT_LATER, [EARLIER, CREPT_LATER], EARLIER_HOLES)
  carried.forEach((p, i) => near(p, CREPT_LATER.baseline_view.baseline_marks[i]))
})

test("a later Run's Baseline Mark that matches an earlier Run's carried Bullet Hole is dropped", () => {
  const carried = holesOver(CREPT_LATER, [EARLIER, CREPT_LATER], EARLIER_HOLES)
  assert.deepEqual(baselineMarksToDraw(CREPT_LATER.baseline_view.baseline_marks, carried), [[THROUGH_PICTURE[0][0] + 500, THROUGH_PICTURE[0][1]]])
})

test("a tight Group's Bullet Holes land on their own Baseline Marks, not their neighbours'", () => {
  // 25 template px apart, and the camera crept 37 between the Runs: each but
  // the first is nearer its neighbour's mark than its own
  const early = run('2026-10-22T10:00:00Z', IDENTITY)
  const late = run('2026-10-22T10:05:00Z', IDENTITY)
  const group: Point[] = [[100, 100], [125, 100], [150, 100], [175, 100]]
  late.baseline_view.baseline_marks = group.map(([x, y]): Point => [x + 37, y])
  const carried = holesOver(late, [early, late], group.map(p => hole('2026-10-22T10:01:00Z', p)))
  carried.forEach((p, i) => near(p, late.baseline_view.baseline_marks[i]))
})

test("Bullet Holes nearer an unrelated Baseline Mark than their own still land on their own", () => {
  // The camera crept 40 between the Runs, and the later baseline also saw a
  // hole 10 and one 20 right of where the picture carries them
  const early = run('2026-10-22T10:00:00Z', IDENTITY)
  const late = run('2026-10-22T10:05:00Z', IDENTITY)
  late.baseline_view.baseline_marks = [[110, 100], [140, 100], [220, 100], [240, 100]]
  const carried = holesOver(late, [early, late], [hole('2026-10-22T10:01:00Z', [100, 100]), hole('2026-10-22T10:02:00Z', [200, 100])])
  near(carried[0], [140, 100])
  near(carried[1], [240, 100])
})
