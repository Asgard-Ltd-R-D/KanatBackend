# Dataset Audit — Kanat 5.0 v11 (COCO export)

**Dataset:** `~/Downloads/Kanat 5.0.v11i.coco`
**Source:** Roboflow export (`universe.roboflow.com/kanat-5/kanat-5.0`), version 11, exported 2026-09-08
**Audit date:** 2026-09-08 · **Read-only** — no files were modified, nothing was retrained.

**Verdict: do not train on this split as-is.** The annotations themselves are clean, but the
train/valid/test split is not a valid split — validation and test frames are near-identical
copies of training frames from the same static-camera clips. Any mAP measured on this split is
close to meaningless.

---

## 1. Structure

```
Kanat 5.0.v11i.coco/
├── README.dataset.txt / README.roboflow.txt
├── train/  3830 .jpg + _annotations.coco.json
├── valid/    42 .jpg + _annotations.coco.json
└── test/     42 .jpg + _annotations.coco.json
```

- **Format:** COCO JSON, one `_annotations.coco.json` per split folder. No `data.yaml`, no manifest —
  splits are defined purely by folder membership.
- **Classes** (`categories`): `0 objects` (Roboflow supercategory placeholder, **0 annotations**),
  `1 board`, `2 bullet_hole`, `3 target`.
- **Roboflow preprocessing (from README):** auto-orient + EXIF strip, resize to 1280×1280 "fit (black edges)".
- **Roboflow augmentation:** 10 versions per source image, random crop 10–60%. Applied to **train only**.

---

## 2. Split sizes and balance

| Split | Images | % of images | Annotations | Boxes/img | board | bullet_hole | target |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 3830 | 97.85% | 58 469 | 15.27 | 4478 (7.7%) | 47 677 (81.5%) | 6314 (10.8%) |
| valid | 42 | 1.07% | 676 | 16.10 | 48 (7.1%) | 559 (82.7%) | 69 (10.2%) |
| test | 42 | 1.07% | 607 | 14.45 | 43 (7.1%) | 476 (78.4%) | 88 (14.5%) |

**The 97.85 / 1.07 / 1.07 ratio is an artifact of augmentation, not the real split.** Train contains
**381 unique source frames**, each duplicated 10× by the crop augmentation (379 frames ×10, 2 frames ×20).
Valid and test are un-augmented, 1 copy per frame.

**Real split, counted in unique source frames: 381 / 42 / 42 = 81.9% / 9.0% / 9.0%.**
That ratio is fine. The *absolute* sizes are the problem: 42 images is far too small to be
statistically meaningful. At 42 images / ~560 bullet_holes, a single missed or spurious detection
moves recall by ~0.2 pp and the 95% CI on image-level metrics is roughly ±15 pp. You cannot
distinguish a 0.82 mAP model from a 0.87 mAP model on this valid set.

**Class balance:** the 3 real classes are present in all three splits, and the class *proportions*
are consistent across splits (bullet_hole ~78–83%, board ~7%, target ~10–15%). No class is
missing or rare-in-valid-but-common-in-train. The 8:1 bullet_hole:board ratio is inherent to the
task (many holes, one board per frame), not a defect.

**Dead class:** category id `0 objects` carries zero annotations. It is a Roboflow export artifact.
If this is converted to YOLO with a naive script you get `nc: 4` with an unused index 0 and every
real class shifted by one — a silent source of "the model predicts class 0 for everything" bugs.

---

## 3. Duplicates and leakage — **the critical finding**

### Exact duplicates
- **0** byte-identical (MD5) images anywhere, within or across splits.
- **0** source frames appearing by filename in more than one split.

So Roboflow's own dedup did its job at the file level. That is not sufficient here.

### Near-duplicates and cross-split leakage
Perceptual hashing (8×8 DCT pHash + 8×8 dHash, requiring **both** Hamming ≤ 6):

| Pair | Near-duplicate pairs |
|---|---:|
| train ↔ valid | 1099 |
| train ↔ test | 1169 |
| valid ↔ test | 143 |
| within valid | \ 225 combined |
| within test | / |

- **40 of 42 valid images (95%)** have at least one near-duplicate in train.
- **38 of 42 test images (90%)** have at least one near-duplicate in train.

### Why: temporal adjacency in static-camera clips
All 3914 images come from **15 video clips** sampled frame-by-frame, and the camera is static.
Consecutive frames are near-identical. The split was made by shuffling *frames*, not *clips*, so
valid/test frames sit between train frames on the same timeline.

Distance from each valid/test frame to the nearest train frame of the same clip:

