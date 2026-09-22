# Bullet Hole Detection — Handover

**As of 2026-09-17.** Branch `feature/test-labels-and-eval`.

**Persistence counts frames, not sightings** (fixed 2026-09-17). The detector
boxes a torn mark as two halves and both fold into one candidate, so a frame was
counted twice and a Bullet Hole could clear the bar on fewer distinct frames than
the bar asks for. `min(ratio, 1.0)` was hiding it — the only symptom was a
persistence wanting to exceed 100%. Both labelled clips score unchanged after the
fix — CamA 13–25s TP 6 / FP 1 / FN 0, F1 0.92 with every persistence value
identical, and CamB 25–36s TP 3 / FP 1 / FN 0, F1 0.86. What moved is CamB's torn
mark, whose frame count fell from 254 to 135; that is the double-counting, and it
confirms the inflation was concentrated on the one mark the detector splits.

**Persistence de-duplicates frames; position does not.** The candidate's location
is still a running mean over every sighting, because that mean is what folds
CamB's two halves into one Bullet Hole over 275 frames and
`test_camb_split_is_not_merged_by_the_gate_alone` pins it. Persistence asks how
many frames saw the mark, position asks where it is — different questions, and
de-duplicating the second would change which candidate absorbs which.

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

Bullet Holes placed within 9–22 template px — under one hole's width. 108 tests
pass in about a second.

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

**The derivation compares the two photographs in the after photograph's own
pixels**, not in template coordinates. Registering each photograph to the
template separately was tried first and does not work: on the customer
photographs that registration correlates 0.69–0.76, the two errors compound,
and every one of the 19 pre-existing marks came out unmatched — marks that are
plainly the same holes in both photographs, 0.001 apart in normalised photo
coordinates, landing 60 to 4000 template px apart. Marks far outside the
printed artwork fared worst, which is the homography extrapolating. One ECC
between the two photographs replaces both registrations, and the 40 template px
tolerance is converted into photograph px by the Target span ratio — on these
photographs the Target spans about a sixth of the template, so the slack is
about 6 photo px. Every pre-existing mark then matches 0.5–5.5 px out.

Those three are no longer worked out by hand. `board.before.txt` carries the one
pre-existing mark as the operator identified it, and the derivation in
`evaluate.py` — `derive_truth.py` is its command line — subtracts it,
reproducing `board.new-since-25s.txt` line for line, which
`test_derive_truth.py` pins. New recordings get the same treatment from a
photograph pair rather than a hand-adjudicated frame.

## Photograph-derived ground truth for the customer recordings

Six recordings now carry ground truth derived from a before/after photograph
pair, in `truth/{cam}-{date}-{time}/`. `board.new.txt` is the derived new
Bullet Holes, `board.{before,after}.export.txt` are the raw exports byte for
byte, and `board.source.txt` names the photographs the coordinates belong to —
the photographs themselves are not version-controlled, like the recordings.

| Recording | After | Pre-existing | **New** | Photo registration |
|---|---|---|---|---|
| `CamA_20260914_141546` | 6 | 0 | **6** | 0.9927 |
| `CamB_20260915_101450` | 1 | 0 | **1** | 0.9376 |
| `CamB_20260915_101550` | 2 | 1 | **1** | 0.9259 |
| `CamB_20260915_102250` | 6 | 2 | **4** | 0.9038 |
| `CamB_20260915_102450` | 10 | 6 | **4** | 0.9456 |
| `CamB_20260915_103223` | 12 | 8 | **4** | 0.8941 |

**Both passes now come from one detection-format delivery** — `Before_
Annotated` and `After_ Annotated`, re-annotated as boxes after the first
delivery arrived as polygons. All twelve label files are `class cx cy w h` on
every line, no polygons and no mixed files, so nothing is reported as mixed any
more. The marks moved 0.001–0.003 in normalised photograph coordinates from the
polygon pass, which is a re-draw of the same holes; five of the six derivations
come out line for line as before.

