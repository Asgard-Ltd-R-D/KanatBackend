"""A Session's Group statistics (SOW 2.1.3): MPI, CEP, Mean Radius, RMS radius
and Extreme Spread, per Target. Vocabulary in the root CONTEXT.md.

Ported from ImageRecognitionService/detection/groups.py, which this package
cannot import; tests/test_groups.py uses its hand-computed points. The method
is a default pending the customer's confirmation (#76):

- MPI: the mean of the Group's millimetre positions.
- CEP: empirical CEP50, the median distance from the MPI.
- Mean Radius and RMS radius: the mean and root-mean-square of those distances.
- Extreme Spread: centre to centre. Calibre is unknown here, so not subtracted.
"""
import itertools
import math
import statistics

from app.schemas.session import Group, Grouping


def grouping(holes) -> Grouping:
    """The Groups of `holes`, the Session's non-deleted Bullet Holes, so the
    operator's corrections apply. A Group is the Bullet Holes that share a
    target_index and have both x_mm and y_mm. A Miss (a detected one with no
    Target) is in none; neither is one without a Position: every manual one,
    whose form takes no Target or millimetres, and a detected one without a
    print scale."""
    by_target: dict[int, list[tuple[float, float]]] = {}
    misses = without_position = 0
    for hole in holes:
        if hole.target_index is not None and hole.x_mm is not None and hole.y_mm is not None:
            by_target.setdefault(hole.target_index, []).append((hole.x_mm, hole.y_mm))
        elif hole.target_index is None and hole.source == "model":
            misses += 1
        else:
            without_position += 1
    return Grouping(groups=[_group(t, pts) for t, pts in sorted(by_target.items())],
                    misses=misses, without_position=without_position)


def _group(target_index: int, pts: list[tuple[float, float]]) -> Group:
    n = len(pts)
    mpi = (sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n)
    group = Group(target_index=target_index, n=n, mpi_x_mm=mpi[0], mpi_y_mm=mpi[1])
    if n >= 2:
        r = [math.dist(p, mpi) for p in pts]
        group.cep_mm = statistics.median(r)
        group.mean_radius_mm = statistics.fmean(r)
        group.rms_radius_mm = math.sqrt(statistics.fmean(d * d for d in r))
        group.extreme_spread_mm = max(math.dist(a, b) for a, b in itertools.combinations(pts, 2))
    return group