| Frame-index distance | 1 | 2 | 3 | 4 | 5 | 6 | >10 | no train frames |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| valid (n=42) | 17 | 10 | 5 | 3 | 2 | 1 | 3 | 1 |
| test (n=42) | 25 | 7 | 0 | 0 | 3 | 1 | 4 | 2 |

**27/42 valid and 32/42 test images have a training frame within ±2 frames** of the same
fixed-camera clip. (Frame indices are those of the extracted frames; the source video frame rate is
not recorded anywhere in the export, so the wall-clock gap between them is unknown. The pixel
measurements below, not an assumed frame rate, are what establish how similar these frames are.)

Full-resolution pixel verification of the closest pairs (grayscale mean absolute difference on a
0–255 scale, and share of pixels differing by more than 16 levels):

| Pair | MAD | pixels differing >16 |
|---|---:|---:|
| `test/CAPTURE_mp4-0071…` vs `train/CAPTURE_mp4-0067…` | **1.98** | 1.4% |
| `valid/CAPTURE_mp4-0266…` vs `train/CAPTURE_mp4-0267…` | **1.66** | 1.3% |
| `test/CAPTURE_mp4-0290…` vs `train/CAPTURE_mp4-0267…` | 6.09 | 10.4% |

**Caveat on these figures:** the 1280×1280 letterbox means part of every frame is black bar, which
is trivially identical in both images and flatters the statistic. For the `0266`/`0267` pair, 22.8%
of the frame is near-black in both. Excluding it and measuring content pixels only, MAD rises from
1.66 to **2.15** and the share unchanged within 16 levels falls from 98.7% to **98.3%** — the
caveat is real but does not change the conclusion.

The full difference distribution for that pair is more telling than any single threshold: **50.7% of
pixels hold the identical integer value** in both images, 83% differ by ≤2 levels, and only 0.49%
differ by more than 32. Those large-change pixels are scattered across the whole frame (bounding box
x 146–1133, y 195–1185), which is the signature of sensor and compression noise rather than anything
in the scene moving — a newly appeared bullet hole would be ~113 px² in one tight cluster.

In other words the ~15 bullet holes the detector is meant to find sit at identical pixel positions in
the training image and the validation image; only noise separates them. The model can score near
perfectly on the "held-out" frame having learned where the holes were, not what a hole looks like.

### Clip-level distribution (the root cause)

| Clip | train | valid | test |
|---|---:|---:|---:|
| vsdc-sr-2025-02-19-18-11-28 | 810 | 0 | 0 |
| good_shooting_vid1 | 550 | 3 | 4 |
| vsdc-sr-2025-02-19-18-27-35 | 480 | 7 | 4 |
| CAPTURE | 460 | 9 | 20 |
| KANA-5-SYNC | 260 | 4 | 3 |
| very_good_shooting_vid | 250 | 5 | 3 |
| KANA-5-OUTER | 250 | 5 | 0 |
| vsdc-sr-2025-02-19-18-17-58 | 220 | 0 | 0 |
| vsdc-sr-2025-02-19-17-46-30 | 160 | 0 | 0 |
| sync-out-of-target | 120 | 5 | 1 |
| NewVid-mp4 | 120 | 0 | 0 |
| outer | 70 | 2 | 2 |
| vsdc-sr-2025-02-19-17-55-17 | 40 | 1 | 2 |
| shooting_vid2 | 40 | 0 | 1 |
| CAPTURE-SYNC-round-1 | 0 | 1 | 2 |

Only 1 of 15 clips (`CAPTURE-SYNC-round-1`, 3 images) is genuinely held out. Every other
valid/test image shares its clip — and therefore its scene, board, camera pose and lighting —
with hundreds of training images.

---

## 4. Annotation quality — clean

Every check passed on all three splits:

| Check | train | valid | test |
|---|---|---|---|
| Images in JSON with no file on disk | 0 | 0 | 0 |
| Files on disk not in JSON | 0 | 0 | 0 |
| Images with 0 boxes | 0 | 0 | 0 |
| Degenerate boxes (w ≤ 0 or h ≤ 0) | 0 | 0 | 0 |
| Boxes < 4 px² | 0 | 0 | 0 |
| Boxes outside image bounds | 0 | 0 | 0 |
| `area` ≤ 0 | 0 | 0 | 0 |
| Annotations with unknown `category_id` | 0 | 0 | 0 |
| Corrupt / unreadable images | 0 | 0 | 0 |

Coordinates are absolute COCO pixels `[x, y, w, h]`, consistent with the declared 1280×1280 —
nothing looks normalized-by-mistake.