**CamA is the cross-check.** Its before photograph is clean, so all six after
labels are new — and those six land 4.9–9.4 template px from the six labels of
`truth/kanatv6`, which were drawn by hand on a *different* photograph. Six of
six match within tolerance. Two independent annotation passes, two
photographs, one answer.

**`CamB_20260915_103223` carries two flags, and is the one recording that got
worse.** Two before-marks have no counterpart within the 6.1 px tolerance: one
at 7.3 px (it was 9.1 px in the polygon pass, so closer now and still out)
and one at 6.14 px,
which misses by 0.06 px. Both mean an after-mark that was probably already on
the Board is counted as new, so this recording's four "new" Bullet Holes are
really two or three. It also has the weakest photograph registration of the six
(0.8941), and its matched marks sit 1.4–4.2 px out, so 6–7 px is an outlier
rather than the normal spread. Check those two marks by eye before the
recording is scored; do not widen the tolerance to make them go away — at 6.14
px the temptation is obvious and the cost is folding genuinely distinct marks
together everywhere else.

`evaluate.py` now prints that flag too: it reads `board.source.txt` beside the
labels it was given and warns when the derivation left before-marks unpaired.
Pointing `--truth-labels` at a derived directory also picks `board.new.txt`
rather than `board.after.export.txt`, which sorts first and would have scored
the run against the pre-existing marks as well. Where there is no derived file
to prefer, a directory of several `.txt` files is now refused by name instead
of resolved alphabetically — in `truth/camb-25-36` that first file is
`board.before.txt`.

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
that stays plainly visible for 21 seconds — see "Three failure modes" below.

---

## Running it

Everything runs from `ImageRecognitionService/` with its `.venv`.

