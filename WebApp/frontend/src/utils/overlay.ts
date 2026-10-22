// Where the Overlay draws (ADR-0009). Pure, so node --test checks it:
// npm test

import type { BulletHole, Place, Run } from '../types'

export type Point = [number, number]

export interface Size {
  width: number
  height: number
}

// How far the video's proportions may stray from the picture's and still be
// the same picture: a decoder's few rows of padding, not another crop
const ASPECT_TOLERANCE = 0.01

// Maps a template point to element px: through `H`, a Run's
// template_to_picture, onto the baseline frame's `picture`, then into the
// rectangle object-contain shows the `video` in, inside an `element` of that
// size. Null while the video's size is unknown, or when its proportions
// differ from the picture's: then it is not the picture the Run saw.
export function templateToElement(
  H: number[][],
  picture: Size,
  video: Size,
  element: Size,
): ((p: Point) => Point) | null {
  if (!(video.width > 0 && video.height > 0)) return null
  const aspect = picture.width / picture.height
  if (Math.abs(video.width / video.height - aspect) > ASPECT_TOLERANCE * aspect) return null
  const scale = Math.min(element.width / video.width, element.height / video.height)
  const width = video.width * scale
  const height = video.height * scale
  const left = (element.width - width) / 2
  const top = (element.height - height) / 2
  return p => {
    const [px, py] = project(H, p)
    return [left + (px * width) / picture.width, top + (py * height) / picture.height]
  }
}

// Where a Run had the Board at the moment `at` (ms): the last place it kept
// at or before it (they are in time order). None before its baseline, nor
// after the latest Look the backend read from it, when it no longer watched
export function placeAt(run: Pick<Run, 'places' | 'watched_until'>, at: number): Place | null {
  if (at > Date.parse(run.watched_until)) return null
  return run.places.filter(p => Date.parse(p.at) <= at).pop() ?? null
}

// A point through a homography, perspective divide included
function project(H: number[][], [x, y]: Point): Point {
  const w = H[2][0] * x + H[2][1] * y + H[2][2]
  return [(H[0][0] * x + H[0][1] * y + H[0][2]) / w, (H[1][0] * x + H[1][1] * y + H[1][2]) / w]
}

// A homography's inverse up to scale, which the perspective divide cancels
function adjugate([[a, b, c], [d, e, f], [g, h, i]]: number[][]): number[][] {
  return [
    [e * i - f * h, c * h - b * i, b * f - c * e],
    [f * g - d * i, a * i - c * g, c * d - a * f],
    [d * h - e * g, b * g - a * h, a * e - b * d],
  ]
}

// The Run a Bullet Hole belongs to (ADR-0009), by its first_seen_at, the time
// the operator gave for a manual one: the latest of `runs` (in taken_at
// order) started at or before it, or the first, whose baseline saw a hole
// fired before it as a Baseline Mark
export function runOf<R extends Pick<Run, 'taken_at'>>(runs: R[], firstSeenAt: string): R | undefined {
  const seen = Date.parse(firstSeenAt)
  return runs.filter(r => Date.parse(r.taken_at) <= seen).pop() ?? runs[0]
}

type Carried = Pick<Run, 'taken_at' | 'baseline_view' | 'places'>
type Hole = Pick<BulletHole, 'first_seen_at' | 'position_x' | 'position_y'>

// How far the picture may carry an earlier Run's hole from the later Run's
// Baseline Mark of it, in template px: the Board's move between the two Runs,
// ~37 on CamA's creep across a 6.5 s restart (#246)
const CARRY_MATCH_TPL_PX = 60

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = sorted.length >> 1
  if (sorted.length === 0) return 0
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

// Run `from`'s template coordinates in Run `to`'s (ADR-0009). Each Run may hang
// them on another Target (#240), so a point goes onto the picture at `from`'s
// last place and back through `to`'s baseline. The Board moves in the picture
// between the two, so it is then shifted by the median offset from `from`'s
// holes (its Bullet Holes `holes` and its Baseline Marks) to the nearest of
// `to`'s Baseline Marks: `to`'s baseline saw each of them as one
// ponytail: one translation, so a Board turned or scaled between the Runs, or
// moved over CARRY_MATCH_TPL_PX, is not followed; fit the Runs' Target
// outlines if restarts show it
function carrier(from: Carried, to: Carried, holes: Point[]): (p: Point) => Point {
  const back = adjugate(to.baseline_view.template_to_picture)
  const last = from.places[from.places.length - 1].template_to_picture
  const through = (p: Point) => project(back, project(last, p))
  const offsets = [...holes, ...from.baseline_view.baseline_marks].map(through).flatMap(([x, y]) =>
    to.baseline_view.baseline_marks
      .map(([mx, my]): Point => [mx - x, my - y])
      .filter(([dx, dy]) => Math.hypot(dx, dy) < CARRY_MATCH_TPL_PX)
      .sort((a, b) => Math.hypot(...a) - Math.hypot(...b))
      .slice(0, 1),
  )
  const dx = median(offsets.map(o => o[0]))
  const dy = median(offsets.map(o => o[1]))
  return p => {
    const [x, y] = through(p)
    return [x + dx, y + dy]
  }
}

// Each Bullet Hole's position in Run `run`'s template coordinates: as stored
// over the Run it belongs to (runOf), carried over from an earlier one
export function holesOver<R extends Carried>(run: R, runs: R[], bullets: Hole[]): Point[] {
  const owners = bullets.map(b => runOf(runs, b.first_seen_at) ?? run)
  const positions = bullets.map((b): Point => [b.position_x, b.position_y])
  const carriers = new Map(
    [...new Set(owners)]
      .filter(owner => owner.taken_at !== run.taken_at)
      .map(owner => [owner, carrier(owner, run, positions.filter((_, i) => owners[i] === owner))] as const),
  )
  return positions.map((p, i) => carriers.get(owners[i])?.(p) ?? p)
}

// How near a Baseline Mark must be to a Bullet Hole to be the same hole, in
// template px: the Detection Service's MATCH_TPL_PX
const MATCH_TPL_PX = 20

// The Baseline Marks drawn: those no Bullet Hole drawn over the same Run
// stands for, by the Detection Service's own test (`strip_pre_existing`)
export function baselineMarksToDraw(marks: Point[], holes: Point[]): Point[] {
  return marks.filter(([x, y]) => holes.every(([hx, hy]) => Math.hypot(x - hx, y - hy) >= MATCH_TPL_PX))
}

// Markers whose numbers would overlap on screen, so each group gets one label
// listing its ranks: the indices of `points` (element px) linked by gaps under
// `px`, a chain included, each group in the order of `points`
export function labelGroups(points: Point[], px: number): number[][] {
  const grouped = new Set<number>()
  const groups: number[][] = []
  points.forEach((_, first) => {
    if (grouped.has(first)) return
    grouped.add(first)
    const group = [first]
    for (let k = 0; k < group.length; k++) {
      const [x, y] = points[group[k]]
      points.forEach(([ox, oy], i) => {
        if (!grouped.has(i) && Math.hypot(x - ox, y - oy) < px) {
          grouped.add(i)
          group.push(i)
        }
      })
    }
    groups.push(group.sort((a, b) => a - b))
  })
  return groups
}
