# Bullet Hole Detection — Handover

**As of 2026-09-17.** Branch `feature/test-labels-and-eval`.

**Persistence counts frames, not sightings** (fixed 2026-09-17). The detector
boxes a torn mark as two halves and both fold into one candidate, so a frame was
counted twice and a Bullet Hole could clear the bar on fewer distinct frames than
the bar asks for. `min(ratio, 1.0)` was hiding it — the only symptom was a
persistence wanting to exceed 100%. CamA scored unchanged after the fix —
13–25s TP 6 / FP 1 / FN 0, F1 0.92 with every persistence value identical.
What moved is CamB's torn
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

| Clip | Window | Labelled | TP | FP | FN | Precision | Recall | F1 | FP attributed to |
|---|---|---|---|---|---|---|---|---|---|
| `CamA_20260914_141546.mkv` (`truth/cama-20260914-141546`) | 13–25s | 6 | 6 | 1 | 0 | 86% | 100% | 0.92 | detector, 827 tpl px out |
| `CamB_20260915_102250.mkv` (`truth/camb-20260915-102250`) | 0–46s | 4 | 4 | 1 | 0 | 80% | 100% | 0.89 | detector, 855 tpl px out |

Bullet Holes placed within 2–28 template px — under one hole's width. Both
surviving false positives attribute to the detector: CamA's at 827 template px
from anything pre-existing, CamB's a 62%-persistent report at 38.56s, 855 px
out. The registration-displacement case ADR-0006 was built on — a 25.60s
report in CamB's old 25–36s window — does not arise over the whole clip,
because the mark it was a displaced sighting of is reported at 1.64s, when it
arrived. Measured 2026-09-27; figures below that do not say otherwise date from
the 2026-09-17 re-verification.

