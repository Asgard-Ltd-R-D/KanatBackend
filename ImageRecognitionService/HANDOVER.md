# Bullet Hole Detection — Handover

**As of 2026-09-17.** Branch `feature/test-labels-and-eval`.

Read this first, then
[`../../bullet_hole_detection_pipeline_updated.md`](../../bullet_hole_detection_pipeline_updated.md)
for the architecture and
[`../docs/adr/0003-a-bullet-hole-is-new-when-it-persists.md`](../docs/adr/0003-a-bullet-hole-is-new-when-it-persists.md)
for why the detection design is what it is.

---

## Where it stands

Two clips now carry operator-labelled ground truth.

| Clip | Window | Labelled | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|---|
| `CamA_20260914_141546.mkv` (`truth/kanatv6`) | 13–25s | 6 | 6 | 1 | 0 | 86% | 100% | 0.92 |
| `CamB_20260915_102250.mkv` (`truth/camb-25-36`) | 25–36s | 4 | 4 | 0 | 0 | 100% | 100% | 1.00 |

Bullet Holes placed within 9–22 template px — under one hole's width. 49 tests
pass in under a second.

**That is ten Bullet Holes across two clips.** The thresholds are jointly
optimal on exactly this sample and that says very little about the next one. SOW
2.3.6 asks for 99% over a statistically meaningful sample, which this is not.

**CamB is the first footage where a bullet landed on a Target** — two of its
four, scoring 7 and 8. Until it arrived, Target assignment and ring scoring had
only unit tests behind them.

Recall is 100% on both clips with the `yolo26n` weights. That is **not** enough
to close `yolo26n` vs `yolo26m`: two recordings is not the held-out test set,
and model selection still waits on it (blocked item 2).

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
not reported. This is the most common way to manufacture a false negative: on
CamB an `--end` of 32 hid two Bullet Holes the model had detected at 0.86 and
0.90 confidence with 100% persistence. Check the window before suspecting the
model.

**Export ground truth from Roboflow as DETECTION, not segmentation.** A
detection export is `class cx cy w h` on every line and `load_labels` takes the
box fast path. A segmentation export is polygons, and if a single annotation was
drawn as a box the file is mixed — that 4-value line is then counted as damaged
and dropped, silently understating ground truth. The CamB export arrived this
way and scored `[TRUTH] 3` against 4 drawn labels.

Where an export needs correcting, **keep the raw file** and correct a derived
copy: `truth/camb-25-36/board.roboflow.txt` is Roboflow's bytes unchanged, and
`board.txt` is the file the evaluation reads.

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
exists, every threshold below is tuned on ten Bullet Holes across two clips, and
`yolo26n` vs `yolo26m` vs P2 cannot be compared meaningfully.

This is the next step, and it is what the following six open questions are
waiting on. **Do not move any constant further on CamA and CamB alone.**

1. Duplicate / split behaviour — the 0.59x vs 0.74x collision above.
2. Genuinely close Bullet Holes, and how near two real marks actually get.
3. Persistence: `PERSIST` 0.50 and the fixed 50-frame window.
4. Baseline suppression, which bounds recall directly.
5. `yolo26n` vs `yolo26m` vs P2.
6. The matching tolerances — `MATCH_TPL_PX`, `DUP_CENTER_FACTOR`,
   `OVERLAP_THRESHOLD` and `evaluate.MATCH_TOLERANCE_TPL`.

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

**One false positive survives** the change filter on CamA, and it is genuine —
it sits inside the ground-truth photo's coverage, so it is not an unlabelled hole
outside the frame.

**The merge gate does not actually separate the two cases it is asked to.**
`same_bullet_hole` merges two detections whose centres fall within
`DUP_CENTER_FACTOR` x the mean box diagonal, or whose boxes overlap by more than
`OVERLAP_THRESHOLD` of the smaller area. Measured on the labelled clips:

- CamB's torn mark, which the detector boxes as two halves, sits at **0.59x**
  diagonal. Ground truth labels it once.
- CamA's closest genuinely distinct pair sits at **0.74x** diagonal.

A per-frame merge of CamB's pair therefore needs 0.59, but anything at or above
0.6 regresses CamA from F1 0.92 to 0.83 — merging shifts which candidate absorbs
which, and so changes persistence bookkeeping, not merely counts. **The two
windows do not overlap on the data that exists.**

CamB does report that mark as one Bullet Hole, and scores 1.00 — but by the
candidate's running mean drifting into range over 275 frames, not because the
gate fires. That is luck, and `test_camb_split_is_not_merged_by_the_gate_alone`
pins it so nobody mistakes it for a property. Settling it needs the held-out test
set, not a nudged constant.

**The box arms must not gate baseline suppression.** Applied there they swallowed
a real new Bullet Hole next to a pre-existing one on CamB, taking recall from
100% to 75%. Suppression stays on the template-px floor — the same trap ADR-0003
records for the 40 px match radius.

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
| `DUP_CENTER_FACTOR` | 0.5 | `new_bullet_holes.py` | Ported from `tagging_bullets.py`; 0.6+ regresses CamA to F1 0.83 |
| `OVERLAP_THRESHOLD` | 0.5 | `new_bullet_holes.py` | Ported; merging on *any* overlap regresses CamA |
| `TARGET_NET_SCALE` | 0.90 | `board.py` | Inside a flat band, not a measured peak |
| `ABSDIFF_SIGMA` | 2.0 | `board.py` | At 2.5 the evidence channel was dead |
| `BOARD_MARGIN` | 0.50 | `board.py` | Bounds recall; see above |
| `GREEN_LO` / `GREEN_HI` | — | `board.py` | One artwork, one lighting condition |
| `MIN_TARGET_AREA_PX` | 5000 | `board.py` | May reject distant Targets |

`MATCH_TOLERANCE_TPL` (40 px, `evaluate.py`) is provisional too — it is the
*scoring* tolerance, not a pipeline threshold. Matches currently land at 9–22
template px against it, which is encouraging and is not validation across a
dataset.

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
