# Bullet Hole Detection — Handover

**As of 2026-09-17.** Branch `feature/test-labels-and-eval`, seven commits on top
of `74a1c5e`.

Read this first, then
[`../../bullet_hole_detection_pipeline_updated.md`](../../bullet_hole_detection_pipeline_updated.md)
for the architecture and
[`../docs/adr/0003-a-bullet-hole-is-new-when-it-persists.md`](../docs/adr/0003-a-bullet-hole-is-new-when-it-persists.md)
for why the detection design is what it is.

---

## Where it stands

Scored against operator-labelled ground truth (`truth/kanatv6`, six Hits, on
`CamA_20260914_141546.mkv` 13–25s):

```
TP 6   FP 1   FN 0        precision 86%   recall 100%   F1 0.92
```

Every Bullet Hole placed within 15–22 template px — under one hole's width.
43 tests pass in under a second.

**That is six Bullet Holes in one clip.** The thresholds are jointly optimal on
exactly this sample and that says very little about the next one. SOW 2.3.6 asks
for 99% over a statistically meaningful sample, which this is not.

---

## Running it

Everything runs from `ImageRecognitionService/` with its `.venv`.

```bash
# Detect new Bullet Holes, optionally rendering the rectified Board
.venv/bin/python new_bullet_holes.py CLIP.mkv --start 13 --end 25 --out out.mp4

# Score a run against labelled ground truth — use this before believing any change
.venv/bin/python evaluate.py CLIP.mkv --start 13 --end 25 \
    --truth-image truth/kanatv6/board.jpeg --truth-labels truth/kanatv6/board.txt

.venv/bin/python -m pytest -q
```

`--end` must leave at least `PERSIST_FRAMES` (50) after the last expected Hit. A
Bullet Hole whose confirmation window runs past the end of the clip is withheld,
not reported.

| File | Holds |
|---|---|
| `board.py` | Board geometry: find, register, rectify, Target/Miss, scoring, mm |
| `new_bullet_holes.py` | The pipeline: baseline, persistence, change evidence, reporting |
| `evaluate.py` | Scoring a run against labelled ground truth |
| `targets/kanat_silhouette_a4.png` | The printed Target artwork; registration depends on it |
| `truth/kanatv6/` | The one piece of ground truth that exists |
| `tagging_bullets.py`, `sweep_profile.py` | The older pipeline. Still live, still uses the 3-class model, documented by ADR-0002 |

---

## Five things that cost real time to learn

Each of these was found by measurement after an assumption failed. They are here
so nobody re-derives them.

**1. The detector is scale-sensitive, and `imgsz` alone does not tell you the
scale.** Two scalings compose — the warp into Board space and ultralytics' own
resize. At net scale 1.81 the model returns *zero* detections, reproduced at
three canvas resolutions an octave apart. Below ~1.1 the response is flat, so
there is no sharp optimum to chase.

`imgsz` is fitted to the canvas's **longest side**, not its width. A portrait
Board of 709×1063 at `imgsz` 704 is a 0.66 letterbox, not 0.99 — an early
version got this wrong and silently starved the detector.

**2. The thresholds were the bug, not the model.** The first values were set by
intuition and returned 1 true positive against 5 false. The model had detected
every Bullet Hole probed, to within 0–7 px. A 70% persistence bar was rejecting
real holes sitting at 0.50–0.62; a 40 template-px match radius was discarding one
125 px clear of its neighbour, because that radius also gates what counts as
"already in the baseline". **Do not tune anything here without `evaluate.py`.**

**3. Change detection cannot be the gate, but is an excellent filter.** As the
sole candidate source it covers at best 4 of 5 known Bullet Holes at *any*
threshold — it would cap recall near 80% before the model is consulted. Applied
*after* confirmation it removes false positives at no measured cost to recall:
the same run scores FP 7 without it and FP 1 with it.

**4. There are no fiducials, and the A4 edge is unusable.** Five marker
dictionaries return zero on the footage — none were printed. The sheet edge is
white paper on a white Board, and thresholding merges Board, sheets and dirt into
one blob. SIFT/ORB also fail: the artwork is flat colour, ~132 keypoints, and the
homography collapses. What works is ECC on the hue-masked printed Target,
correlation 0.98, converging on 300 of 300 frames.

**5. Ground-truth exports arrive in two formats and one arrived truncated.**
Roboflow gives `class cx cy w h` for detection and `class x1 y1 x2 y2 …` for
segmentation, and one export was cut off mid-number. `evaluate.py` decides format
per *file* and reports damaged labels rather than dropping them, because
silently discarding a label flatters recall.

