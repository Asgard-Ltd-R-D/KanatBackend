# Disk-first Target search: the alternative to the colour gate

**Status: not adopted (2026-11-24).** The colour gate stays, made adaptive
(`board.find_targets`: a hue band with a per-frame Otsu saturation floor)
with a shape check on every Target after the reference
(`board.fitted_outline`, `TARGET_MIN_IOU`). This page keeps the measured
alternative so it can be picked up without redoing the work. **Switch to it
if outdoor footage shows the adaptive gate losing the Target**, above all
under a strong blue cast, where the paper itself turns saturated cyan.

## Why the colour gate fails outdoors

At a customer visit, the Target was found indoors and not found outdoors in
direct sun, zoomed in. The print is teal, hue 87 (CamA) to 93 (CamB, sun),
and the fixed gate stopped at 95. A white-balance gain of 10% (B/R 1.21)
moved the whole print past 95, and nothing was found. The disk check, which
decides that a blob is a Target, never saw it. Under the true fit the disk
was found in every failing case: the shape survives light the colour does
not.

The paper round the print is bluish (hue 97-111, saturation up to 170 on
CamA outdoors), so no hue band parts print from paper. The adaptive gate
splits them by saturation instead. It holds to B/R 1.32 on CamB.

## The method

No colour gate and no initial position. Luma is not used either:
over-exposure clips the print's green channel to the disk's white.

1. **Whiteness:** each pixel's darkest channel. White paper and the white
   disk stay high, and ink of any hue drops.
2. **Candidates:** bright blobs of an adaptive threshold (windows 31, 101,
   301 px, at full and half resolution), every contour nesting level,
   near-elliptical (axes ratio >= 0.6, fill >= 0.8), the band 1.15-1.6 radii
   out at most 0.75 of the disk's whiteness, radius at least
   `MIN_TARGET_AREA_PX` as a disk (~8.8 px).
3. **Seed:** the affine taking the template's 10-ring disk onto the ellipse.
4. **Verify:** `board.interior_fit` (disk centre and digit row,
   correlation >= 0.6).
5. **Refine:** ECC (affine) of the artwork's whiteness onto the frame's,
   masked to the artwork the frame shows. This reads camera roll, which
   step 4 cannot.

## What was measured

Lighting: hue +-4/8, saturation x0.5/x0.3, exposure x1.6/x2.2, warm and
cool white balance, and a "sun" mix. Zoom: digital 1-4x about the ring.
Frames: CamA `_141546`, CamB `_102450` and the artwork drawn on grey.
Negatives: `good_shooting_vid2` and `test_video` (other target types, with
bullseyes), and CamA and CamB with their prints painted out.

| | Fixed gate (`main` 3f80479) | Adaptive gate | Disk-first |
|---|---|---|---|
| Targets missed, lighting x zoom | 21 of 165 | 2 of 165 | 0 of 176 |
| False Targets, 88 negative cases | not measured | blue bags, before the shape check | 0 |

