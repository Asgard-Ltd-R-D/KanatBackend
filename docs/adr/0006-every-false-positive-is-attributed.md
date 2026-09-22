# Every false positive is attributed, and no run is refused on its residual

Every false positive in a scored run is reported with a likely cause:
**registration displacement**, **detector**, or **unknown**. The cause sits
underneath the headline TP / FP / FN counts and changes none of them, and the
registration residual is printed alongside every score. Nothing is refused,
withheld or marked unscoreable on the strength of that residual.

## Why a false positive needs a cause at all

[ADR-0003](0003-a-bullet-hole-is-new-when-it-persists.md) confirms a Bullet Hole
when it persists. A pre-existing mark that registration has displaced past the
suppression radius **is** persistent — perfectly so, because it is a real mark
sitting still — and so it is reported as a new Bullet Hole. Persistence is
structurally unable to filter it, and `HANDOVER.md` carries it as the one OPEN
failure mode.

That failure is invisible in a score. It arrives as one more FP, indistinguishable
from a detector error, and a precision drop on new footage therefore reads as a
model problem. `HANDOVER.md` records two of three investigated failures as having
been mis-diagnosed exactly that way. With five customer recordings about to be
spent on model comparisons ([ADR-0005](0005-the-held-out-set-is-whole-capture-setups.md)),
an unattributed FP is a model comparison confounded by how far registration
displaced marks that day.

Measured on the two labelled clips, they fail differently and it shows:

| clip | FP | nearest pre-existing mark | attributed to |
|---|---:|---:|---|
| CamA 13–25s | 1 | 827 template px | detector |
| CamB 25–36s | 1 | 29 template px | displacement |

CamB's is the 25.60s report `HANDOVER.md` traced by hand through a table of
per-frame pairing distances. It now comes out of the run.

## The bands are provisional diagnostic boundaries

Neither band is a validated threshold, and **neither was derived from the two
clips it is reported on.** The near band is one Bullet Hole's width — a physical
scale that was already the scoring's slack — and the far band is twice it by
judgement. Nothing was fitted to make CamA come out `detector` and CamB
`displacement`: the measured distances are 827 and 29 template px against bands
at 80 and 40, so only CamB's sits anywhere near an edge, and that is the case
`HANDOVER.md` had already traced by hand through per-frame pairing distances.

Both carry `PROVISIONAL` in the source, the marker this codebase uses for a value
that has not been validated against footage. They are there to say **where to
look** when precision drops, not to certify a cause. An attribution is a lead,
and `unknown` is what the evidence supports when there is no lead.

## Why the bands are the scoring's own slack

A false positive within the **match tolerance** of a mark that was on the Board at
the baseline frame is *on* that mark — by exactly the standard that already
credits a detection with a ground-truth label. Past **twice** that, nothing
pre-existing is near enough for registration to have put a detection there, so
what remains is the detector.

Between the two is `unknown`, and `unknown` is an outcome rather than a rounding
of the evidence. The one measurement that could bound displacement — the
registration residual — is **censored at the match radius**: a mark displaced
further is not matched to the baseline at all, so it never enters the residual.
The maximum sits exactly on the radius on both labelled clips (20.0 of 20.0
template px on each), which is the ceiling, not a coincidence. Nothing in this
project bounds how far registration can displace a mark, so nothing here can
divide the two causes cleanly, and the band that says so is more honest than a
constant fitted to one clip.

The factor of two is a judgement about how wide to leave that band and is
deliberately generous, because the two errors are not symmetric: calling a
detector error registration hides a model problem, calling registration a
detector error is the misdirection this ADR exists to stop, and `unknown` costs
neither.

## Why the residual never refuses a run

It is tempting to gate: residual above some bar, run unscoreable. No such bar has
been validated. Nothing ties a residual to Bullet Hole scale or to SOW 2.3.2's
5 mm, and the only two clips that could calibrate one are both censored at their
own radius. Deriving a threshold from a single clip is the error this project
keeps finding in its own constants — the 0.70 persistence bar and the 40 px match
radius both came that way, and both were wrong.

A run refused on an uncalibrated bar destroys a measurement that was there to be
had. A run scored with its residual printed loses nothing. So the residual is a
disclosure, as `first detected` / `last detected` is under
[ADR-0004](0004-a-confirmed-bullet-hole-is-never-retracted.md): the pipeline
says what it could not do and leaves the judgement to the operator.

## What this cannot tell you

The marks it measures against are **the detector's own baseline detections**.
Nothing else says what was on the Board at the first frame — ground truth is a
photograph of the Board, and it carries no frame. So the attribution inherits the
baseline's errors both ways: a pre-existing mark the baseline missed leaves its
displaced sighting looking like a detector error, and a baseline phantom lends a
genuine detector error the look of displacement. `[INFO] baseline: N pre-existing
Bullet Holes over M frame(s)` prints on every run, and `BASELINE_FRAMES` exists
because a one-frame baseline inherits that frame's every miss.

The registration residual is **not** an input, although the same suppression step
computes it. It cannot be: it is censored at the match radius, so it says nothing
about the marks that escaped suppression — which are precisely the ones being
attributed. It is printed beside the score and used by a reader, not by the rule.

## Consequences

- Headline counts are unchanged by attribution, so every score recorded before
  this remains comparable with every score after it.
- A model comparison can be read per cause, so a registration-heavy day cannot
  be mistaken for a worse detector.
- `unknown` will appear, and it is not a defect to be tuned away. Narrowing it
  needs footage that bounds displacement, which is what the held-out recordings
  are for — not another sweep of the two clips that produced the band.
- `new_bullet_holes.process` returns its baseline marks and residual with its
  Bullet Holes, because nothing downstream can attribute anything without the
  marks that were already on the Board.
