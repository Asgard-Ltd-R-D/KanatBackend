"""Bullet Hole positions carried between Runs' template coordinates (ADR-0009).

Each Run may hang its template coordinates on another Target (#240), so a hole
stored over an earlier Run is first carried into the latest Run's space before
it is drawn over that Run's baseline frame. A port of the frontend's
`utils/overlay.ts` (`runOf`, `holesOver` and its carrier), which the live
Overlay and the add-bullet modal use: the PDF places the holes where they do.
"""
import math
import statistics

Point = tuple[float, float]

# How near a Baseline Mark must be to a Bullet Hole to be the same hole, in
# template px: the Detection Service's MATCH_TPL_PX
MATCH_TPL_PX = 20
# How far the picture may carry an earlier Run's Bullet Hole from the later
# Run's Baseline Mark of it, in template px (#246)
CARRY_MATCH_TPL_PX = 60


def project(matrix, p: Point) -> Point | None:
    """A point through a 3x3 homography; None on its line at infinity."""
    x, y = p
    w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    if abs(w) < 1e-9:
        return None
    return ((matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / w,
            (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / w)


def adjugate(m):
    """The 3x3 adjugate: the inverse up to scale, which a homography ignores."""
    (a, b, c), (d, e, f), (g, h, i) = m
    return [
        [e * i - f * h, c * h - b * i, b * f - c * e],
        [f * g - d * i, a * i - c * g, c * d - a * f],
        [d * h - e * g, b * g - a * h, a * e - b * d],
    ]


def run_of(runs: list, first_seen_at):
    """The Run a Bullet Hole belongs to: the latest of `runs` (in taken_at
    order) started at or before it, or the first, whose baseline saw a hole
    fired before it as a Baseline Mark."""
    owner = None
    for run in runs:
        if run.taken_at <= first_seen_at:
            owner = run
    return owner or runs[0]


def _carrier(src, dst, holes: list[Point]):
    """Run `src`'s template coordinates in Run `dst`'s: onto the picture at
    `src`'s last place, back through `dst`'s baseline, then shifted by the
    offset to `dst`'s Baseline Marks that the most points agree on (the
    camera creeps between Runs), refined to the median of theirs."""
    back = adjugate(dst.baseline_view["template_to_picture"])
    places = src.places or []
    last = places[-1]["template_to_picture"] if places else src.baseline_view["template_to_picture"]

    def through(p: Point) -> Point | None:
        on_picture = project(last, p)
        return project(back, on_picture) if on_picture is not None else None

    marks = [tuple(m) for m in dst.baseline_view.get("baseline_marks") or []]
    points = [q for q in (through(p) for p in [*holes, *(tuple(m) for m in src.baseline_view.get("baseline_marks") or [])])
              if q is not None]
    offsets = [[(mx - x, my - y) for mx, my in marks if math.hypot(mx - x, my - y) < CARRY_MATCH_TPL_PX + MATCH_TPL_PX]
               for x, y in points]

    def agreeing(shift: Point) -> list[tuple[Point, float]]:
        sx, sy = shift
        out = []
        for own in offsets:
            nearest = None
            for offset in own:
                stray = math.hypot(offset[0] - sx, offset[1] - sy)
                if stray < MATCH_TPL_PX and (nearest is None or stray < nearest[1]):
                    nearest = (offset, stray)
            if nearest:
                out.append(nearest)
        return out

    candidates = [o for own in offsets
                  for o in sorted((o for o in own if math.hypot(*o) < CARRY_MATCH_TPL_PX), key=lambda o: math.hypot(*o))]
    best: list[tuple[Point, float]] = []
    for candidate in candidates:
        found = agreeing(candidate)
        if len(found) > len(best) or (len(found) == len(best) and sum(s for _, s in found) < sum(s for _, s in best)):
            best = found
    dx = statistics.median(o[0] for o, _ in best) if best else 0.0
    dy = statistics.median(o[1] for o, _ in best) if best else 0.0

    def carry(p: Point) -> Point:
        q = through(p)
        return (q[0] + dx, q[1] + dy) if q is not None else p
    return carry


def holes_over(run, runs: list, holes) -> list[Point]:
    """Each Bullet Hole's position in Run `run`'s template coordinates: as
    stored over the Run it belongs to (run_of), carried over from an earlier
    one. `runs` is the board's Runs in taken_at order; without any, as stored."""
    positions = [(h.position_x, h.position_y) for h in holes]
    if not runs:
        return positions
    owners = [run_of(runs, h.first_seen_at) for h in holes]
    carriers = {}
    for owner in {id(o): o for o in owners}.values():
        if owner.taken_at != run.taken_at:
            own = [p for p, o in zip(positions, owners) if o is owner]
            carriers[id(owner)] = _carrier(owner, run, own)
    return [carriers[id(o)](p) if id(o) in carriers else p for p, o in zip(positions, owners)]
