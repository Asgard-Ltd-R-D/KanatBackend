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
| `CamB_20260915_102250.mkv` (`truth/camb-25-36`) | 25–36s | 3 | 3 | 1 | 0 | 75% | 100% | 0.86 |

Bullet Holes placed within 9–22 template px — under one hole's width. 54 tests
pass in under a second.

**Every figure in this document was re-verified on 2026-09-17 after the
memory-safety fix below**, on `opencv-python==4.10.0.84`. All three F1 scores,
the drift ranges, the ECC medians, the co-occurrence counts and the anchor
measurements reproduced unchanged. The runs are *not* bit-identical across the
OpenCV change — CamA's baseline detected 4 pre-existing marks where it had found
5, and persistences moved a point or two — because 4.10 and 5.0 letterbox with
different resize implementations and marginal detections land either side of the
confidence floor. That the aggregates survived that perturbation is a stronger
check than bit-equality would have been.

**CamB is scored against 3 labels, not the 4 the operator drew.** The fourth sits
on a mark that was *already on the Board* at the 25s baseline frame — clean at
t=0, present at t=25.0 and still there at t=45.5. It is not a new Bullet Hole in
this window, and a single final frame cannot show when a mark arrived, so the
label was reasonable and the scoring was not. `board.txt` is the operator's four
labels; `board.new-since-25s.txt` is the three used above and is what
`--truth-labels` should point at for this window.

An earlier revision of this file reported CamB as F1 1.00. That figure was
wrong: it credited the pipeline with finding a pre-existing mark.

**That is nine Bullet Holes across two clips.** The thresholds are jointly
optimal on exactly this sample and that says very little about the next one. SOW
2.3.6 asks for 99% over a statistically meaningful sample, which this is not.

**CamB is the first footage where a bullet landed on a Target** — two of its
four, scoring 7 and 8. Until it arrived, Target assignment and ring scoring had
only unit tests behind them.

Recall is 100% on both clips with the `yolo26n` weights, *within the labelled
windows*. That is **not** enough to close `yolo26n` vs `yolo26m`: two recordings
is not the held-out test set, and model selection still waits on it (blocked
item 2).

It is also not the whole story about recall. Outside the labelled window, on the
full 0–46s CamB clip, the detector returns **nothing at conf 0.02** for a mark
that stays plainly visible for 22 seconds — see "Three failure modes" below.

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

## Three failure modes found on CamB, 2026-09-17

All three were found on the full 0–46s clip, all three were confirmed against the
imagery, and **none of them is the merge gate or a threshold**. They are recorded
here because the operator spotted every one of them by watching the video, and
the pipeline reported all three as ordinary Bullet Holes.

**1. The single-frame baseline invents Bullet Holes.** A mark plainly visible in
the t=0 frame was missed by the baseline detection and so re-detected as *new*
40 ms later, at 0.04s. No bullet arrives in one frame. The same thing produced
the 25.60s report in the windowed run, from a mark present at the 25.0s baseline.
The baseline is one frame, and everything downstream inherits whatever that frame
failed to see. This is the most reproducible defect found: two false positives,
two runs.

**2. One mark is reported twice when registration displaces it.** Two Bullet
Holes 27 Board px apart, at 31.16s and 38.56s. Across 363 frames they NEVER
appeared together — 306 frames at one position, 49 at the other, 0 at both. Two
genuine Bullet Holes co-occur constantly once both exist. `merge_displaced_tracks`
is the mitigation and is OFF by default; the cause is geometric and open.

**3. A confirmed Bullet Hole is never re-examined when it stops existing.** The
0.04s mark is detected at conf 0.82–0.86 for its first two seconds, then the
detector returns **nothing at conf 0.02** from ~3s, while the mark stays visible
to the eye until 25.0s — a genuine recall failure, not a threshold, and the only
detector problem found today. Between 25.0s and 25.5s the mark then disappears
from the raw image altogether while the near-Target anchors hold to 3.6 px, so
whatever moved was local to the bottom of the Board — the non-planar/curl case.
It confirmed only because its two detectable seconds coincided with the 50-frame
window, and nothing ever revisits a confirmed Bullet Hole afterwards.

### What the geometry actually measures

An earlier probe reported 38.6 px of registration drift. **That figure was wrong**
— it tracked the green-mask contour centroid, and `H` is estimated from that same
mask, so mask noise read as geometry error. Measured against stationary physical
marks, which depend on `H` alone:

| Probe | distance from Target | median | max |
|---|---|---|---|
| anchor 2 | 38 px | 0.5 px | 36.3 px |
| anchor 1 | 58 px | 2.0 px | 9.3 px |
| far mark (#5) | 105 px | 1.5 px | 34.2 px |

Registration is good most of the time and throws occasional large excursions. The
excursions look worse far from the Target, which is what a homography fitted to a
single Target does — but anchor 2 is close in and still threw 36.3 px, so
"far field is worse" is **not** established. `MAX_DISPLACEMENT_FRACTION` is
scaled by distance on the strength of that unproven pattern and should be
re-derived on footage with more than one Target.

Cumulative drift is ruled out: seeding ECC from the baseline instead of the
previous frame reproduces the chained numbers to three decimals.

## The opencv pin is load-bearing

`requirements.txt` pinned nothing, so `pip install -r` resolved `opencv-python`
to **5.0.0.93**. Every release from **4.11** onward — 5.x included — ships
KleidiCV as a custom HAL, and its NEON `resize` kernel writes out of bounds.
Reached through ultralytics' letterbox on *every* `_detect` call, it segfaulted
on `CamA_20260914_141846.mkv` at a **different frame each run** — 61 and 222 on
5.0.0, 28 and 111 on 4.14.0. A different frame each time is heap corruption, not
a data-dependent fault.

It failed **silently**: exit 139, no traceback, no partial-result warning. A run
that dies at frame 61 is indistinguishable from one that found nothing, and
`grep`-based tooling hides it completely. It took four runs of that clip to
notice, and only by checking the exit code by hand.

`4.10.0.84` is the last release without KleidiCV — `Custom HAL: carotene` only.
It survives the same clip for 499 frames across three runs. **A range pin is not
enough**: `>=4.10,<5` resolves straight back to 4.14.

Two things follow. First, `opencv-python==4.10.0.84` is exact on purpose; do not
loosen it without re-running that clip. Second, every threshold in this project
is measured against footage, and an unpinned resolution swaps the detector or its
image pipeline out from under those measurements without anything failing loudly.

**Still open:** nothing reports a truncated run. `process` should compare frames
actually processed against frames requested and say so when they differ. Until it
does, a crashed run and a clean one look the same.

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
