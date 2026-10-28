"""Where the Target Sheet lies around the artwork, from #62's photographs (#271).

Each photograph is rectified onto the Target Sheet by the sheet's own four edges,
so the sheet is the ruler: every edge is fitted as a line above and below the
tape, and their corners map onto 297 x 210 mm, oriented like the template
(head up). The artwork's green mask is then fitted onto the sheet's by an affine
ECC, the tape masked out. The sheet's corners, carried back through that fit,
are the sheet's rectangle in template px, and the silhouette's extremes,
carried forward, are its margins in mm.

    .venv/bin/python -m tools.sheet_fit
"""
import os

import cv2
import numpy as np

from detection.board import BASE_DIR, DEFAULT_TEMPLATE

PHOTOS = [os.path.join(BASE_DIR, "docs", "ring_measurement", f"{name}.jpg")
          for name in ("side_to_side", "head_to_feet")]
SHEET_MM = (297, 210)
PX_PER_MM = 10
# The silhouette's outermost green, template px, edges at the pixel boundary:
# body sides, head apex, feet.
EXTREMES = {"left": 172.5, "right": 1221.5, "top": 9.5, "bottom": 1081.5}


def green(img):
    b, g, r = (img[..., i].astype(int) for i in range(3))
    return (g - r > 40) & (g - b > 20)


def largest(mask):
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    return labels == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])


def tape(img):
    """The tape measure, grown to cover its metal hook and shadow."""
    h, s, v = cv2.split(cv2.cvtColor(img, cv2.COLOR_BGR2HSV))
    yellow = largest(((h > 15) & (h < 40) & (s > 80) & (v > 100)).astype(np.uint8))
    return cv2.dilate(yellow.astype(np.uint8), np.ones((81, 81), np.uint8)) > 0


def sheet(img, covered):
    """The sheet: its white margin, its artwork and the tape lying on it."""
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1]
    white = ((grey > 175) & (sat < 40)) | green(img) | covered
    return largest(cv2.morphologyEx(white.astype(np.uint8), cv2.MORPH_CLOSE,
                                    np.ones((15, 15), np.uint8)))


def edge_line(mask, covered, side):
    """`(vx, vy, x0, y0)` of one sheet edge, from its outermost pixel on
    every 4th scanline away from the tape, refitted without points over 2 px
    off (corners, curl)."""
    vertical = side in ("left", "right")
    m = mask if vertical else mask.T
    first = side in ("left", "top")
    pts = []
    for i in range(40, m.shape[0] - 40, 4):
        run = np.flatnonzero(m[i])
        if not len(run):
            continue
        j = run.min() if first else run.max()
        near = covered[i, max(j - 30, 0):j + 30] if vertical else covered[max(j - 30, 0):j + 30, i]
        if not near.any():
            edge = j - 0.5 if first else j + 0.5
            pts.append((edge, i) if vertical else (i, edge))
    pts = np.float32(pts)
    keep = np.ones(len(pts), bool)
    for _ in range(3):
        vx, vy, x0, y0 = cv2.fitLine(pts[keep], cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        keep = np.abs((pts - [x0, y0]) @ [-vy, vx]) < 2.0
    return vx, vy, x0, y0


def corner(a, b):
    (vx1, vy1, x1, y1), (vx2, vy2, x2, y2) = a, b
    t = np.linalg.solve([[vx1, -vx2], [vy1, -vy2]], [x2 - x1, y2 - y1])[0]
    return x1 + t * vx1, y1 + t * vy1


def rectify(img):
    """The sheet at `PX_PER_MM`, head up, and which of it the tape left visible.

    Both photographs have the head to the right, so the template's top-left is
    the photograph's top-right."""
    covered = tape(img)
    mask = sheet(img, covered)
    e = {side: edge_line(mask, covered, side) for side in ("left", "right", "top", "bottom")}
    src = np.float32([corner(e["top"], e["right"]), corner(e["bottom"], e["right"]),
                      corner(e["bottom"], e["left"]), corner(e["top"], e["left"])])
    w, h = (n * PX_PER_MM for n in SHEET_MM)
    H = cv2.getPerspectiveTransform(src, np.float32([[0, 0], [w, 0], [w, h], [0, h]]))
    rectified = cv2.warpPerspective(img, H, (w, h), flags=cv2.INTER_CUBIC)
    visible = cv2.warpPerspective((~covered).astype(np.uint8), H, (w, h),
                                  flags=cv2.INTER_NEAREST)
    return rectified, cv2.erode(visible, np.ones((15, 15), np.uint8))


def measure(photo, template=DEFAULT_TEMPLATE):
    """`(margins mm, sheet rectangle template px, (mm/px x, mm/px y), ECC)`.

    Margins are left, right, top (head), bottom (feet); the rectangle is
    `(x0, y0, x1, y1)`, each side the mean of its two corners.
    """
    rectified, visible = rectify(cv2.imread(photo))
    artwork = green(cv2.imread(template)).astype(np.float32)
    s = 0.1763 * PX_PER_MM  # seeded from ADR-0011's centred sheet
    warp = np.float32([[s, 0, s * 140], [0, s, s * 36]])
    criteria = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 100, 1e-6)
    correlation, warp = cv2.findTransformECC(
        cv2.GaussianBlur(artwork, (0, 0), 1.5),
        cv2.GaussianBlur(green(rectified).astype(np.float32), (0, 0), 1.5 * s),
        warp, cv2.MOTION_AFFINE, criteria, visible, 5)
    A = np.vstack([warp, [0, 0, 1]]).astype(float)
    to_mm = lambda x, y: (A @ [x, y, 1])[:2] / PX_PER_MM
    # Body sides read at y 800, mid-way down them; head and feet at the apex column.
    margins = (to_mm(EXTREMES["left"], 800)[0],
               SHEET_MM[0] - to_mm(EXTREMES["right"], 800)[0],
               to_mm(702, EXTREMES["top"])[1],
               SHEET_MM[1] - to_mm(702, EXTREMES["bottom"])[1])
    w, h = SHEET_MM
    c = (np.linalg.inv(A) @ np.vstack([np.float64([[0, w, w, 0], [0, 0, h, h]]) * PX_PER_MM,
                                       np.ones(4)]))[:2]
    rect = ((c[0, 0] + c[0, 3]) / 2, (c[1, 0] + c[1, 1]) / 2,
            (c[0, 1] + c[0, 2]) / 2, (c[1, 2] + c[1, 3]) / 2)
    scale = (np.hypot(A[0, 0], A[1, 0]) / PX_PER_MM, np.hypot(A[0, 1], A[1, 1]) / PX_PER_MM)
    return margins, rect, scale, correlation


if __name__ == "__main__":
    rects = []
    for photo in PHOTOS:
        margins, rect, scale, correlation = measure(photo)
        rects.append(rect)
        print(f"{os.path.basename(photo)}: ECC {correlation:.4f}, "
              f"mm per template px x {scale[0]:.4f} y {scale[1]:.4f}")
        print("  margins mm  left {:.1f}  right {:.1f}  head {:.1f}  feet {:.1f}".format(*margins))
        print("  sheet, template px  x {:.1f} .. {:.1f}  y {:.1f} .. {:.1f}".format(
            rect[0], rect[2], rect[1], rect[3]))
    mean = np.mean(rects, axis=0)
    print("mean sheet, template px  x {:.1f} .. {:.1f}  y {:.1f} .. {:.1f}".format(
        mean[0], mean[2], mean[1], mean[3]))