```bash
# Detect new Bullet Holes, optionally rendering the rectified Board
.venv/bin/python new_bullet_holes.py CLIP.mkv --start 13 --end 25 --out out.mp4

# The baseline spans --baseline-frames frames from --start (default 5, ~200 ms).
# A Hit landing inside that window is absorbed into the baseline and never
# reported, so --start must sit before the shooting.

# Derive the new Bullet Holes from a before/after photograph pair. --truth-labels
# then points at the board.new.txt this writes, never at the after export.
.venv/bin/python derive_truth.py \
    --before-image photos/CamB.before.jpeg --before-labels export/before.txt \
    --after-image  photos/CamB.after.jpeg  --after-labels  export/after.txt \
    --out-dir truth/camb-20260915-102250

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

That is no longer how it is read. **The rule is per line: four values is a box,
six or more is a polygon**, wherever it sits in the file. Mixed files are the
norm, not the exception — in the first two customer deliveries, nine of the
twelve label files carried a box line among polygons — and the old per-file
rule dropped every one of those labels. A dropped before-label lets a
pre-existing mark through as a new Bullet Hole; a dropped after-label flatters
recall. Both are now read, and the mix is reported.

The delivery in use is detection throughout and reports no mix, so that rule is
now insurance rather than the daily path. It stays: the next delivery is one
annotator's checkbox away from arriving as polygons again.

What is still refused is a **damaged** line: fewer than four values, or an odd
number of them, which is a coordinate cut short. That is a wrong position
rather than a differently drawn one, so `derive_truth.py` refuses the file by
line number instead of deriving a mark in the wrong place.

Where an export needs correcting, **keep the raw file** and correct a derived
copy: `truth/camb-25-36/board.roboflow.txt` is Roboflow's bytes unchanged, and
`board.txt` is the file the evaluation reads.

**Every recording needs a manifest entry before any tool will open it.**
`recordings.json` maps sha256 to Capture Setup, role (`sealed`,
`threshold-work` or `spent`), frame rate and analysis window. A file in no
entry is refused, and so is an entry whose role is none of those three —
an unallocated recording has no role, and guessing one is how the held-out set
gets spent. `CamA_20260914_141546.mkv` and `CamB_20260915_102250.mkv` are not
on this machine, so the two commands above need their entries adding first:

```bash
.venv/bin/python -c "import manifest; print(manifest.content_hash('CLIP.mkv'))"
```

A recording whose role is `sealed` is refused unless `--final-run` is passed,
and that run is appended to `sealed_runs.log` — which is committed, not
ignored — with the date, model and commit. Lookup is by content hash, so
renaming a file cannot move it across the split boundary. See `manifest.py` and
ADR-0005.

The guard sits on the recording, because that is where provenance is.
`new_bullet_holes.py`, `evaluate.py` and `tagging_bullets.py` all call
`manifest.gate` before opening one; `sweep_profile.py` takes a frame already on
disk, which cannot be traced back to the footage it came from. Gating the
extraction is what keeps sealed pixels out of it.

| File | Holds |
|---|---|
| `board.py` | Board geometry: find, register, rectify, Target/Miss, scoring, mm |
| `new_bullet_holes.py` | The pipeline: the shared frame loop, baseline, persistence, change evidence, reporting |
| `evaluate.py` | Scoring a run against labelled ground truth |
| `manifest.py`, `recordings.json` | Split membership by content hash, the sealed guard, the run log |
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

## Three failure modes found on CamB, and what they turned out to be

All three were found on the full 0–46s clip by the operator watching the video,
and the pipeline reported all three as ordinary Bullet Holes. **On 2026-09-17
each was measured rather than inferred, and two of the three changed
classification.** None of them is the merge gate or a threshold.

**1. The single-frame baseline invents Bullet Holes. FIXED.** A mark plainly
visible in the t=0 frame was missed by the baseline detection and re-detected as
*new* 40 ms later, at 0.04s. No bullet arrives in one frame. Measured: the mark
sits 127 Board px clear of anything else, is detected at >=0.40 continuously from
0.04s, and the single baseline frame simply missed it.

The baseline is now the de-duplicated union of `BASELINE_FRAMES` frames
(`baseline_marks`), which catches it in frame 1. The alternative — lowering the
baseline's confidence floor — was rejected: 0.20 recovers the same mark on this
clip, but by 0.10 the baseline starts suppressing on the printed rings, blinding
the pipeline to Bullet Holes on the one Target CamB finally put bullets on. That
is a constant fitted to one clip inside a narrow safe band. `BASELINE_FRAMES` is
a duration, and its cost is bounded and visible: **a Hit landing inside the
baseline window is absorbed and never reported, so the baseline interval must
precede the shooting interval.**

**This mode had one instance, not two.** The 25.60s report in the windowed run
was attributed to it and is not the same defect — see mode 2.

**Verified on the full 0–46s clip after the fix.** The baseline now holds 4
pre-existing marks over 5 frames where one frame found 2, **no report is made at
0.04s**, and the run completes 1150 frames at exit 0. Ground truth covers only
25–36s, so the full-clip output is not scored; what is established is that the
specific defect is gone. The earliest report is now t=1.64s, a different mark
that first appears mid-clip and is then detected in 98% of the frames after it —
consistent with a real Hit, and unlabelled, so not claimed as one.

**2. One mark is reported twice when registration displaces it. OPEN, and larger
than first recorded.** Two Bullet Holes 27 Board px apart, at 31.16s and 38.56s.
Across 363 frames they NEVER appeared together — 306 frames at one position, 49
at the other, 0 at both. Two genuine Bullet Holes co-occur constantly once both
exist. `merge_displaced_tracks` is the mitigation and is OFF by default.

**The 25.60s report belongs here too.** At `--start 25` the baseline holds three
marks and every later frame holds three detections, pairing 1:1. No mark was
missed. What happens is that the pairing distance grows:

| mark | from Target | 25.04s | 25.40s | 25.60s | 26.00s | 26.80s |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 57 px | 0.2 | 0.6 | 0.7 | 0.4 | 1.1 |
| B1 | 77 px | 0.2 | 0.3 | 1.7 | 1.7 | 3.0 |
| B2 | **118 px** | 0.6 | 1.8 | **3.4** | 3.2 | 4.2 |

Board px, against a `match_radius` of 2.96. B2 crosses at 25.60s — the exact
timestamp reported — and stays across. So the displacement **ramps and persists**
rather than spiking, and that matters: ADR-0003 separates flicker from marks, and
**a displaced mark is a perfectly persistent false positive.** Persistence is
structurally unable to filter it.

Widening baseline suppression to cover it was considered and rejected. It trades
away recall for genuine Bullet Holes near pre-existing ones, which is the failure
already measured on this clip (100% -> 75%) and the trap ADR-0003 records for the
40 template-px radius. The defence is disclosure, not suppression: see
`[REGISTRATION]` below.

**3. A confirmed Bullet Hole is never re-examined when it stops existing. NO
SURVIVING INSTANCE — it is the same mark as mode 1.** The 0.04s mark is detected
at 0.82-0.86 for its first ~3.8 seconds, then the detector returns **nothing at
conf 0.02** from 4.0s (nearest detection 116 px away) and never recovers it
through 25.0s, while the mark stays visible to the eye. It confirmed only because
its ~95 detected frames contain the 50-frame window.

Once the multi-frame baseline classifies that mark pre-existing, it is not
reported at all, and **no case remains of a genuinely new Bullet Hole that
vanished.** So no lifecycle, retraction or re-examination was built. Retraction
would have deleted this mark — a real one, visible to the operator — and any
threshold that catches a false positive here catches that too, because they are
the same signal.

What was built instead is disclosure. `_report` prints `first detected` and
`last detected` per Bullet Hole with the count of frames it was seen in, and the
Bullet Hole stays confirmed. **A detection ceasing is not evidence that the
Bullet Hole ceased** — recorded as
[ADR-0004](../docs/adr/0004-a-confirmed-bullet-hole-is-never-retracted.md). Re-run
the full clip after any change here and confirm no lifecycle case has appeared
before building one.

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

Cumulative drift is ruled out as the *mechanism*: seeding ECC from the baseline
instead of the previous frame reproduces the chained numbers to three decimals.
That rules out the tracker accumulating error. It does not rule out a growing
error, and on CamB there is one.

**The scene is stationary; the warp is not.** Over CamB 25.0-26.8s, comparing
each mark's position in the raw frame against its position in Board space:

| t | Target contour centroid, raw drift | B0 raw / board | B1 raw / board | B2 raw / board |
|---|---:|---:|---:|---:|
| 25.20 | 9.1 | 0.4 / 0.4 | 0.3 / 0.8 | 0.5 / 1.5 |
| 25.60 | 9.0 | 0.3 / 0.7 | 0.4 / 1.7 | 0.4 / 3.4 |
| 26.60 | 17.1 | 0.4 / 1.3 | 1.1 / 3.0 | 0.6 / 4.6 |
| 26.80 | 13.3 | 0.2 / 1.1 | 0.8 / 3.0 | 0.6 / 4.2 |

The three marks hold to **0.2-1.1 px in the raw frame** across the whole window.
Nothing physical moved — not the Board, not the camera. **Every
pixel of the Board-space displacement is introduced between raw-frame
coordinates and Board space.** The green-mask contour the front end keys on
wanders 3-17 raw px over the same frames.

**ECC correlation is not a registration-health metric.** It sat at 0.94-0.96
throughout, including the frames where B2 was 4.6 px out of place. It reports
that the fit converged, not that the geometry is acceptable. `process` now says
so on the `[BOARD]` line rather than printing a bare correlation figure.

**Registration is an open defect, not an out-of-scope item.** The measurement
above is 45 frames of one clip and does not overturn CamA's anchor-2 reading of
36.3 px at 38 px out, nor does it prove the mechanism is mask instability rather
than something downstream of it — only that the error enters with the warp while
the scene is still. Do not implement a new registration algorithm on this window
alone. Make the failure observable first, characterise it on the other clips and
the held-out recordings, and **if registration error approaches Bullet Hole scale
or threatens SOW 2.3.2's 5 mm, reopen the registration design and fix the cause
rather than add further downstream defences.**

`MAX_DISPLACEMENT_FRACTION` is scaled by distance on the strength of the
distance ordering, which CamB's three marks support (0.019x / 0.039x / 0.036x of
reach) and CamA's anchor 2 contradicts. It should be re-derived on footage with
more than one Target.

**The disclosure earns its keep on mode 2.** On the full clip the displaced pair
reports as #4 at 31.16s (detected in 85% of frames after it, last seen 45.96s)
and #5 at 38.56s (**21%**, last seen 41.72s against a clip running to 46s). One
of those two lines looks like a Bullet Hole and the other does not, and the
operator can now see which without opening the video. Nothing is retracted — the
count is still 5.

### Every run now reports what it could not do

Three disclosures, all of them cheap, none of them corrective:

- `[REGISTRATION] residual on N baseline-matched detection(s): median X Board px`.
  A residual is the distance from a detection to the baseline mark it matched —
  same physical mark, so the distance is registration error and nothing else.
  It needs no ground truth and no anchors: `strip_pre_existing` already computes
  it to decide suppression.

  **The max is censored and the median is the measurement.** A residual can
  never exceed the match radius, because a mark displaced further than that is
  not matched to the baseline at all — it is reported as a new Bullet Hole. Both
  labelled clips run into that ceiling:

  | clip | median | max | match radius |
  |---|---:|---:|---:|
  | CamA 13–25s | 4.5 | 8.1 | 8.1 |
  | CamB 25–36s | 1.5 | 3.0 | 3.0 |

  Board px. In template px the two medians are 11.1 and 10.1 — the same error in
  scale-invariant units across two clips, two cameras and two Board distances.
  That the max sits exactly on the radius in both is the ceiling, not a
  coincidence, and it means **displaced pre-existing marks are reaching the
  threshold on both clips, not only the one where a false positive was noticed.**
- `[WARN] truncated: processed N of M requested frames`, and confirmation is
  measured against frames actually read. **This is a short read, not a crash** —
  see the OpenCV pin below for the crash, which is a different failure and
  cannot be reported from inside `process` at all.
- `first detected` / `last detected` per Bullet Hole.

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

**A crash and a short read are different failures and no longer share a name.**
A **short read** — the clip ending early, a frame failing to decode — leaves the
interpreter alive, and `process` now reports `[WARN] truncated: processed N of M
requested frames` and measures confirmation against what it read rather than what
it asked for. A **crash** is exit 139 with the interpreter gone; `process` never
reaches its return and cannot report anything, and neither can `evaluate.py`,
which calls it in-process.

So the guard against the crash is not a report, it is
`test_environment.py`, which fails the suite in under a second if `cv2` or the
installed `opencv-python` is not the pinned build. That catches the cause — the
environment drifting off the pin — before a clip run is spent discovering it by
hand. An exit-code wrapper was considered and rejected: it tells you a run died,
a version assert tells you why, earlier, for less code.

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
| `PERSIST` | 0.50 | `new_bullet_holes.py` | Swept against ground truth; 0.70 lost most of the group. Counts distinct FRAMES since 2026-09-17 — see below |
| `PERSIST_FRAMES` | 50 | `new_bullet_holes.py` | Length provisional; *fixed* window is by design |
| `DEFAULT_CONFIDENCE` | 0.40 | `new_bullet_holes.py` | Swept; flat nearby |
| `BASELINE_FRAMES` | 5 | `new_bullet_holes.py` | Chosen as ~200 ms, not swept. Fixes the 0.04s defect at 5 and at 2; upper bound is the absorption risk, not a measurement |
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
