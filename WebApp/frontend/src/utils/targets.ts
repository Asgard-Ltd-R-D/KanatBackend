// Attributing a manually placed shot to a target. Pure, so node --test checks it.

import { adjugate, project, type Point } from './overlay.ts'

// Picture px -> template point: the inverse of a Run's template_to_picture
export function pixelToTemplate(H: number[][], px: Point): Point {
  return project(adjugate(H), px)
}

// Index of the lowest-index sheet (a pair of opposite corners) holding `p`
export function targetOfPoint(sheets: [Point, Point][], p: Point): number | null {
  const i = sheets.findIndex(([a, b]) =>
    p[0] >= Math.min(a[0], b[0]) && p[0] <= Math.max(a[0], b[0]) &&
    p[1] >= Math.min(a[1], b[1]) && p[1] <= Math.max(a[1], b[1]))
  return i < 0 ? null : i
}

// Picture px -> mm from the ring centre, Y flipped to the printed axes
export function millimetres(ringCentre: Point, mmPerPx: number, p: Point): { x_mm: number; y_mm: number } {
  return { x_mm: (p[0] - ringCentre[0]) * mmPerPx, y_mm: (ringCentre[1] - p[1]) * mmPerPx }
}