**Minor issues found:**

- **192 identical-bbox pairs and 61 overlapping pairs (IoU > 0.7) in train**, i.e. ~253 annotations
  (0.43% of train) that are double-labelled or heavily overlapping. Zero such pairs in valid/test.
  Since train is 10 copies of 381 frames, this traces back to roughly **25 source frames** with a
  double-labelled box. Worth a spot-check but not blocking.
- **Box counts per image: 1–38.** The 38-box maxima (`NewVid-mp4-0027/0029`) are plausible for a
  well-shot target, not obvious errors. The minimum, `shooting_vid2_mp4-0026` with a single box,
  is worth a look.
- **422 train images (11%), 5 valid, 7 test have zero `bullet_hole` boxes** — board/target only.
  These read as legitimate pre-fire frames, i.e. useful negatives, not missing annotations.
- **90 train / 4 valid / 6 test images have no `board` box** while having `target` boxes. Given
  `board` is otherwise present on 97.6% of train images, this is a mild labelling inconsistency
  worth reviewing on the ~9 affected source frames.
- **1 train image has a `board` but no `target`.**

---

## 5. Image quality and consistency

- **Resolution: 1280×1280 for all 3914 images.** Perfectly uniform — Roboflow's letterbox resize.
  Note this means every image carries black bars; the true content aspect ratio is not square.
- **All images RGB JPEG, all readable, 0 corrupt.** Total 380 MB (train 371.5, valid 3.9, test 4.6).
- **EXIF stripped** on all images (Roboflow auto-orient), so EXIF gives no provenance signal.
- **Synthetic : real ratio = 0 : 3914.** Every filename maps to one of 15 `.mp4` capture clips
  (`CAPTURE`, `KANA-5-SYNC`, `vsdc-sr-2025-02-19-*`, `good_shooting_vid1`, …). There is **no
  BlenderProc or otherwise synthetic data in this export** — no procedural naming, no render-style
  filenames, no synthetic subset in any split. If synthetic data was expected here, it did not
  make it into v11.
- **Augmentation diversity is real:** mean pHash distance between the 10 crop-augmented copies of
  the same source frame is 25.2 / 64 bits, so the crops do vary substantially. The leakage is not
  caused by weak augmentation — it is caused by the frame-level split.

---

## 6. Data sufficiency

Rule of thumb used: **a class needs ≳ 1500 instances across ≳ 100 genuinely distinct scenes** for a
reliable detector; **< 200 instances is too sparse to train at all.** Augmented copies do not count
as independent instances — 10 crops of one frame carry roughly the information of one frame.

Effective (de-augmented) training instances:

| Class | Raw train instances | Effective (÷10) | Verdict |
|---|---:|---:|---|
| bullet_hole | 47 677 | ~4 768 | Adequate in count; scene diversity is the limit |
| target | 6 314 | ~631 | Thin |
| board | 4 478 | ~448 | Thin |

- **`board` is the sparsest class at ~448 effective instances**, followed by `target` at ~631.
  Both are above the 200 floor but well below comfortable. They are also the easy classes
  (large, high-contrast, one or two per frame), so this is likely tolerable in practice.
- **The real ceiling is scene diversity, not instance count: 381 unique frames from 14 clips.**
  For bullet_hole, ~4768 effective instances sounds healthy, but they are drawn from 14 boards
  under 14 lighting conditions. Expect the model to generalize poorly to a new range, a new board
  print, or new lighting.
- **No class is well-represented in train but absent in valid/test** — proportions match across all
  three splits (§2). That is the one balance property this dataset gets right.
- **Object scale is a training-config risk:** median `bullet_hole` box is 0.0098 of the image
  diagonal ≈ **12.5 px at 1280×1280**; the 1st percentile is ≈ 4.5 px. If you train at
  `imgsz=640`, the median hole becomes ~6 px and the small ones ~2 px — below what standard YOLO
  stride-8 heads resolve. Train at 1280, or tile.

---

## 7. Prioritized findings

### Blocking — fix before the next training run

1. **Train/valid/test leakage via temporal frame adjacency.** 40/42 valid and 38/42 test images
   have a near-duplicate in train; 27/42 and 32/42 respectively sit within ±2 frames of a train
   frame in the same static-camera clip, with full-res MAD as low as 1.66/255. Validation mAP from
   this split measures memorization, not detection. **Every metric reported off this split so far
   should be treated as unreliable and re-measured after a re-split.**

   *Cause and fix:* the split was made over individual **frames**, which are not independent samples
   — consecutive frames of a fixed-camera clip are near-copies of each other, so shuffling them
   scatters near-identical images across the split boundary. The fix is to split over whole
   **clips**, so that every frame of a given recording lands entirely in one split. Note this is
   *not* an augmentation-ordering problem: the export already augments train only, and no source
   frame appears in more than one split (see §8, step 1).