**Since #40 (2026-09-27) the truth photograph is registered to the baseline
video frame**, over the whole picture, and reaches template space through
that frame's homography — no longer straight to the artwork, which on the CamB
photographs threw labels up to 58 000 template px out. CamA reproduces, its
pairs moving from 9–16 to 2–7 px; CamB's truth could not be scored before it
(TP 1 / FP 3 / FN 3 over 25–36s). The threshold-work pair scores for the first time:
`_102450` TP 2 / FP 0 / FN 2 (both misses off the canvas, #41) and `_103223`
TP 2 / FP 1 / FN 0.

**CamB is scored over the whole clip, 0–46s**, because that is what its
truth covers: the before photograph predates the recording. Over the old
25–36s window the same truth reads 4 / 0 / 0, F1 1.00 — flattered, because
one of its four new Bullet Holes arrived at 1.64s and a displaced sighting of
it at 25.60s is credited to it. (The frame-labelled 25–36s annotation,
formerly `truth/camb-25-36`, was superseded and removed because its annotation
quality was not trusted.) A derived score now prints `[PLACEMENT]`: the after
photograph's pre-existing marks against the run's baseline, 3–16 and 6–12 px
on those two — the placement's own error, measured on every run. Truth with no
pre-existing mark (CamA's) prints `[WARN] placement unverified` instead. Which
export lines were pre-existing is recorded by line number in `board.source.txt`
(`pre-existing-export-lines`), so correcting a label in `board.new.txt` does not
change it. 174 tests pass.

**Every figure in this document was re-verified on 2026-09-17 after the
memory-safety fix below**, on `opencv-python==4.10.0.84`. All three F1 scores,
the drift ranges, the ECC medians, the co-occurrence counts and the anchor
measurements reproduced unchanged. The runs are *not* bit-identical across the
OpenCV change — CamA's baseline detected 4 pre-existing marks where it had found
5, and persistences moved a point or two — because 4.10 and 5.0 letterbox with
different resize implementations and marginal detections land either side of the
confidence floor. That the aggregates survived that perturbation is a stronger
check than bit-equality would have been.

An earlier revision of this file reported CamB as F1 1.00 against a single
after-photograph's labels. That figure was wrong: it credited the pipeline with
finding a pre-existing mark, which is what the before photograph now prevents.

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

Pre-existing marks are no longer worked out by hand: the derivation in
`evaluate.py` — `derive_truth.py` is its command line — subtracts the before
photograph's labels, and every recording gets the same treatment from a
photograph pair.

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
| `CamB_20260915_103223` | 12 | 10 | **2** | 0.8941 |

**Both passes now come from one detection-format delivery** — `Before_
Annotated` and `After_ Annotated`, re-annotated as boxes after the first
delivery arrived as polygons. All twelve label files are `class cx cy w h` on
every line, no polygons and no mixed files, so nothing is reported as mixed any
more. The marks moved 0.001–0.003 in normalised photograph coordinates from the
polygon pass, which is a re-draw of the same holes.

CamA's before photograph is clean, so all six after labels are new.
(`kanatv6` was an older annotation set for this recording, superseded as
unreliable and removed; nothing here is measured against it.)

**The derivation registers twice, and the second time on the marks
themselves.** The artwork is a sixth of these photographs, so an ECC
homography fitted to it is extrapolating everywhere else, and the residual
grows with distance from it: on `CamB_20260915_103223`, 1.4 px on the Target
and 6–7 px a Target-span away. That left two before-marks unpaired at 7.3 and
6.14 px against a 6.1 px tolerance, and each unpaired before-mark is a
pre-existing mark counted as a new Bullet Hole. Cropping the photographs of
both marks settles what they are: the same hole, in both photographs, displaced
— not a new hole beside an old one, which would show two holes in the after
photograph and shows one.

So the marks the first registration *did* agree on become the correspondences
for a second one. They are spread over the whole Board rather than the sixth
of it the artwork covers, and a similarity — 4 degrees of freedom against 8
correspondences — cannot bend to fit noise. It replaces the homography rather
than correcting it, because two photographs taken from nearly the same place
are related by something close to a similarity, and the perspective the
homography adds only holds where it was fitted. Correcting H instead was tried:
0.2–4.7 px and one mark still unpaired, against 0.1–1.5 px and none.

Re-matching happens at the **same** tolerance, so a refit can only pull the
same mark together, never widen what counts as one mark — the criterion that
two distinct marks are not folded together is untouched. It is kept only if it
matches at least as many marks as the artwork registration did, and is refused
below 4 correspondences, where a similarity reproduces its own input and says
nothing. `board.source.txt` records whether it was used.

On `CamB_20260915_103223` that takes the residuals from 1.4–7.3 px to
0.1–1.5 px, pairs all ten before-marks, and leaves **2** new Bullet Holes: one
high on the white Board and one at the top of the green silhouette. The
operator confirms those two independently. `CamB_20260915_102450` also refits
(0.2–0.7 px, from 0.7–4.7) and its answer is unchanged; the other four have too
few pairs to refit and are untouched.

`evaluate.py` warns when a derived file still has unpaired before-marks: it
reads `board.source.txt` beside the labels it was given. No recording trips it
now, which is the point — it is there for the next delivery.
Pointing `--truth-labels` at a derived directory also picks `board.new.txt`
rather than `board.after.export.txt`, which sorts first and would have scored
the run against the pre-existing marks as well. Where there is no derived file
to prefer, a directory of several `.txt` files is now refused by name instead
of resolved alphabetically — beside `board.txt`, that first file is
`board.before.txt`.

**That is ten Bullet Holes across two clips** — the threshold-work pair adds
six, for falsification only. The thresholds are jointly
optimal on exactly this sample and that says very little about the next one. SOW
2.3.6 asks for 99% over a statistically meaningful sample, which this is not.

## The threshold-work recordings: what held, what broke

Run end to end on 2026-09-27 at `7ef2ffe`, after #34 and #40, at current
constants — [`falsification_run.md`](falsification_run.md) has the counts, the
probe, the residuals and a verdict per constant. No constant moved.

| Recording | Window | New | TP | FP | FN | Precision | Recall | F1 | FP attributed to |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `CamB_20260915_102450` | 0–47.76s | 4 | 2 | 0 | 2 | 100% | 50% | 0.67 | — |
| `CamB_20260915_103223` | 0–51.88s | 2 | 2 | 1 | 0 | 67% | 100% | 0.80 | detector, 255 tpl px out |

Placement error (`[PLACEMENT]`) is 3–16 and 6–12 template px. Every new Bullet
Hole on the canvas was found and scored by the scorer; the one false positive
is a real object — insect or debris — that persistence and change evidence pass
by construction.

**One constant breaks: the canvas ends before the Board does (#41).** Both
false negatives, and two of `_103223`'s pre-existing marks, sit below the
canvas the detector is given; a third new Bullet Hole is on its edge.
`BOARD_MARGIN` bounds recall, and on this setup it binds.

**The canvas was not widened; the run discloses the gap instead.** Making the
canvas the whole camera view was measured: net scale held (0.90–0.91, `imgsz`
follows the canvas) but CamA fell from TP 6 / FP 1 / FN 0 to 5 / 2 / 1, F1
0.77 — its canvas already misses a third of its view, and any change to the
canvas moves its marginal detections. So every run now prints `[WARN] N% of
the camera's view is off the canvas`, with how many Target spans it runs past
each edge (`board.uncovered_view`): 94% on the CamB close pose, reaching 4–5
spans below, and 34% on CamA, to the sides — counted in frame pixels, which
on these near-square-on views agrees with Board-plane area to 0.4 points. It
is the camera view, not the Board — gravel included — because nothing detects
the plywood. A second warning fires at the end if any registered frame put
the view further off the canvas than the baseline did. It fires on the still
CamB close pose too: reach is the frame corners, extrapolated 4–5 spans from
the one Target, and ran 4.4–7.0 spans left frame to frame over 3 s while the
fraction held at 94%. It is registration noise there, not a moving camera, and
the line says it cannot tell which. `[PLACEMENT]` cannot match off-canvas
pre-existing marks, but still warns on them: the Board running past the
canvas and a wrong placement throwing them there look the same from here.

**Registration error grows with distance from the Target (#46, measured
2026-09-28, `registration_reach.py`).** Every mark labelled on the before
photograph is stationary on the Board, so its Board-space wander over the
recording is registration error at that distance. Each is tracked in the raw
frame by NCC (synthetic sub-pixel shifts recovered to 0.3 frame px; median NCC
0.91–0.95 on footage), then carried through that frame's homography. Template
px from the mark's baseline position; distance from the ring centre in Target
spans (1072 template px):

| Recording | ≤ 0.5 spans: median / p95 | 0.6–0.8 spans | 1.2–1.3 spans |
|---|---|---|---|
| `_102450` | 5–10 / 10–17 (4 marks) | 13–17 / 23–36 (2) | — |
| `_102250` | 6–14 / 14–31 (2) | — | — |
| `_103223` | 11–15 / 20–22 (5) | 10–18 / 19–31 (3) | **31–34 / 66–73** (2) |

`MATCH_TPL_PX` is 20. Near the Target, p95 already sits at it on `_103223`
(the registration defect recorded above); by 0.8 spans it is past it on both
recordings that reach that far, and at 1.2–1.3 spans — where `_102450` truth
#3 and #4 sit, 1.17 and 1.26 on this scale, not the ~1.7 quoted earlier —
median error is 1.6× and p95 3.5× the match radius. `_103223` #10 moves
7.5 frame px raw yet 73 template px in Board space, so extrapolating the
homography accounts for it, not only sheet motion. **So far-field registration must be fixed
before the canvas grows**; a sheet-edge canvas would search Board whose
positions do not hold still. Gaps: CamA's before photograph labels no marks,
so CamA is unmeasured; the only marks past 0.8 spans are two, both on
`_103223`, both below the Target.

**CamA, supplementary: wander after appearance** (`--appeared`, not baseline
marks). CamA's six new Bullet Holes, each tracked from its first detection in
the 2026-09-28 run (14.64–18.52s) to 25s, sit at 0.70–0.90 spans: median 4.5–11.5,
p95 9–22 template px, one of six over `MATCH_TPL_PX`, NCC 0.82–0.93. Not
comparable with the table above: it omits the drift from the baseline to each
arrival, and CamA's pose is closer (1 frame px ≈ 2.2 template px, against ≈ 6
on the CamB close pose). Nothing on CamA lies past 0.9 spans. Finding
appearance from pixels instead misfired — CamA's blurred rings matched a hole's
patch up to 3.5 s before it arrived — and was dropped.

**Registering on the Board's texture, against the baseline frame, holds the far
field (#50, measured 2026-09-28).** `registration_reach.py --registration`
scores alternatives with the same probe, and the runtime is unchanged.

**How it registers.** The anchored modes keep the baseline homography H0 and
register each frame to the **baseline** frame, not the previous one: H = W · H0.
`texture` (#50 B) fits W to the greyscale frame, with `--motion homography`.
The fit uses ECC's own mask over a square within 1.5 Target spans of the ring;
its corners reach about 2.1 spans. A hole of `PATCH + SEARCH` is cut around
every mark being scored, so no mark helps register itself. The mask is passed
to ECC rather than multiplied into both images, because a fixed edge in both
images pulls W towards no motion.

p95 in template px:

| Recording | Runtime | Texture homography |
|---|---|---|
| `_103223` ≤ 0.5 spans | 20–22 | **5–7** |
| `_103223` 0.6–0.8 | 19–31 | **3–5** |
| `_103223` 1.2–1.3 | 63–66 | **9.3 / 10.3** |
| `_102450` ≤ 0.5 | 10–17 | **3–7** |
| `_102450` 0.6–0.8 | 23–36 | **4–5** |
| `_102250` ≤ 0.5 (#2 / #1) | 13.6 / 30.5 | **5.0 / 6.7** |
| CamA `--appeared` 0.7–0.9 | 9–22 | **5–9** |

**Both of #50's probe criteria pass.** The far field is at half of
`MATCH_TPL_PX`, and every mark on every recording improves. It also runs in
about half the runtime chain's time, ~4 min against ~8 per CamB recording,
because ECC runs at half resolution.

**The first, pre-mask run was worse.** A (`affine`: an affine fitted to the
green mask) reached p95 21–22 at 1.2–1.3 spans, and texture 16–20. That run had
the region multiplied into the images and the marks inside it. It was not
repeated for A.

**The yardstick was tightened for this (`f4d6c77`).** `locate` refuses an NCC
peak on the search window's edge, because a peak there is not a maximum. Under
the first texture run, CamA #2 flipped to a neighbour exactly `SEARCH` px away,
reading as p95 38. Such frames are counted in the new `skipped` column. That
rule censors wander past `SEARCH`, so it favours whichever mode wanders most.
Here that is the runtime: it skips 17 and 74 frames on `_103223` #9 and #10,
while texture skips at most 1 on any CamB mark, and 2 on CamA #2.

**Drift / jitter split (#50 C).** Each row reports p95 drift (a rolling mean
over 25 found frames, 1 s at 25 fps) and p95 jitter (the rest). Under the
runtime, `_103223`'s far marks are 50–55 drift and 34–36 jitter. Under texture,
jitter is 1.6–3.2 everywhere and drift at most 9. Smoothing would buy little
more.

**Next is the runtime change,** scored with `evaluate.py` on all four recordings
against #46's 8/16/32 px canvas-shift control. Before that, one more check: the
fit's baseline frame is the recording's first frame, and ECC against it
degrades as new Bullet Holes accumulate. Nothing here shows it yet, since lost
and skipped counts are 0–2, but these windows are under a minute.

The first run of this record, before #40, scored both recordings F1 0.00 with
probe rate 0.00 on every label. **That was the photograph registration, not the
pipeline** — labels thrown up to 58 000 template px off the Board — and it is
superseded. Both recordings share `_102250`'s Capture Setup, so this adds
Bullet Holes and no setup.

## The held-out set is two recordings of one Capture Setup

The six delivered files are **three** Capture Setups, and the five customer
recordings are **two** — not the one ADR-0005 allowed they might collapse to.
Which recording carries which role is `recordings.json`, and the grounds are
[`capture_setups.md`](capture_setups.md); neither is restated here, so that
changing an allocation is one edit and not three.

**The split came out three threshold-work / two sealed, not the other way
round.** `CamB_20260915_102250` is in the results table above; every current
constant is jointly fitted to it and CamA. Its two unopened siblings share its
camera pose, Board and light, so sealing them would hold out an arrangement
already fitted and report re-detection as generalisation — the error ADR-0005
exists to prevent. The wide pair is the only footage here with a camera pose
nothing has been fitted to, so the wide pair is what is sealed. Two recordings,
roughly two Bullet Holes: a thin held-out set, and the only one the delivery
contains.

**CamB is the first footage where a bullet landed on a Target** — two of its
four, scoring 7 and 8. Until it arrived, Target assignment and ring scoring had
only unit tests behind them.

Recall is 100% on both fitted clips with the `yolo26n` weights, *within the labelled
windows*. That is **not** enough to close `yolo26n` vs `yolo26m`: two recordings
is not the held-out test set, and model selection still waits on it (blocked
item 2).

It is also not the whole story about recall. Outside the labelled window, on the
full 0–46s CamB clip, the detector loses a mark that is still plainly visible.
It finds it only on and off from 4.0s, not at all from 12.40s onward, while the
operator still sees it at 25.0s — see "Three failure modes" below, which also
corrects the earlier "21 seconds" figure.

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
    --truth-labels truth/cama-20260914-141546
# Derived truth names its own photograph in board.source.txt; --truth-image
# is then optional, and one that disagrees is warned about by name
.venv/bin/python evaluate.py videos/CamB_20260915_102250.mkv --start 0 --end 46 \
    --truth-labels truth/camb-20260915-102250

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
copy: in a derived truth directory `board.after.export.txt` is the export's
bytes unchanged, and `board.new.txt` is the file the evaluation reads.

**Every recording needs a manifest entry before any tool will open it.**
`recordings.json` maps sha256 to Capture Setup, role (`sealed`,
`threshold-work` or `spent`), frame rate and analysis window, plus a
`window_basis` line saying whether that window was verified against labelled
ground truth or is a provisional whole-clip stand-in. No tool reads
`window_basis`; it is there so an operator does not trust a window nobody
established. A file in no entry is refused, and so is an entry whose role is none of those three —
an unallocated recording has no role, and guessing one is how the held-out set
gets spent. All six delivered recordings now carry one, grouped and allocated
in [`capture_setups.md`](capture_setups.md). A recording arriving later needs
its hash taking first:

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
| `truth/<recording>/` | Ground truth, one directory per recording |
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
0.04s**, and the run completes 1150 frames at exit 0. Scored over the whole
clip against `truth/camb-20260915-102250` it reads TP 4 / FP 1 / FN 0 (see
the results table), so the specific defect is gone. The earliest report is now t=1.64s, a different mark
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

**The 25.60s report no longer has to be worked out by hand.** Run over
25–36s, `evaluate.py`'s attribution put it 29 template px from the nearest
mark on the Board at the baseline frame, against a suppression radius of 20 —
`displacement`. That distance is the pipeline's own baseline and needs no
annotation; the mark it was displaced from is the one the canonical truth has
arriving at 1.64s. Over the whole clip, which is how CamB is now scored, the
report does not arise. See [ADR-0006](../docs/adr/0006-every-false-positive-is-attributed.md).

**3. A confirmed Bullet Hole is never re-examined when it stops existing. NO
SURVIVING INSTANCE — it is the same mark as mode 1.** The 0.04s mark is detected
at 0.82-0.86 for its first ~3.8 seconds. After that, the shared frame loop at
conf 0.02 finds it only on and off: 40 of 526 frames between 4.0s and 25.0s,
most of them in 6.2–9.1s, and the last at 12.36s. **From 12.40s it is never
detected again**, through the clip's end at 45.96s, while the operator can still
see it at 25.0s. It confirmed only because its ~95 detected frames contain the
50-frame window.

Measured with `probe.py --at 774.8,1417.7` on the full clip. That is the mark's
template position in frame 1 (0.04s), found as HANDOVER defines the mark: the
conf-0.40 detection that frame 0 lacks and frames 1–4 hold, 128 Board px from
anything in frame 0.

**Correction (2026-09-23).** This paragraph used to say the detector returns
"nothing at conf 0.02 from 4.0s (nearest detection 116 px away) and never
recovers it through 25.0s". That was wrong. The 2026-09-17 probe behind it was
reproduced exactly, down to the decimal (4.0s: 115.9, 10.0s: 103.9, 25.0s: 98.4
Board px). It had two defects that compounded:

1. **Its coordinates did not stay on the mark.** Each sampled frame was
   registered with a fresh `board.build_view` and got its own Board space,
   whose scale ranges from 0.141 to 0.187 over the clip. It was then compared
   with one fixed Board-px point taken from t=0. At 6.0s the old probe reported
   57.4 Board px; the same detection is 12.2 template px from the mark, inside
   the 40 px radius. Run on every frame instead of ten, that comparison still
   finds a single detection after 4.0s (6.40s).
2. **It sampled sparsely.** It looked only at t = 2, 4, 6, 8, 10, 14, 18, 22, 24
   and 25s. With coordinates that do stay on the mark, whole-second samples
   catch at most 2 of the 40–55 frames that hold a detection, so sampling alone
   would still have read as "gone".

The two registrations also disagree about when the mark is last seen. Under a
fresh view per frame, measured in template space, there are 55 detections
after 4.0s and the last is at 19.24s. Under the chained registration the
runtime uses, the last is at 12.36s. The 12.40s figure is therefore a statement
about what the runtime sees, not a registration-independent fact.

The conclusion holds: a real mark stops being detected while it is plainly
visible, for at least 12.6 s. Only the onset moved, from 4.0s to 12.40s.

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

Four disclosures, all of them cheap, none of them corrective:

- `[ATTRIBUTION] N false positive(s): a displacement, b detector, c unknown`, from
  `evaluate.py`. Every false positive in a scored run gets a likely cause and its
  distance to the nearest mark that was already on the Board, and the counts
  above it are untouched by it. See
  [ADR-0006](../docs/adr/0006-every-false-positive-is-attributed.md).
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

  `evaluate.py` repeats this line under every score, in template px, whether or
  not any detection matched a baseline mark. It is a disclosure and nothing
  more: **no run is refused or marked unscoreable on the strength of its
  residual.** No registration-failure bar has been validated — not against
  Bullet Hole scale, not against SOW 2.3.2's 5 mm — and deriving one from a
  single clip is the error this project keeps finding in its own constants.
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
outside the frame. `[ATTRIBUTION]` puts it on the detector, 827 template px from
anything that was already on the Board, so it is not registration displacement
wearing a detector's clothes.

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
| `BOARD_MARGIN` | 0.50 | `board.py` | Bounds recall; see above. **Breaks** on both threshold-work recordings — #41. Unchanged: the whole-view canvas regressed CamA; the run warns what the canvas leaves out |
| `GREEN_LO` / `GREEN_HI` | — | `board.py` | One artwork, one lighting condition |
| `MIN_TARGET_AREA_PX` | 5000 | `board.py` | May reject distant Targets |

`MATCH_TOLERANCE_TPL` (40 px, `evaluate.py`) is provisional too — it is the
*scoring* tolerance, not a pipeline threshold. Matches land at 2–28 template
px against it on the fitted clips and 5–23 on the threshold-work pair, whose
one false positive is 255 px out — supported there, weakly, because nothing
lands near 40. Encouraging, and not validation across a dataset.

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

`mine_negatives.py` makes them, from spent and threshold-work footage only — it
refuses sealed recordings outright, with no flag. It covers the gravel and not
the rings: an empty label file on the Board would be a lie, because the Board
carries Bullet Holes. On 2026-09-23, over every recording the manifest does
not seal, it yields **15** negatives, all `cama-20260914`: 5 from `_141546`,
4 from `_144747`, 3 from `_150248`, and 1 each from `_141646`, `_141846` and
`_145047` (`negatives/sources.csv` is the record). Near-duplicates are dropped
across the whole Capture Setup, so its seventh file, `_141446`, adds nothing new. Nothing comes from the CamB close trio,
whose canvas is all Board, or from the legacy clips, which carry no green Target.
A static camera gives only a few distinct gravel tiles per clip, so more
negatives means more Capture Setups, not a smaller `--step`.

`yolo26.yaml` and `yolo26-p2.yaml` are both present in the installed ultralytics
(8.4.126), so `m` and the P2 experiment are available whenever the test set makes
them measurable.
