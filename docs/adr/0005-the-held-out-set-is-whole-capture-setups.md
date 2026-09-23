# The held-out set is whole Capture Setups, and none of it is trained on

Five new customer recordings, roughly 3–5 Bullet Holes each, all go to
evaluation. None becomes training data. They are split by **Capture Setup** —
camera pose, Board, lighting, distance — not by file and not by frame: two go to
threshold work, the rest are sealed, and sealed means no pixels are used for
anything, not even unlabelled background crops.

**The counts in that sentence did not survive measurement.** The delivery turned
out to be two customer Capture Setups of three recordings and two, so preserving
setup integrity inverted the split to three threshold-work and two sealed — see
"What the delivery turned out to be" at the end. The unit, a whole Capture
Setup, is the part of this decision that held, and it is the part that matters.

[ADR-0003](0003-a-bullet-hole-is-new-when-it-persists.md) records that every
threshold in the pipeline is tuned on six Bullet Holes in one clip and "will
overfit to it", and names the held-out test set as the only thing that settles
them. This is that test set, and what it may and may not be used for.

## Why none of it is trained on

Five recordings carry about twenty Bullet Holes. `dataset_audit.md` §6 puts the
bar for a reliable detector at roughly 1500 instances across 100 distinct
scenes; twenty instances across at most five scenes is not a training
contribution, and splitting them three ways leaves a final test set of four to
eight Bullet Holes — the same order as the six on CamA that `HANDOVER.md`
already says "says very little about the next one."

The same twenty are, however, the first footage that can answer whether the
pipeline works where nothing was tuned. That is the scarce thing, and spending
it on training buys nothing measurable and destroys the only thing it was good
for.

## Why the unit is a Capture Setup and not a file

The three CamA recordings are timestamped 14:14:46, 14:15:46 and 14:18:46 — one
afternoon, one camera, one Board, in three files. `dataset_audit.md` §5 found
the same shape in the training data: fifteen clips were roughly **nine**
visually distinct set-ups, the five `vsdc-sr-2025-02-19-*` clips were a single
41-minute session, and that one session supplied **40% of the entire dataset**.

Registration, `GREEN_LO`/`GREEN_HI`, `MIN_TARGET_AREA_PX` and net scale are all
properties of the physical set-up. Two files from one afternoon exercise none of
them independently, so holding out a *file* from a tuned session measures
re-detection of a scene already fitted, and reports it as generalisation.

If all five recordings turn out to be one Capture Setup, the result is **one**
held-out scene. The report says one.

## Why ground truth is photographs, not annotated frames

Ground truth is two labelled photographs of the Board per recording — before
firing and after. The set difference is the new Bullet Holes; `evaluate.py`
already registers such a photograph to the printed artwork, so positions taken
from a different viewpoint are comparable.

This is what makes leakage a non-question rather than a procedure. **No video
frame is annotated, so there are no adjacent frames to split.** The
frame-adjacency leakage measured in `dataset_audit.md` §3 — 40 of 42 validation
images with a near-duplicate in train, full-resolution MAD as low as 1.66 on a
0–255 scale — cannot arise against ground truth that contains no frames.

The *before* photograph is not bookkeeping. Scoring CamB against a single after
photograph credited the pipeline with finding a mark that was already on the
Board at the baseline frame, and an earlier revision of `HANDOVER.md` reported
F1 1.00 on that basis. A single final photograph cannot show when a mark
arrived. Two can.

Where footage is already shot and nobody can return to the Board, an operator
labels the first frame by hand. That is weaker evidence than a photograph, and
it is still independent of the detector, which is what makes it evidence at all.

## Why sealed means zero pixels

[ADR-0003](0003-a-bullet-hole-is-new-when-it-persists.md) names the right fix
for the gravel false positives as background frames with empty label files —
images, no annotation. That is cheap enough to be tempting to take from all five
recordings, on the argument that an empty label file teaches nothing about
Bullet Holes.