2. **Valid and test are too small to measure anything.** 42 images / ~600 boxes each. Even without
   leakage, the confidence interval is far wider than the differences you would be trying to detect
   between checkpoints.

### Real risks — address soon

3. **Only 381 unique source frames from 15 clips.** The 3830-image train set is 10× augmentation
   of a small dataset. Reported "3914 images" overstates the information content by roughly 10×.
4. **Object scale vs. training resolution.** Median bullet_hole ≈ 12.5 px at 1280. Training at 640
   will silently destroy the smallest ~25% of the target class.
5. **Category `0 objects` is an empty placeholder.** Will produce an off-by-one class map in any
   naive COCO→YOLO conversion.

### Nice to have

6. 253 duplicate/overlapping annotation pairs in train (~25 source frames) — spot-check and clean.
7. 9 source frames with `target` boxes but no `board` box — labelling inconsistency.
8. No synthetic data present, despite the pipeline supporting it (§5).

---

## 8. Recommended next steps

1. **Re-split by clip, not by frame — this is the single highest-value change.**
   Hold out entire source clips. A defensible allocation from the 15 available clips:
   - *test*: `CAPTURE-SYNC-round-1` (already effectively held out) + `outer` + `shooting_vid2`
   - *valid*: `vsdc-sr-2025-02-19-17-55-17` + `sync-out-of-target` + `KANA-5-OUTER`
   - *train*: the remaining 9 clips.

   This gives a genuinely unseen validation scene. Do the split on **source frames before
   augmentation**, then augment train only. Note that the current export already gets this part
   right — train holds 381 source frames × 10 crops, valid/test hold 42 un-augmented frames each,
   and **no source frame appears in more than one split**. The leakage is therefore *not* caused by
   augmenting before splitting; it is caused by splitting **frames** instead of **clips**, so
   adjacent frames of the same static-camera video land on opposite sides of the boundary.
   Splitting by clip is the fix. Verify afterwards with a cross-split pHash check: target **zero**
   cross-split pairs at Hamming ≤ 6.

2. **Accept that clip-level splitting alone is not enough — collect more clips.** With 15 clips,
   holding out 3 leaves 12 for training and a validation set of one board under one lighting
   condition. Target **≳ 30 distinct capture sessions** (different boards, ranges, lighting, camera
   distances), then hold out 5–6 entire sessions. Concretely: **~15 more capture sessions**, which
   at the current ~25 usable frames per session is roughly 400 more source frames.

3. **Do not deduplicate valid/test by deleting images.** The right fix is the re-split, not
   removing the 40 leaking valid images — deleting them would leave a 2-image validation set.

4. **Train at `imgsz=1280`** (or tile 1280 into 640 crops with overlap) to keep 12 px bullet holes
   detectable. If you must run 640 for latency, measure the small-object recall penalty explicitly
   before committing.

5. **Pin the class map explicitly** when converting to YOLO: drop category 0 and map
   `board→0, bullet_hole→1, target→2`, with `nc: 3`. Do not rely on COCO id order.

6. **Add real negatives.** 422 train images already have no bullet_hole; that is a good start.
   Add frames with no board and no target at all (empty range, wall, floor, people walking past)
   so the detector learns to stay silent — important for a real-time shot-tracking pipeline where
   false positives register phantom shots.

7. **Spot-check the 253 overlapping annotation pairs** and the 9 frames missing a `board` box.
   Low priority relative to items 1–2.

8. **If BlenderProc synthetic data exists, it is not in this export.** Decide whether it should be
   — synthetic boards with known hole positions would directly address the scene-diversity ceiling
   in item 2, at far lower cost than 15 more range sessions. Keep any synthetic subset identifiable
   by filename prefix so this ratio stays auditable, and keep it out of valid/test.

---

### Reproducing this audit

All findings come from read-only passes over the COCO JSONs and image bytes: MD5 over file bytes;
8×8 dHash and 8×8 DCT pHash (32×32 input) with a Hamming ≤ 6 threshold on both hashes
simultaneously; frame indices parsed from the Roboflow filename pattern
`<clip>_mp4-<NNNN>_jpg.rf.<hash>.jpg`; full-resolution grayscale MAD for pair verification.
