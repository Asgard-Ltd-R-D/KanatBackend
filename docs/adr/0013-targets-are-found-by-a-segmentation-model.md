---
status: proposed
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
