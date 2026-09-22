# A Bullet Hole is new when it persists

A Bullet Hole is reported when it is absent from the baseline **and** is
still detected in at least **50% of the 50 frames following its first sighting**,
**and** change detection corroborates it.
Detection runs across the whole Board and is filtered afterwards; change
detection does not decide what the model looks at.

*Amended 2026-09-17: the baseline is the de-duplicated union of several frames
from `--start`, not the single frame this ADR was written against. A single
frame passed its own misses through as new Bullet Holes — measured on CamB, a
mark it missed was reported as new 40 ms later. The decision recorded here is
unaffected; only what "the baseline" names has changed. See `HANDOVER.md`.*

Once confirmed, it stays confirmed:
[ADR-0004](0004-a-confirmed-bullet-hole-is-never-retracted.md) records why.

This is the temporal analysis that [ADR-0001](0001-report-bullet-holes-not-hits.md)
recorded as an upgrade path and declined to build at the time. Building it does
not change that ADR's conclusion — see below.

## Why persistence, and not a better model

Across 30 sampled frames of `CamA_20260914_141546.mkv` at a 0.15 floor:

| Where the detection lands | Detections | Median confidence | Above 0.4 | Above 0.6 |
|---|---:|---:|---:|---:|
| On paper or Board | 135 | 0.71 | 109 | 88 |
| On dirt and background | **827** | 0.39 | 397 | 232 |

**86% of raw detections land on gravel** — dark specks on a light ground, which
is what the positive class looks like, and which the training set never
contained as a negative. Confidence cannot separate them: 397 of them still
clear 0.4, and a threshold high enough to exclude them starts discarding real
Bullet Holes.

Persistence separates them on a property no threshold captures. A Bullet Hole
appears once and then stays. Gravel and shadow detections flicker. On the 13–17s
window that criterion reduced **70 candidates to 7**.

The alternative on the table was a larger detector (`yolo26n` → `yolo26m`).
Capacity does not address this failure: the model is not short of parameters, it
is being asked about a texture nobody trained it on. The data fix — background
frames with empty label files — remains open and is the right one.

## Why the confirmation window is fixed, not "to the end of the clip"

The first implementation measured persistence as a fraction of all frames after
first sighting. That made the verdict depend on clip length: the same footage
reported 7 new Bullet Holes over 13–17s and 4 over 13–25s, because registration
drift over the longer run pushed real holes below the threshold.

A fixed 50-frame window makes the answer a property of the Bullet Hole rather
than of where the operator stopped the recording. `test_new_bullet_holes.py` pins
this, in `test_verdict_does_not_depend_on_clip_length` and
`test_unelapsed_window_is_not_reported`.

## Why change detection is evidence, not the gate

The obvious cheaper design runs `cv2.absdiff` against the baseline and hands
only the changed regions to the model.

Three counts are in play over the 13–17s window and must not be conflated.
**Six** is ground truth — the operator counted them off the footage. **Five** is
what this pipeline confirms. **Four** is how many of those five change detection
can see at all. The table below is scored against the five, because they are the
positions we have coordinates for; against ground truth the ceiling is worse
still, four of six.

Measured after registration and brightness normalisation:

| Threshold | Candidate regions | Known new Bullet Holes covered |
|---|---:|---|
| 1.5σ | 253 | **4 of 5** |
| 2σ | 110 | **4 of 5** |
| 2.5σ | 63 | **4 of 5** |
| 3σ | 27 | 3 of 5 |
| 4σ | 1 | 1 of 5 |

One of the five is invisible to change detection at *every* threshold; loosening
to 253 candidates does not recover it. As the sole candidate source, `absdiff`
would cap system recall near 80% before the model is consulted, against the 99%
in SOW 2.3.6. The likely cause is local misregistration — the paper is stapled
and curled, so the difference at that point is dominated by edge ghosting.

Change detection is therefore kept only as corroborating evidence for a
detection the model already made.

## The thresholds were wrong, and only ground truth showed it

The first values — a 70% persistence bar and a 40 template-px match radius — were
set by intuition. Scored against an operator-labelled photograph of the same
Board (`truth/kanatv6`, six Hits), they gave **1 true positive and 5 false**.

| Change | Why it was wrong | Result |
|---|---|---|
| persistence 70% -> 50% | the real Bullet Holes sat at 0.50-0.62; the bar rejected almost the whole group | recall 1/6 -> 4/6 |
| match radius 40 -> 20 template px | the radius also gates what counts as "already in the baseline", so it discarded a real Bullet Hole 125px clear of its neighbour | 4 -> 5 true positives |
| change evidence: metadata -> filter | every true Bullet Hole was corroborated; the false ones were not | 7 false -> 1 |

Final on that clip, against a complete six-label export: **TP 6, FP 1, FN 0** —
precision 86%, recall 100%, F1 0.92. Every Bullet Hole is placed within 15-22
template px, under one hole's width. The sixth was confirmed once the annotator
re-exported as boxes; an earlier segmentation export had truncated that label
mid-number, and the detection 26 template px away turned out to be the Bullet
Hole it described.

Change detection as a filter is doing most of the precision work: the same run
without it scores TP 6, FP 7, F1 0.63.

`evaluate.py` is what produced these numbers and is the reason the thresholds are
no longer guesses. It registers the ground-truth photograph and the video frame
to the same printed artwork, so positions taken from different viewpoints are
comparable, and matches one-to-one so a cluster of false positives cannot all
claim the same label.

A sweep over confidence, persistence, match radius and the change filter
confirms these four values are jointly optimal on this ground truth. That is
reassurance about the sweep, not about the values:
**they are tuned on six Bullet Holes in one clip and will overfit to it.**
They are better than intuition, not validated. The held-out test set remains the
only thing that settles them.

## Consequences

Nothing can be reported until its confirmation window has elapsed — about two
seconds at 25fps. This is affordable only because the latency budget was
relaxed to 5–10 seconds; it does not fit SOW 2.3.4's 0.5 seconds, which is
recorded as needing renegotiation.

The camera is not static (~16px drift over 12 seconds on this footage), so every
frame is registered to the baseline before positions are compared.

Both thresholds are working values, not measured ones. `MATCH_PX` (22) and the
70% fraction were set by hand against a single clip. Unlike the de-duplication
gate in [ADR-0002](0002-single-de-duplication-gate.md) — whose 0.5x sits in a
measured gap between two populations — these have no such justification yet, and
the held-out test set needed to earn them does not exist.

Recall on the only window with ground truth is **5 of 6**. That is the number to
beat, and it is far from SOW 2.3.6.

A Bullet Hole appearing within `PERSIST_FRAMES` of the end of the clip is **not
reported**, because its confirmation window has not elapsed. Shortening the
denominator to the frames that happen to remain is what made the verdict depend
on clip length in the first place, so the window is required to complete instead.
Any analysis must therefore run at least 50 frames past the last expected Hit.

Frames where registration fails are excluded from the denominator rather than
counted as a sighting missed. A lost frame is no evidence either way, and
counting it as absence let a run of registration hiccups push a real Bullet Hole
below the threshold. A registered frame with no detection does still count —
there, the model genuinely looked and saw nothing.

[ADR-0001](0001-report-bullet-holes-not-hits.md)'s conclusion is unchanged.
Temporal analysis recovers Bullet Holes that appear over time; it does not
separate two Hits through one Bullet Hole, which leaves no visual change in any
frame.
Reported counts remain a floor on Hits.
