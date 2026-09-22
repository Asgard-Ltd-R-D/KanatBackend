# A confirmed Bullet Hole is never retracted

Once [ADR-0003](0003-a-bullet-hole-is-new-when-it-persists.md) confirms a Bullet
Hole, nothing later un-confirms it. The pipeline never re-examines a confirmed
Bullet Hole, never revises a count downwards, and never reports that a Bullet
Hole stopped existing. When detections of it cease, the run says so — `first
detected` and `last detected`, with the number of frames it was seen in — and
leaves the judgement to the operator.

ADR-0003 says when a Bullet Hole *becomes* confirmed and is silent on whether it
can stop being. This is the other half.

## Why a detection ceasing is not evidence

A Hit is permanent. A Bullet Hole is the visible mark it leaves, and it can
genuinely cease — paper torn away, a sheet replaced, the Board curling a mark out
of view. A detection is neither: it is what the model returned this frame.
Detections stop for reasons that have nothing to do with the mark, and the
footage shows it plainly.

Measured on `CamB_20260915_102250.mkv`, on the mark first detected at 0.04s:

| | |
|---|---|
| detected at 0.82-0.86 | 0.04s to ~3.8s, about 95 frames |
| nearest detection at a **0.02** floor thereafter | 4.0s: 116 px · 10.0s: 104 px · 25.0s: 98 px |
| visible to the operator | until 25.0s |
| reappears | never, over ~525 frames |

The detector lost a real mark for twenty-one seconds while it sat in plain view.
Any rule that retracts on absence retracts this one.

## Considered options

**Re-examine and retract.** The obvious design, and the one the failure was
originally written up as needing. It would have removed a false positive: the
0.04s mark was reported as *new* when it was pre-existing. But it removes it for
the wrong reason, by a rule that cannot tell "this was never a Bullet Hole" from
"the detector stopped seeing a Bullet Hole" — and on the only instance available,
those are the same signal at the same threshold.

That false positive had a different cause and now has a different fix: the
baseline is built from several frames, so the mark is classified pre-existing and
never reported. **After that fix there is no surviving case of a genuinely new
Bullet Hole that vanished.** Retraction would carry a demonstrated cost against
no demonstrated benefit.

**Disclose and leave the count alone.** Chosen. The data was already in hand —
the tracker records which frames each Bullet Hole was seen in — so it costs a
line of reporting and no new state. On the full CamB clip it separates the
displaced sighting at 38.56s (seen in 21% of frames after it, last seen 41.72s of
a 46s clip) from its twin at 31.16s (85%), which is the signature of a
registration displacement, visible without opening the video.

## Consequences

Anything consuming these results — the operator's report, and the .NET service
when it takes them — can treat a confirmed Bullet Hole as final, and needs no
path for a retraction it has no way to verify.

The cost is that a confirmed false positive stays in the count. Precision is
therefore defended entirely *before* confirmation — baseline suppression,
persistence, change-evidence corroboration, and whatever eventually fixes
registration, which is an open defect reaching the suppression threshold on both
labelled clips. It is not defended by deleting Bullet Holes afterwards on
evidence that cannot tell a false positive from a mark the detector lost.

Revisit if footage ever shows a genuinely new Bullet Hole that vanishes;
`HANDOVER.md` records that the full clip is re-run after any change here to check
whether one has appeared.
