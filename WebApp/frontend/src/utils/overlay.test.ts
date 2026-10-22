import { test } from 'node:test'
import assert from 'node:assert/strict'
import { baselineMarksToDraw, templateToElement, type Point } from './overlay.ts'

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
