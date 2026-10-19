# A single measured de-duplication gate

De-duplication — "is this candidate box the same Bullet Hole I already have?" —
is answered by one gate in `ImageRecognitionService/detection/tagging_bullets.py`
(`is_duplicate_bullet`). Two boxes are the same Bullet Hole if their centres lie
within **0.5x the mean box diagonal**, or they overlap by more than **50% of the
smaller box's area**. Nothing else in the pipeline merges Bullet Holes.

*Amended 2026-10-19: the delivered gate is `same_bullet_hole` in
`ImageRecognitionService/detection/new_bullet_holes.py`. `is_duplicate_bullet`
survives only in `tagging_bullets.py`, which is not delivered (#75). Both arms
above were ported unchanged (`DUP_CENTER_FACTOR`, `OVERLAP_THRESHOLD`), with a
floor in front of them: two centres within the match radius (`MATCH_TPL_PX`, in
Board px) are one Bullet Hole whatever their boxes say. The pipeline first
shipped with the floor alone, and on CamB_20260915_102250 it reported one torn
mark twice: the floor came to 2.96 Board px against a mark 13.4 px across. That
is why the box arms came back. Three other places ask whether two detections are
one mark, and each uses the floor alone, never a threshold of its own:
`baseline_marks` folds the baseline frames, `strip_pre_existing` drops what was
already on the Board, and `merge_band_detections` drops a band's second sighting
of a mark on the margin canvas's edge (#46). The box arms are kept out of the
first two on purpose. In the baseline they would fold two distinct pre-existing
marks into one, and in suppression they swallowed a real new Bullet Hole next to
a pre-existing one, taking CamB recall from 100% to 75%. `merge_displaced_tracks`
answers a different question, whether a later track is a displaced sighting of an
earlier one; it is provisional and off by default (`--merge-displaced`).*

## Why one gate

Five suppression tests previously ran in sequence, all answering the same
question with independently tuned values:

| Test | Value | Fate |
|---|---|---|
| Overlap, share of smaller box | 0.5 | **kept** — the surviving overlap arm, unchanged |
| Centre distance (`CLOSE_CENTER_FACTOR`) | 3.0x box diagonal | removed |
| Minimum separation (`MIN_SEPARATION`) | 4.5x box diagonal | removed |
| Cluster radius (`CLUSTER_FACTOR`/`MIN_CLUSTER_DIST`) | `max(0.75x diagonal, 10px)` | removed |
| IoU suppression (`IOU_SUPPRESS_THRESH`) | 0.2 | removed |

Two of the removed four carried comments recording that they had been tuned
against a single 960x544 clip.

The damage was invisible and additive. The widest gate, `MIN_SEPARATION`, merged
any two boxes whose centres fell within 4.5x their diagonal: across the sample
images it wrongly merged **63 of 422 detected pairs — 14.9% of pairs**, so tight
groups were silently collapsed. And with five tests in series no single value
could be tuned with a predictable effect, because another test was already
suppressing the pairs under examination.

The centre-distance gate replaced the four removed ones; the overlap arm it sat
beside is retained as-is, so "50% of the smaller box" is an old value that
survived review, not a new design.

## Why 0.5x

Measured across the sample images:

| Population | Centre distance, in box diagonals |
|---|---|
| Genuinely distinct Bullet Holes, closest pair | **0.93x** |
| Duplicate boxes of one Bullet Hole | **below 0.3x** |

The two populations do not overlap, and 0.5x sits in the empty gap between them.
At that value the gate merges zero distinct Bullet Holes in the sample set.

These numbers are the whole justification for the threshold. Anyone retuning it
should first reproduce them on their own captures — the values it replaced were
retuned blind precisely because no measurement was recorded alongside them.

## Consequences

The threshold is expressed in box diagonals, so it is scale-invariant: it holds
across captures at different camera distances and zooms without retuning. That is
why it stays a module constant rather than becoming a Capture Profile field —
unlike confidence and inference size, it does not depend on the physical setup.

Re-introducing a second suppression stage re-introduces the failure. Prefer
adjusting this gate, with measurements.

Confidence thresholding still drops low-scoring boxes upstream, and the two
interact: lowering confidence to recover Bullet Holes feeds more near-coincident
boxes into this gate. That is the interaction the four removed gates made
untunable.

Overlapping Hits that leave one visible mark are still reported as one — a
separate, deliberate ceiling ([ADR-0001](0001-report-bullet-holes-not-hits.md)),
not something de-duplication can fix.
