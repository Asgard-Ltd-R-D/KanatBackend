"""Group statistics for one Range (SOW 2.1.3): MPI, CEP, Mean Radius, RMS radius
and Extreme Spread, per Target. Vocabulary in CONTEXT.md.

The method is fixed, and recorded as a default pending the customer's
confirmation (Asgard reply, 2.1.3):

- MPI: the mean of the Group's millimetre positions.
- CEP: empirical CEP50, the median distance from the MPI.
- Mean Radius and RMS radius: the mean and root-mean-square of those distances.
- Extreme Spread: centre to centre. Calibre is unknown here, so not subtracted.

Pure: no I/O, so the SOW 2.4.1 report can reuse it on any (operator-corrected)
set of Bullet Holes.
"""
import itertools
import math
import statistics


def groups(holes):
    """Each Target's Group statistics, and how many Misses were left out.

    `holes` are reported Bullet Holes: dicts with "target" (an index, or None
    for a Miss) and "mm" (X, Y offset from that Target's centre, Y up). Returns
    `({target: {"n", "mpi", "cep", "mean_radius", "rms_radius", "extreme_spread"}},
    misses)`. A Target with no Bullet Holes has no entry; below two Bullet
    Holes every spread measure is None.
    """
    by_target = {}
    for hole in holes:
        if hole["target"] is not None:
            by_target.setdefault(hole["target"], []).append(tuple(map(float, hole["mm"])))
    misses = sum(1 for hole in holes if hole["target"] is None)
    return {t: _group(pts) for t, pts in sorted(by_target.items())}, misses


def _group(pts):
    n = len(pts)
    mpi = (sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n)
    stats = {"n": n, "mpi": mpi, "cep": None, "mean_radius": None, "rms_radius": None,
             "extreme_spread": None}
    if n >= 2:
        r = [math.dist(p, mpi) for p in pts]
        stats.update(cep=statistics.median(r), mean_radius=statistics.fmean(r),
                     rms_radius=math.sqrt(statistics.fmean(d * d for d in r)),
                     extreme_spread=max(math.dist(a, b)
                                        for a, b in itertools.combinations(pts, 2)))
    return stats
