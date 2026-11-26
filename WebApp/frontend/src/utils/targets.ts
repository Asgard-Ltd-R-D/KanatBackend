// Attributing a manually placed shot to a target. Pure, so node --test checks it.

import { adjugate, project, type Point } from './overlay.ts'

// Picture px -> template point: the inverse of a Run's template_to_picture
export function pixelToTemplate(H: number[][], px: Point): Point {
  return project(adjugate(H), px)
}

// Whether `p` lies inside `polygon` or on its edge (even-odd ray cast)
function inPolygon(polygon: Point[], [x, y]: Point): boolean {
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    // On the edge counts as inside, as the detector's pointPolygonTest >= 0
    const cross = (xj - xi) * (y - yi) - (yj - yi) * (x - xi)
    if (Math.abs(cross) < 1e-9 && x >= Math.min(xi, xj) && x <= Math.max(xi, xj) &&
        y >= Math.min(yi, yj) && y <= Math.max(yi, yj)) return true
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

// The Target a shot at `p` is on, by the detector's rule (ADR-0014,
// board.py `assign`): the lowest-index Target whose outline holds it, else
// the lowest-index sheet (a pair of opposite corners) whose bound does; null
// beyond every sheet. Sheets grow 5 mm past the print, so neighbours overlap:
// the outline decides first.
export function targetOfPoint(sheets: [Point, Point][], p: Point, outlines: Point[][] = []): number | null {
  const outline = outlines.findIndex(o => o.length > 2 && inPolygon(o, p))
  if (outline >= 0) return outline
  const i = sheets.findIndex(([a, b]) =>
    p[0] >= Math.min(a[0], b[0]) && p[0] <= Math.max(a[0], b[0]) &&
    p[1] >= Math.min(a[1], b[1]) && p[1] <= Math.max(a[1], b[1]))
  return i < 0 ? null : i
}

// Picture px -> mm from the ring centre, Y flipped to the printed axes
export function millimetres(ringCentre: Point, mmPerPx: number, p: Point): { x_mm: number; y_mm: number } {
  return { x_mm: (p[0] - ringCentre[0]) * mmPerPx, y_mm: (ringCentre[1] - p[1]) * mmPerPx }
}