It teaches the background, and the background is the entire domain shift being
measured. A model trained on a sealed recording's gravel, lighting and Board
answers a weaker question than the one the sealed set exists to ask, and the
contamination is not visible afterwards — it cannot be un-seen in a checkpoint.

Negatives therefore come only from already-spent footage:
`CamA_20260914_141446.mkv` and `_141846.mkv`, which have never been analysed but
share a Capture Setup with `_141546` that every current threshold is fitted to,
plus the two threshold-work recordings. There is enough, so the strict rule
costs nothing.

## Consequences

**Split membership is recorded in a manifest keyed by sha256, and the tooling
enforces it.** A rename cannot change a role, a sealed recording is refused
without an explicit flag, and every run against sealed footage is appended to a
log with date, model and commit. "We only looked once" becomes a record rather
than a claim — which is what an acceptance conversation about SOW 2.3.6 will
want. The rule this protects is one that gets broken by accident, months later,
during a long sweep, by someone who was not party to the decision.

**The two threshold-work recordings may falsify a constant, not optimise one.**
They raise the evidence from two Capture Setups and nine Bullet Holes to at most
four and seventeen. A joint sweep over seventeen produces a number that looks
earned and is not; this project has already paid for that once, and ADR-0002's
0.5x shows what an earned threshold looks like — two populations measured and
separated, not a grid-search maximum. A constant that breaks on new footage
opens a diagnosis into the mechanism, the way the 38.6 px drift figure did.

**Detector evaluation and pipeline evaluation stay apart.** The photographs score
the pipeline. The detector is scored by per-Bullet-Hole detection rate — the
share of registered frames holding a raw box near a known position at a low
confidence floor — which needs no further annotation, runs on the rectified
Board canvas the runtime actually feeds the model, and is the generalised form
of the probe that found CamB's mark invisible at conf 0.02 for twenty-one
seconds. Frame-level mAP is annotated only where that probe shows the detector
is the problem.

**False positives are attributed, with an explicit `unknown`.** Registration
displacement is the one OPEN failure mode in `HANDOVER.md`, and a displaced mark
is a perfectly persistent false positive that persistence is structurally unable
to filter. The residual maximum sits exactly on the match radius on **both**
labelled clips — 8.1 of 8.1 on CamA, 3.0 of 3.0 on CamB — which is censoring,
not coincidence, and means displaced pre-existing marks reach the threshold on
both. Unattributed, a precision drop on new footage reads as a model problem and
sends the work to the wrong place.

No run is made unscoreable on the residual. There is no validated
registration-failure threshold tied to Bullet Hole scale or to SOW 2.3.2's 5 mm,
and inventing one from a single clip is the error this project keeps finding in
its own constants.

## What the delivery turned out to be

Measured 2026-09-22 on the six delivered files; grounds and figures in
[`../../ImageRecognitionService/capture_setups.md`](../../ImageRecognitionService/capture_setups.md),
roles in `recordings.json`.

**Three Capture Setups across the delivery, two across the five customer
recordings.** Not the one this ADR allowed they might collapse to, and not five.

The split came out **three threshold-work, two sealed** — the reverse of the
two-and-the-rest above. `CamB_20260915_102250` is one of the two clips every
current constant is fitted to, and its two unopened siblings share its camera
pose, Board and light. Sealing them would hold out a session already fitted and
report re-detection as generalisation, which is the thing this ADR names as the
error. The wide pair, `_101450` and `_101550`, is the only footage in the
delivery with a pose nothing has been fitted to, so it is what is sealed.

Which means the held-out set is one Capture Setup and roughly two Bullet Holes
— thinner than the two-to-four setups this ADR hoped for, and the honest size of
what arrived. The rule that the unit is a Capture Setup is what forced it; the
file count was never the thing being protected.

Negatives accordingly come from `cama-20260914`, `legacy-dev` and the three
`camb-20260915-close-one-board` recordings — the "two threshold-work recordings"
above is three.

The two CamA files this ADR names as spent, `_141446` and `_141846`, were not in
the delivery. They arrived on 2026-09-23 with a third, `_141646`, which this ADR
does not name; all three measure as `cama-20260914` and carry `spent`.
