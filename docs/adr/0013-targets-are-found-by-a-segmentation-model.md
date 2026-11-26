---
status: accepted
---

# Targets are found by a segmentation model

Every Target in a frame is found by a YOLO26n-seg instance segmentation model
(`trained_models/target_seg_406/best.pt`, #406), not by the green hue band
that `board.find_targets` used. The hue band, and the hue checks built on it
to keep scenery out (`at_hue`, `TARGET_HUE_TOLERANCE`, `BoardView.hue`), are
deleted. The colour gate survives only where the colour is known: the
synthetic template image, and the phone photographs `tools/evaluate.py`
registers truth from, so that the bench's own measure did not move during
the change. Decided 2026-11-25, spec #400.

## Why

At the 2026-11-24 customer visit, in direct sun and zoomed in, the gate lost
the Target: sun, white balance, H.264 and blur all move the print's colour,
and a Target the gate drops is never seen by anything after it. A model
trained to find the print by its shape does not depend on that colour.

## Considered options

- **Adaptive hue gate** (#401): it widened the band, which let in blue bags
  the size of the print and made re-anchor seeds run to the ECC cap (10 s).
- **Disk-first search** (`docs/disk_first_target_search.md`): hand-tuned for
  the same single failure.
- **Keeping the gate as a fallback beside the model**: two finders to tune
  and to disagree; rejected to keep one path.

## What does not change

Registration (`register`, `interior_fit`, `track_view`, re-anchor), the
reference Target showing its white disk, the outlines taken through each
Target's fit (#396), Target numbering, the sheets, and every measurement in
Board space. The model only supplies the masks those start from. Its
confidence and area floors are provisional, set from a sweep on held-out
footage.

## Known limitation

Measured 2026-11-25 on the held-out footage (#413), every frame also run
greyscale, hue-rotated, warm and cool cast, and at 0.3 saturation: the model
finds every Target with no false one in greyscale, a 30° hue rotation, both
casts and low saturation, on every set. Large hue rotations break it: at
60° and 90° indoor it adds false Targets (2 and 4 on 30 Targets), and at 180°,
the green print turned magenta, it finds 10/30 indoor and 47/60 outdoor. No
sun, white balance or H.264 moves the print that far, so this is accepted as
outside the operating conditions, without retraining. If a print in another
colour is ever used, retrain with hue augmentation first.

The reference Target, and so the Board scale (`board_scale_for`, the
reference at `TARGET_NET_SCALE`), can differ from the hue gate's: the model's
masks rank the Targets' sizes differently. On CamB `_101450` it takes the
lower-left Target where the gate took the upper-left, and the scale falls
from 0.139 to 0.130. The baseline then holds 0 Baseline Marks where `main`
held 6, real holes on the lower-left sheet that sit at the detector's
sensitivity edge (forced back to 0.139, they are found again); on `_101550`,
4 against 9. Accepted (#413): the regression bench passes with no false
positive added, and a pre-existing hole the baseline misses is reported as
new only if the detector later catches it. If that shows up, take the scale
from the largest Target instead of the reference.