- **Zoom ceiling.** With the full digit row (6 to 6), 8 of 176 are missed:
  the artwork at zoom 4, its outer 6s cut by the frame. Verifying on
  7 8 9 | 9 8 7 alone found all 176. The shorter row's scale accuracy is
  not measured (#302 calibrated on the full row).
- **Precision, artwork on grey (truth known).** Steps 1-4 alone: centre
  0.00-0.03 mm, but 1.8 mm at the 6-ring with no roll, 4.2 mm at 2 deg,
  9.1 mm at 5 deg, not found at 10 deg. With step 5: 0.04-0.21 mm at the
  6-ring, roll 0-20 deg, every lighting.
- **Precision, real frames against `main`'s fit (no truth).** Centre
  0.00-0.32 mm at zoom 1-4, 6-ring 0.5-4.0 mm. The largest are CamB with
  clipped sun, where the print loses texture.
- **Latency, Mac CPU, one thread, unoptimised.** Search: P50 140 ms, P95
  473 ms, max 691 ms (a 3840x2160 frame included). With the refinement:
  300-550 ms per frame. Only the baseline, a re-anchor and the silhouette
  check need it: tracking (`track_view`) never uses colour.

The thresholds were set while looking at these same cases: this is
regression, not a held-out result (ADR-0005).

## Not tested

Real outdoor or zoomed footage, a disk shot through or covered by a hand,
the regression bench, and the position-error truth set.

## Prototype

The functions as measured, against `detection.board` at 3f80479.

```python
import cv2, sys, numpy as np
from detection import board

R_TPL = board.RING_DIAMETER_TPL / 2
BLOCKS = (31, 101, 301)       # adaptive-threshold windows, px
# The existing minimum Target size, as a disk: artwork area / disk area = 20.6
_ART_PER_DISK = 806119 / (np.pi * R_TPL ** 2)
MIN_DISK_R = np.sqrt(board.MIN_TARGET_AREA_PX / _ART_PER_DISK / np.pi)   # ~8.8 px

def whiteness(frame):
    return frame.min(axis=2)

def _dark_ring(g, e):
    """The band just outside the disk is print: clearly darker than the disk.
    Measured on a crop round the ellipse, not the whole frame."""
    (cx, cy), (ew, eh), ang = e
    R = int(np.ceil(max(ew, eh) * 0.85)) + 2
    x0, y0 = max(int(cx) - R, 0), max(int(cy) - R, 0)
    crop = g[y0:int(cy) + R, x0:int(cx) + R]
    c = (cx - x0, cy - y0)
    inner = np.zeros_like(crop); cv2.ellipse(inner, (c, (ew * 0.8, eh * 0.8), ang), 255, -1)
    ring = np.zeros_like(crop); cv2.ellipse(ring, (c, (ew * 1.6, eh * 1.6), ang), 255, -1)
    cv2.ellipse(ring, (c, (ew * 1.15, eh * 1.15), ang), 0, -1)
    return inner.any() and ring.any() and cv2.mean(crop, ring)[0] <= 0.75 * cv2.mean(crop, inner)[0]

def candidates(w):
    out = []
    for k in (1, 2):   # full and half resolution: disks bigger than the largest window
        g = cv2.GaussianBlur(w if k == 1 else cv2.resize(w, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA), (5, 5), 0)
        for block in BLOCKS:
            bright = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, block, -10)
            cs, _ = cv2.findContours(bright, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for c in cs:
                area = cv2.contourArea(c)
                if area < np.pi * (MIN_DISK_R / k) ** 2 * 0.8 or len(c) < 8:
                    continue
                e = cv2.fitEllipse(c)
                (cx, cy), (ew, eh), ang = e
                if min(ew, eh) < 0.6 * max(ew, eh) or area < 0.8 * np.pi * ew * eh / 4:
                    continue
                if not _dark_ring(g, e):
                    continue
                e = ((cx * k, cy * k), (ew * k, eh * k), ang)
                r = np.sqrt(ew * eh) / 2 * k
                if r < MIN_DISK_R:
                    continue
                if any(np.hypot(e[0][0] - o[0][0], e[0][1] - o[0][1]) < r / 2 and
                       abs(np.sqrt(o[1][0] * o[1][1]) / 2 / r - 1) < 0.1 for o in out):
                    continue
                out.append(e)
    return out

def seed(e):
    """Template -> frame affine taking the 10-ring disk onto ellipse `e`."""
    (cx, cy), (ew, eh), ang = e
    t = np.radians(ang); R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    A = R @ np.diag([ew / 2 / R_TPL, eh / 2 / R_TPL]) @ R.T
    b = np.array([cx, cy]) - A @ board.RING_CENTRE_TPL
    return np.vstack([np.c_[A, b], [0, 0, 1]]).astype(np.float32)

def find(frame):
    """[(H, correlation)] one per verified 10-ring, and the candidate count."""
    w = whiteness(frame)
    w3 = cv2.merge([w, w, w])
    found, cands = [], candidates(w)
    for e in cands:
        H = seed(e)
        A, corr = board.interior_fit(w3, H)
        if A is not None:
            Hf = (H @ A).astype(np.float32)
            c = board.apply(Hf, [board.RING_CENTRE_TPL])[0]
            if all(np.linalg.norm(c - board.apply(h, [board.RING_CENTRE_TPL])[0]) > MIN_DISK_R for h, _ in found):
                found.append((Hf, corr))
    return found, len(cands)

# --- step 5: refine ---
TW = cv2.GaussianBlur(whiteness(cv2.imread(board.DEFAULT_TEMPLATE)).astype(np.float32), (0, 0), 3)

def refine(frame, H, template_mask, k=0.25):
    """ECC (affine) of the artwork's whiteness onto the frame's, at k px per template px."""
    w = whiteness(frame); S_ = np.float32([[k, 0, 0], [0, k, 0], [0, 0, 1]])
    size = (int(TW.shape[1] * k), int(TW.shape[0] * k))
    tpl = cv2.resize(TW, size, interpolation=cv2.INTER_AREA)
    # the frame warped into (scaled) template space by the seed; ECC finds the correction
    cur = cv2.warpPerspective(w, S_ @ np.linalg.inv(H), size, flags=cv2.INTER_LINEAR, borderValue=255).astype(np.float32)
    cur = cv2.GaussianBlur(cur, (0, 0), 3 * k)
    mask = cv2.resize(template_mask, size, interpolation=cv2.INTER_NEAREST)
    mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))
    seen = cv2.warpPerspective(np.full(w.shape, 255, np.uint8), S_ @ np.linalg.inv(H), size, flags=cv2.INTER_NEAREST, borderValue=0)
    mask = mask & cv2.erode(seen, np.ones((9, 9), np.uint8))   # only artwork the frame shows
    W = np.eye(2, 3, dtype=np.float32)
    _, W = cv2.findTransformECC(tpl, cur, W, cv2.MOTION_AFFINE, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5), mask, 5)
    Wk = np.linalg.inv(S_) @ np.vstack([W, [0, 0, 1]]) @ S_      # template -> template correction
    Hr = (H @ Wk).astype(np.float32)
    A, _ = board.interior_fit(frame, Hr)
    return (Hr @ A).astype(np.float32) if A is not None else Hr
```
