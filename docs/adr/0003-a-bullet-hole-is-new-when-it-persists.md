# A Bullet Hole is new when it persists

A Bullet Hole is reported when it is absent from the baseline **and** is
still detected in at least **50% of the 50 frames following its first sighting**
(25 frames since the 2026-11-08 amendment below),
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

*Amended 2026-10-28: a Candidate persists as soon as the verdict can no longer
change, not only when its window ends. The window, the 50% and the Lost-frame
floor (#110) stay as they are. The verdict is fixed once the Looks with a
Detection would reach 50% even if every remaining due Look registered and saw
nothing, and the floor would hold even if every remaining due Look were Lost.
Rejection still waits for the window to end. On a recording, the Bullet Holes
reported are the same; only the moment they are reported moves. Live, Change
Evidence is first checked at that earlier moment, and then at each later Look
as before (the 2026-10-11 amendment below). The reason is Hit-to-report
latency. At a stride of about 5, a clean Hit's verdict is fixed about 0.8 s
after its first Detection, about 1.2 s before its window ends.*

*Amended 2026-11-02, accepted 2026-11-05 (#259): a Candidate that
was judged and did not persist, rejected or unconfirmable, stops gathering
Detections. The next Detection at its place opens a new Candidate, with a
window of its own, judged by the same 50% and the same floor. A persisted
Candidate keeps gathering, as before. A window that ended before a Look is
judged before that Look's Detections are matched, so past a stride's gap the
first Look of the next Candidate is not taken by one about to be rejected.
Before this, every later sighting folded into the dead Candidate and no
Candidate ever opened there again. On `CamA_20260914_141546` from 5 s,
truth #1's Candidate was seen on 18 of its 50 frames and rejected, and the
detector then saw it on 93% of the later Looks without reporting it. The
cost is that more Candidates reach Change Evidence, so precision rests more
on it. Early verdicts (2026-10-28) only ever persist early: a Candidate is
rejected, and so closed, only once its window has passed. It was accepted
on yolo26m, the production model, which passes the regression bench with it.
On yolo26n, kept for fast local runs, it adds false positives where n holds
phantom Baseline Marks on the green print of `CamA_20260914_141446`.*

*Amended 2026-11-08 (#310, #313, #314): the window is 25 frames, not 50.
Nothing else about Persistence changes: the 50%, the Lost-frame floor,
early verdicts and closing judged Candidates stay as they are. The window
is still counted in frames. At `LIVE_STRIDE` 4 it holds 7 Looks, of which
4 are needed, so a clean Hit's verdict is fixed on its 4th Look, 480 ms
after its first Detection, not 960 ms. A rejection waits 1 s. The 50 frames
were sized against gravel and shadow flicker, which the sheet canvases
([ADR-0011](0011-detection-is-limited-to-the-target-sheets.md)) no longer
show the detector. Measured on yolo26m, on regression footage only
([ADR-0010](0010-every-recording-may-be-opened.md)):
on the bench at stride 4, 25 frames lost no truth hole and added no false
positive against 50. It gained one truth hole (`CamA_20260914_141546` #4)
and reported every truth hole 0.48 s sooner, with Position Error unchanged.
False positives before the change filter were unchanged on every
recording. At stride 1 and all four shifts, stride 4 still loses nothing
against stride 1 ([ADR-0007](0007-live-input-is-sampled-at-a-fixed-stride.md)).
On the five unlabelled CamA recordings, 25 frames added two reports, and
review by hand classed both as real new Bullet Holes. In a Stream drop
replay, with the path deleted 0.2 s after truth #4's arrival frame for 5 s,
25 frames reported the same Bullet Holes as 50, with truth #4 reported after
the reconnect. A drop covering 4 of a window's 7 due Looks, about 0.5 s,
makes that Candidate unconfirmable under the Lost-frame floor, and #259's
reopening recovers it. 40 frames also
passed the bench and was not needed. #299's Change Evidence share rule
(the 2026-11-02 amendment below) was measured at 50 frames: if it is ever
revived, it must be re-measured at the window then in force.*

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

*Amended 2026-10-11: Persistence reaches the same verdicts on a recording and
live, but Change Evidence is checked at different times, on purpose. On a
recording it is checked once, after the last Look, against every corroborated
Detection of the run, at each persisted Candidate's final position. Live, it is
checked when the Candidate persists, against the Detections corroborated so
far, at its position then; if none corroborates it, it is checked against each
later Look's, at its position at that Look. Unifying the two is the obvious
tidy-up, and it changes recording results. The thresholds in this ADR and
[ADR-0007](0007-live-input-is-sampled-at-a-fixed-stride.md)'s stride table were
measured with the end-of-run check, and the Sealed recordings cannot be run
again to re-measure them ([ADR-0005](0005-the-held-out-set-is-whole-capture-setups.md)).*

*Amended 2026-11-02 (#299; measured, not adopted): both checks accept
Change Evidence that arrives after a Candidate's window, and on a recording
from any Detection near its final position, its own or not. That is how
marks already on the Board pass once #259 lets them persist. The baseline
missed them because the detector's score on anything stationary, a mark, a
ring edge or plain paper, wanders for the whole run. A rule was measured
that replaces both checks: a persisted Candidate is corroborated when at
least 50% of its own Detections in its first window are, the same 50% as
Persistence, and it is reported early only once both verdicts are fixed.
On regression footage only ([ADR-0010](0010-every-recording-may-be-opened.md)),
at stride 4 and stride 1, the lowest truth hole was at 62% and 64%, and the
false positives #299 found were at most 43% (stride 4, one 0.48 s burst)
and 0%. It lost no truth hole, removed every false positive of that kind,
and added no latency at the median and 800 ms at most, on the 62% hole. It
is not adopted: #259's other added reports are 67–100% corroborated, so no
share that keeps every truth hole removes them. #300 attributed them
(2026-11-05): registration since fixed, a light patch since gone, a bird
resting on the sheet, and real holes on a recording thought empty.
Re-measured on the sheet canvases
([ADR-0011](0011-detection-is-limited-to-the-target-sheets.md)), every
on-sheet truth hole on `CamA_20260914_141546` shows Change Evidence on
96–100% of its Looks. The on-sheet hole the run misses is missed by the
detector, not by change detection. The 13–17 s measurement above, of one
hole change detection could not see, stands as history: it was made on the
whole Board, before the sheet canvases.*

## The thresholds were wrong, and only ground truth showed it

The first values — a 70% persistence bar and a 40 template-px match radius — were
set by intuition. Scored against the photograph-derived truth of the same
Board (`ImageRecognitionService/data/truth/cama-20260914-141546`, six Hits), they give **2 true positives,
5 false and 4 missed**. (First measured on an earlier annotation of this
recording, since superseded as unreliable; every figure in this section is
re-measured on the canonical truth, and the conclusions are unchanged.)

| Change | Why it was wrong | Result |
|---|---|---|
| persistence 70% -> 50% | the real Bullet Holes sat at 0.50-0.62; the bar rejected almost the whole group | recall 2/6 -> 5/6 |
| match radius 40 -> 20 template px | the radius also gates what counts as "already in the baseline", so it discarded a real Bullet Hole 125px clear of its neighbour | 5 -> 6 true positives |
| change evidence: metadata -> filter | every true Bullet Hole was corroborated; the false ones were not | 7 false -> 1 |

Final on that clip: **TP 6, FP 1, FN 0** — precision 86%, recall 100%, F1
0.92. Every Bullet Hole is placed within 2-7 template px, under one hole's
width.

Change detection as a filter is doing most of the precision work: the same run
without it scores TP 6, FP 7, F1 0.63.

`evaluate.py` is what produced these numbers and is the reason the thresholds are
no longer guesses. It registers the ground-truth photograph to the recording's
baseline frame and reaches the printed artwork through that frame's own
homography, so positions taken from different viewpoints are comparable, and
matches one-to-one so a cluster of false positives cannot all claim the same
label. (Registering the photograph straight to the artwork, as it first did,
held on CamA and fails on photographs where the artwork is a small part of the
picture — #40.)

A sweep over confidence, persistence, match radius and the change filter
confirms these four values are jointly optimal on this ground truth. That is
reassurance about the sweep, not about the values:
**they are tuned on six Bullet Holes in one clip and will overfit to it.**
They are better than intuition, not validated. The held-out test set is the
only thing that can test them, and it tests them as they stand: they are fixed
before the sealed run, which evaluates them once and does not re-set them
([ADR-0005](0005-the-held-out-set-is-whole-capture-setups.md)).

## Consequences

Nothing can be reported until its verdict can no longer change (the
2026-10-28 amendment above). A clean Hit's verdict is fixed before its window
ends, 480 ms after its first Detection at stride 4 (the 2026-11-08
amendment). A marginal Candidate, and every rejection, still waits out the
whole window, 1 s at 25fps. This is affordable only because the latency budget was
relaxed to 5–10 seconds; even the early case does not fit SOW 2.3.4's 0.5
seconds, which is recorded as needing renegotiation.

The camera is not static (~16px drift over 12 seconds on this footage), so every
frame is registered to the baseline before positions are compared.

Both thresholds are working values, not measured ones. `MATCH_PX` (22) and the
70% fraction were set by hand against a single clip. Unlike the de-duplication
gate in [ADR-0002](0002-single-de-duplication-gate.md) — whose 0.5x sits in a
measured gap between two populations — these have no such justification yet, and
the sealed run cannot supply one. It evaluates the values fixed before it, and
tuning them on what it reveals would spend it ([ADR-0005](0005-the-held-out-set-is-whole-capture-setups.md)).

Recall on the only window with ground truth is **5 of 6**. That is the number to
beat, and it is far from SOW 2.3.6.

On a recording, a Bullet Hole appearing within `PERSIST_FRAMES` of the end of
the clip is **not reported**, because its confirmation window has not elapsed.
That holds even when its verdict was fixed early: reporting it would make a
recording's results differ from the end-of-window verdicts, which the
2026-10-28 amendment keeps identical. Shortening the denominator to the frames
that happen to remain is what made the verdict depend on clip length in the
first place, so the window is required to complete instead. Any analysis must
therefore run at least `PERSIST_FRAMES` (25) frames past the last expected Hit.

Live, a Range has no clip end to wait for. A Candidate whose verdict was fixed
early is reported at once and stays reported
([ADR-0004](0004-a-confirmed-bullet-hole-is-never-retracted.md)); one still
undecided when the Range ends is unconfirmable, not rejected.

Frames where registration fails are excluded from the denominator rather than
counted as a sighting missed. A lost frame is no evidence either way, and
counting it as absence let a run of registration hiccups push a real Bullet Hole
below the threshold. A registered frame with no detection does still count —
there, the model genuinely looked and saw nothing.

Excluding lost frames has a floor (#110): a window in which fewer than
`PERSIST` of the frames the loop tried to register did register confirms
nothing, and is unconfirmable rather than rejected, like a window that has not
elapsed. Frames tried, not frames in the window: a frame never read, such as a
stride gap (#81), is no registration failure, and a stride of 13 leaves ~4 looks
a window on purpose. 100% of one look is not
persistence. Measured on `CamA_20260914_150248` once its pan frames were counted
lost: two wrong fits that survived among them confirmed 9 false Bullet Holes on
1–2 looks each. Clips that lose no frames are unaffected.

[ADR-0001](0001-report-bullet-holes-not-hits.md)'s conclusion is unchanged.
Temporal analysis recovers Bullet Holes that appear over time; it does not
separate two Hits through one Bullet Hole, which leaves no visual change in any
frame.
Reported counts remain a floor on Hits.
