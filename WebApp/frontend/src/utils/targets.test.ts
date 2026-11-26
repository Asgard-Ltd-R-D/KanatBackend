import { test } from 'node:test'
import assert from 'node:assert/strict'
import { project, type Point } from './overlay.ts'
import { millimetres, pixelToTemplate, targetOfPoint } from './targets.ts'

const H = [[2, 0.1, 30], [0.05, 1.8, 40], [0.0001, 0.0002, 1]]

test('pixelToTemplate inverts template_to_picture', () => {
  const template: Point = [120, 75]
  const [x, y] = pixelToTemplate(H, project(H, template))
  assert.ok(Math.abs(x - 120) < 1e-6 && Math.abs(y - 75) < 1e-6, `${x},${y}`)
})

const sheets: [Point, Point][] = [[[0, 0], [100, 100]], [[50, 0], [200, 100]]]

test('targetOfPoint: inside sheet 1 only', () => assert.equal(targetOfPoint(sheets, [150, 50]), 1))
test('targetOfPoint: overlap goes to the lowest index', () => assert.equal(targetOfPoint(sheets, [75, 50]), 0))
test('targetOfPoint: an outline holding the point beats an overlapping lower sheet', () => {
  // (75, 50) is in both sheets, but inside Target 1's printed outline
  const outlines: Point[][] = [[[10, 10], [40, 10], [40, 90], [10, 90]], [[60, 10], [190, 10], [190, 90], [60, 90]]]
  assert.equal(targetOfPoint(sheets, [75, 50], outlines), 1)
})
test('targetOfPoint: on an outline edge counts as inside', () => {
  const outlines: Point[][] = [[[10, 10], [40, 10], [40, 90], [10, 90]], [[60, 10], [190, 10], [190, 90], [60, 90]]]
  assert.equal(targetOfPoint(sheets, [60, 50], outlines), 1)
})
test('targetOfPoint: off every outline, the sheet rule as before', () => {
  const outlines: Point[][] = [[[10, 10], [40, 10], [40, 90], [10, 90]], [[120, 10], [190, 10], [190, 90], [120, 90]]]
  assert.equal(targetOfPoint(sheets, [75, 50], outlines), 0)
})
test('targetOfPoint: outside all', () => assert.equal(targetOfPoint(sheets, [300, 50]), null))

test('millimetres flips Y to the printed axes', () => {
  const m = millimetres([100, 100], 1, [110, 90])
  assert.ok(m.x_mm > 0 && m.y_mm > 0)
})

test('millimetres at the ring centre is zero', () => {
  assert.deepEqual(millimetres([100, 100], 0.1763, [100, 100]), { x_mm: 0, y_mm: 0 })
})

test('millimetres scales by mmPerPx', () => {
  const m = millimetres([100, 100], 0.1763, [200, 0])
  assert.ok(Math.abs(m.x_mm - 17.63) < 1e-9 && Math.abs(m.y_mm - 17.63) < 1e-9)
})
