"""The scoring-ring radii, read off the Target artwork (#70).

Rays are traced out from `RING_CENTRE_TPL` every half degree, sampled at a
quarter pixel. On each ray:

- the white 10-ring's edge is where the profile first drops through the level
  halfway between the white disk and the green around it;
- each ring line is a run above that level, at most 6 px wide (wider runs are
  the numerals), and its radius is the run's centre. A run belongs to the
  nearest `RING_RADII_TPL` line, so re-running converges on the same values.

Each value is the median over the rays, so numerals and the silhouette, which
cut the outer rings off on some rays, do not move it. The artwork's rings are
~2% taller than wide; a median radius is the circle `score()` uses.

    .venv/bin/python -m tools.ring_landmarks
"""
import cv2
import numpy as np

from detection.board import DEFAULT_TEMPLATE, RING_CENTRE_TPL, RING_RADII_TPL

WHITE, GREEN = 253, 84  # the artwork's disk and background levels
HALF = (WHITE + GREEN) / 2


def measure(template=DEFAULT_TEMPLATE):
    """(10-ring edge radius, (ring line radii...)) in template px."""
    grey = cv2.imread(template, cv2.IMREAD_GRAYSCALE).astype(np.float32)
    r = np.arange(0, 560, 0.25, dtype=np.float32)
    edges, lines = [], [[] for _ in RING_RADII_TPL[1:]]
    for a in np.radians(np.arange(0, 360, 0.5)):
        x = (RING_CENTRE_TPL[0] + r * np.cos(a)).astype(np.float32)
        y = (RING_CENTRE_TPL[1] + r * np.sin(a)).astype(np.float32)
        v = cv2.remap(grey, x[:, None], y[:, None], cv2.INTER_LINEAR,
                      borderValue=0)[:, 0]
        i = np.argmax((r > 40) & (v < HALF))  # past the centre mark
        edges.append(r[i - 1] + (v[i - 1] - HALF) / (v[i - 1] - v[i]) * 0.25)
        above = np.diff(np.r_[0, (v > HALF) & (r > edges[-1] + 5), 0].astype(int))
        for start, end in zip(np.flatnonzero(above == 1), np.flatnonzero(above == -1) - 1):
            centre, width = (r[start] + r[end]) / 2, r[end] - r[start]
            # Nearest line, 40 px either way: the rings are ~100 px apart, and a
            # tighter window clips the ~2% ellipse and biases the median.
            near = np.abs(np.subtract(RING_RADII_TPL[1:], centre))
            if width < 6 and near.min() < 40:
                lines[near.argmin()].append(centre)
    return float(np.median(edges)), tuple(float(np.median(f)) for f in lines)


if __name__ == "__main__":
    edge, line_radii = measure()
    print(f"10-ring edge radius {edge:.2f} px, diameter {2 * edge:.2f} px")
    print("ring line radii " + ", ".join(f"{x:.2f}" for x in line_radii))