---

## Blocked, in priority order

**1. One ruler measurement.** The printed white 10-ring's diameter in
millimetres. Everything physical scales linearly with it, so it is not guessed —
`to_millimetres` raises `NotCalibrated` instead. Pass `--ring-mm` once measured.
This blocks millimetre output and SOW 2.3.2 entirely.

It cannot be recovered from the imagery: no page edge in the video, and the
close-up ground-truth photo is cropped inside the sheet.

*Scoring does **not** need this* — a score is a ratio inside one image. It works
now.

**2. The held-out test set.** Whole recordings held out, never frames — adjacent
video frames are near-identical and splitting by frame is leakage. Until it
exists, every threshold below is tuned on six Bullet Holes, and `yolo26n` vs
`yolo26m` vs P2 cannot be compared meaningfully.

**3. SOW 2.3.4 renegotiation in writing.** The pipeline assumes the 5–10 second
budget. The signed 0.5 s is not met and cannot be with a 50-frame confirmation
window.

**4. Ground-truth method for acceptance.** SOW 2.3.2 and 2.3.6 both name it as
undefined.

---

## Not verified by real data

**No bullet has ever landed on a Target** in any footage provided — all seven
detections in the reference clip are Misses. So Target assignment, per-Target
ring centres and scoring are proven only by unit tests and a direct check on a
real Board view. A clip where someone hits the silhouette would exercise all
three at once. **This is the most valuable single piece of footage to capture
next.**

**One false positive survives** the change filter, and it is genuine — it sits
inside the ground-truth photo's coverage, so it is not an unlabelled hole outside
the frame.

**The Board's extent is inferred from where the Targets are**, because nothing
detects the plywood. `BOARD_MARGIN` bounds *recall*, not presentation: a Bullet
Hole outside the canvas is never seen, not merely unscored. A Target with no
green in its artwork — the ring-only one on the left of the sample footage — is
not found at all.

**The Board is treated as a single plane.** The sheets are stapled separately and
visibly curl. `board.residuals` exists to measure what that costs; run it first
if SOW 2.3.2's 5 mm proves unreachable, before building per-Target homographies.

---

## Every tunable, and its standing

All are named constants marked `PROVISIONAL`. **None is validated.**

| Constant | Value | Where | Basis |
|---|---|---|---|
| `PERSIST` | 0.50 | `new_bullet_holes.py` | Swept against ground truth; 0.70 lost most of the group |
| `PERSIST_FRAMES` | 50 | `new_bullet_holes.py` | Length provisional; *fixed* window is by design |
| `DEFAULT_CONFIDENCE` | 0.40 | `new_bullet_holes.py` | Swept; flat nearby |
| `REQUIRE_CHANGE_EVIDENCE` | True | `new_bullet_holes.py` | Swept; FP 7 → 1 at no measured recall cost |
| `MATCH_TPL_PX` | 20.0 | `board.py` | Swept; 40 discarded a real Bullet Hole |
| `TARGET_NET_SCALE` | 0.90 | `board.py` | Inside a flat band, not a measured peak |
| `ABSDIFF_SIGMA` | 2.0 | `board.py` | At 2.5 the evidence channel was dead |
| `BOARD_MARGIN` | 0.50 | `board.py` | Bounds recall; see above |
| `GREEN_LO` / `GREEN_HI` | — | `board.py` | One artwork, one lighting condition |
| `MIN_TARGET_AREA_PX` | 5000 | `board.py` | May reject distant Targets |

Measured artwork landmarks — `RING_CENTRE_TPL`, `RING_DIAMETER_TPL`,
`RING_OFFSET_TPL`, `RING_RADII_TPL` — are *not* tunables. They are readings off
`targets/kanat_silhouette_a4.png` and only change if the artwork does.

---

## If false positives return

Not by training a larger model. 86% of raw detections landed on gravel the
training set never contained as a negative, and the surviving false positives sit
on the printed rings and numerals — dark-on-light features that resemble Bullet
Holes. **Add background frames with empty label files.** No annotation work, just
images. That is the cheap, standard remedy for this exact failure, and it comes
before any architecture change.

`yolo26.yaml` and `yolo26-p2.yaml` are both present in the installed ultralytics
(8.4.126), so `m` and the P2 experiment are available whenever the test set makes
them measurable.
