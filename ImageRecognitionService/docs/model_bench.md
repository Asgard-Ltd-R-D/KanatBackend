# Model bench: yolo26n, s and m, and yolo26n with background negatives

**Measured 2026-09-30 at `542abd3`**, issue #30, and the negatives run on
2026-10-01 (its own section). `opencv-python==4.10.0.84`, `ultralytics==8.4.126`,
inference on CPU (the runtime's default device), every constant at its current
value. No sealed recording was opened and no
`--final-run` was passed; `data/sealed_runs.log` still does not exist.

**Nothing is promoted.** `DEFAULT_MODEL` is still `kanat_yolo26n_v1`. The four
recordings below are the fitted clips and the threshold-work pair. The standing
order is not to move anything on them, and a model is not an exception. The
comparison that could choose a model is the sealed set, and it has not been run.

## The checkpoints

Read from each checkpoint's own `train_args`. **Every run is a fresh training run
from the COCO-pretrained weights of its size. None continues from the shipped
checkpoint.** All train at image size 960 on `pibh`, one class, `bullet_hole`.

**`pibh` is not a downloaded split.** The training notebook builds it in
`/kaggle/working/pibh` from Kaggle's `qiyan527/target-paper-images-with-bullet-holes`
(6557 train / 1605 val / 96 test images; a local copy exists, unhashed). It drops
the 96 test images, whose one box is the whole target paper, and the 3 train
images that have no label file. Then it re-splits the remaining 8159 frames by
scene into **5941 train / 1475 val / 743 test**. A scene is a 16-bit dHash bucket,
86 of them. s's notebook was saved with its output, which prints those counts
and `5941 images, 0 backgrounds`. n's and m's notebooks are not on hand.

Each run's learning rate at the end of its first warmup epoch fixes its batches
per epoch, and so its train size. n and s fit 743 batches of 8 and m fits
1485–1486 of 4: 5937–5944 images each, never the Kaggle copy's 6557. The negatives
run fits 745 batches, 5953–5960 images, which is 5941 + 3 + 15 = 5959 (below). The
split is deterministic. So if n and m ran the same code over the same Kaggle
files, every run trained and validated on the same frames. The notebooks are not
committed.

| Checkpoint | Local path (`trained_models/`, not committed) | sha256 | Started from | imgsz | Epochs (best) | Batch | Where, ultralytics |
|---|---|---|---|---:|---:|---:|---|
| n, shipped | `kanat_yolo26n_v1/weights/best.pt` | `f7e407c6…` | `yolo26n.pt`, fresh | 960 | 100 (100) | 8 | Kaggle, 8.4.130 |
| s | `kanat_yolo26s_v1/weights/best.pt` | `511ca5c4…` | `yolo26s.pt`, fresh | 960 | 100 (99) | 8 | Kaggle, 8.4.158 |
| m (the run #30 found in flight) | `kanat_yolo26m_v1/weights/best.pt` | `1a6a5a86…` | `yolo26m.pt`, fresh | 960 | **200** (198) | **4** | `asgard` Linux GPU box, 8.4.165 |
| n + negatives | `kanat_yolo26n_neg_v1/weights/best.pt` | `6729d93d…` | `yolo26n.pt`, fresh | 960 | 100 (100) | 8 | Kaggle, 8.4.167 |

Seed 0, patience 20, `close_mosaic` 10, default augmentation and `optimizer=auto`
on all of them. "`asgard`" is the machine m's `train_args` name, under
`/home/asgard/`.

**m is not only a capacity step.** It trained twice as many epochs at half the
batch, so m against n confounds capacity with schedule. **s is the like-for-like
capacity step**: same recipe, same platform, only the size changes.

Validation mAP50-95 (n 0.870 / s 0.885 / m 0.904 / n + negatives 0.855) is on
that 1475-frame scene split. The re-split exists to stop the frame leakage
`dataset_audit.md` found in the Roboflow export it audited, but nobody has checked
that 16-bit scene buckets stop it on `pibh`. Those are also `pibh`'s frames, not
this footage. The figures are listed for identity, not for comparison.

## Footage and ground truth

The same for every checkpoint: the four recordings carrying photograph-derived
truth that the manifest does not seal. That is 16 new Bullet Holes over 2
Capture Setups, each recording run over its manifest window.

| Recording | Capture Setup | Window | New Bullet Holes |
|---|---|---|---:|
| `CamA_20260914_141546` | `cama-20260914` | 13–25s | 6 |
| `CamB_20260915_102250` | `camb-20260915-close-one-board` | 0–46s | 4 |
| `CamB_20260915_102450` | same | 0–47.76s | 4 |
| `CamB_20260915_103223` | same | 0–51.88s | 2 |

```bash
.venv/bin/python -m tools.probe data/videos/CamA_20260914_141546.mkv --start 13 --end 25 \
    --truth-labels data/truth/cama-20260914-141546 \
    --model trained_models/kanat_yolo26{n,s,m}_v1/weights/best.pt
.venv/bin/python -m tools.evaluate data/videos/CamA_20260914_141546.mkv --start 13 --end 25 \
    --truth-labels data/truth/cama-20260914-141546 --model trained_models/kanat_yolo26s_v1/weights/best.pt
# ... and the same for the three CamB recordings over their windows
```

## Detector probe, per Bullet Hole

`probe.py`: conf 0.02, radius 40 template px. No frame was lost to registration
on any run, so every checkpoint's rate has the same denominator on a given
recording and the rates compare directly. **Since arrival** is the share of
frames holding a Detection, counted from the earliest first Detection any of
the three checkpoints made and taken from the printed rate (±1 point of
rounding). The one exception is `_102450` truth #2, below.

**CamA 13–25s** (300 frames, net scale 0.90):

| Bullet Hole | arrives | n | s | m | Note |
|---|---:|---:|---:|---:|---|
| truth #1 | 15.88s | 100% | 59% | 96% | s first sees it at 16.20s and never after 22.84s |
| truth #2 | 14.64s | 53% | 47% | **30%** | m never sees it after 18.12s (171 frames blind) |
| truth #3 | 16.48s | 96% | 100% | 80% | |
| truth #4 | 17.08s | 62% | 64% | **85%** | the mark the pipeline has lost since #50 |
| truth #5 | 14.00s | 85% | 99% | 98% | n first sees it at 14.64s, 16 frames after s and m |
| truth #6 | 15.24s | 100% | 100% | 64% | m never sees it after 23.80s |
| mean | | **83%** | 78% | 76% | |

**CamB: saturated.** At conf 0.02 all three checkpoints see all ten new Bullet
Holes in every frame, or all but a handful, from arrival to the end of the
clip. The only differences:

| Recording | Bullet Hole | arrives | n | s | m | Note |
|---|---|---:|---:|---:|---:|---|
| `_102250` | truth #1 | 31.16s | ~100% | ~100% | ~100% | |
| | truth #2 | 29.00s | 100% | 100% | 100% | |
| | truth #3 | 1.64s | ~100% | **89%** | ~100% | s's last Detection is 45.72s |
| | truth #4 | 30.60s | ~100% | ~100% | ~100% | |
| `_102450` | truth #1 | 32.92s | ~100% | ~100% | ~100% | |
| | truth #2 | 32.40s | —* | ~100% | ~100% | *n also fires near it on and off from 8.60s to 15.48s, before the Hit: the ring-numeral flicker `falsification_run.md` records. s and m do not. Arrival is taken from s and m, and n's rate mixes the flicker in, so its share after 32.40s cannot be read from it. The pipeline puts n at 384 of 384 frames from 32.40s at conf 0.40 |
| | truth #3 | 31.28s | ~100% | ~100% | ~100% | n first at 31.28s, s and m at 31.48s |
| | truth #4 | 31.60s | ~100% | ~100% | ~100% | |
| `_103223` | truth #1 | 11.20s | ~100% | ~100% | ~100% | |
| | truth #2 | 11.20s | ~100% | ~100% | ~100% | |

So on the CamB close pose, capacity buys no recall the probe can see: n is
already at the ceiling. The small `_102450` truth #3 and #4 are no exception,
now that #46 puts them on the canvas.

## Pipeline, per Bullet Hole

`evaluate.py` with each checkpoint dropped in, at every current constant. **Those
constants — `DEFAULT_CONFIDENCE` 0.40, `PERSIST`, the baseline — were fitted
with n**, so s and m are scored at n's operating point. The probe above is
the threshold-free comparison; this is what swapping the weights in would do
today.

| Recording | n TP/FP/FN | s | m |
|---|---|---|---|
| CamA 13–25s | 5/1/1 | 3/0/3 | 4/1/2 |
| `_102250` 0–46s | 4/1/0 | 3/0/1 | **4/0/0** |
| `_102450` 0–47.76s | 4/0/0 | 4/0/0 | 4/0/0 |
| `_103223` 0–51.88s | 2/1/0 | 2/1/0 | 2/1/0 |
| **pooled, 16** | **15/3/1**, F1 0.88 | 12/1/4, F1 0.83 | 14/2/2, F1 0.88 |

Each Bullet Hole, ✓ found and ✗ not found:

| Recording | truth | n | s | m |
|---|---|:-:|:-:|:-:|
| CamA | #1 | ✓ | ✗ | ✓ |
| | #2 | ✓ | ✗ | ✗ |
| | #3 | ✓ | ✓ | ✓ |
| | #4 | ✗ | ✗ | ✓ |
| | #5 | ✓ | ✓ | ✓ |
| | #6 | ✓ | ✓ | ✗ |
| `_102250` | #1–#2, #4 | ✓ | ✓ | ✓ |
| | #3 | ✓ | ✗ | ✓ |
| `_102450` | #1–#4 | ✓ | ✓ | ✓ |
| `_103223` | #1–#2 | ✓ | ✓ | ✓ |

**The false negatives are the detector, not the change filter.** Rerun with
`--no-change-filter`, CamA loses the same Bullet Holes for every checkpoint: s
never confirms #1, #2 or #4 at conf 0.40, and m never confirms #2 or #6. The
probe puts each of them at 64% of frames or less since arrival: s at 59, 47 and
64%, m at 30 and 64%. n's own false negative, #4, sits at 62%. s's `_102250`
truth #3 is not confirmed without the filter either, and it is the one false
negative the conf-0.02 probe does not explain: s sees it in 89% of frames there. Probed again at the
operating 0.40, s sees it in ~16% of the frames after 1.64s, against n's ~91%.
So s finds the mark but scores it below the threshold that was fitted to n.
That confidence failure is exactly what the probe's low floor keeps separate
from a detection failure.

**The false positives, one by one:**

- CamA: n's is the one HANDOVER records, `detector` at 830 px. m's is a
  different mark at 14.36s, `detector` at 217 px, seen in 13% of the frames
  after it. s has none.
- `_102250`: n's is found #4 at 30.60s on ring 8, `detector` at 520 px, which
  HANDOVER records. **Neither s nor m produces it.**
- `_103223`: n and m report the insect or debris that lands at 19.76–19.84s,
  `detector` at 259–261 px. It is a real object, which persistence and change
  evidence pass by construction (`falsification_run.md`). s's false positive
  arrives at 19.88s but is `detector` at **639** px. Its baseline holds all ten
  photographed marks, like the others', so it sits somewhere else on the Board.
  Whether it is the same object is not established.

**What the change filter is covering for.** False positives the pipeline
confirms *before* change evidence: read directly from `--no-change-filter` runs
(CamA, and s on `_102250`), and elsewhere from the `[FILTER]` counts less the
true positives.

| Recording | n | s | m |
|---|---:|---:|---:|
| CamA | 5 | 10 | 1 |
| `_102250` | 2 | 2 | 0 |
| `_102450` | 0 | 0 | 0 |
| `_103223` | 1 | 1 | 1 |
| **pooled** | **8** | **13** | **2** |

On CamA they sit almost all on Target 1's printed rings (`[model only]`, no
change against the baseline). Attributed there (ADR-0006), n's 5 are all
`detector`, s's 10 are 7 `detector`, 1 `displacement` and 2 `unknown`, and
m's 1 is `detector`. The filter removes all but the six false
positives in the pipeline table, so the headline counts barely move. m leans on the filter least by a wide margin. Its two are the CamA
14.36s mark and the `_103223` insect, both real changes that the filter passes
anyway.

## What this says, and what it does not

- **Capacity does not buy recall on this footage.** On CamB the detector is
  saturated for all three. On CamA, s and m each hold some marks better than n
  (m: #4 and #5; s: #5) and lose others (m: #2 after 18s and #6; s: #1). The
  mean detection rate falls from n to s to m.
- **m may buy precision on the printed Target.** Before the change filter, m
  confirms 2 false positives over the four recordings, against n's 8 and s's
  13. Neither of m's is on the printed Target. At detector level, s and m also
  skip the `_102450` numeral flicker that n shows. That is the failure mode
  HANDOVER places on "the printed rings and numerals". ADR-0003's argument
  that capacity cannot fix the *gravel* is not tested here: none of these
  false positives is gravel.
- **s is not a step between n and m.** It confirms the most ring false
  positives and loses the most recall. Size alone does not order these
  checkpoints, so m's precision may owe as much to its 200 epochs as to its
  size.
- **CamA differences are the size of CamA's grid noise.** Before #50, #46's
  canvas-shift control took n's CamA F1 from 0.92 to 0.67–0.83 by translating
  the canvas 8–32 px and nothing else. A mark or two gained or lost there is
  not, on its own, a property of the model.
- **These are the fitted clips.** CamA and `_102250` are what every constant
  was set on, with n. Two Capture Setups and 16 Bullet Holes. The held-out
  comparison `HANDOVER.md` blocks model selection on (open question 5) is
  still the sealed set's to answer.

## yolo26n with background negatives

**Measured 2026-10-01 at `3baf632`.** Same code (only docs have changed since
`542abd3`), same libraries, device and constants, same commands with
`--model trained_models/kanat_yolo26n_neg_v1/weights/best.pt`. As a drift check,
the shipped n still scores 5/1/1 on CamA there, with the same 830 px false
positive. **Not promoted.**

This is the training-data experiment, kept apart from capacity: the shipped n
recipe with background images added.

### The run

- **Fresh from `yolo26n.pt`, imgsz 960, 100 epochs, batch 8, seed 0, patience
  20**, on Kaggle with ultralytics 8.4.167. This re-runs the recipe with data
  added; it does not fine-tune the shipped checkpoint. The best epoch is the
  last.
- **Data: the notebook that builds `pibh` (above), with two steps added after
  the split**, both into train only. One restores the 3 unlabelled Kaggle train
  images (`175`, `257`, `271`, clean unshot targets) with empty label files. The
  other adds the 15 #28 negatives, uploaded into the Kaggle dataset as
  `negatives/`. The run saved no output, so its train scan is not on record;
  its 745 batches fit the 5959 images this makes. Nothing checks the uploaded 15
  against `data/negatives` by hash. All 15 local label files are empty.
- **So it adds 18 backgrounds, not 15.** n, s and m trained on none: the
  notebook drops images without a label file, and s's scan reads `0
  backgrounds`. 18 in 5959 is 0.30%. A null result would say that these 18 at
  that weight changed nothing. It would not say that background negatives
  cannot work.
- **Not the only change.** The platform is the same as the shipped n's, but
  ultralytics went from 8.4.130 to 8.4.167, and the GPU may differ: n's 100
  epochs took 6.6 h, these took 5.0 h. No run measures how far a second run of
  one recipe moves these scores. The same notebook without the two steps, on
  8.4.167, is the control for both.
- **Where they come from.** All 15 are `cama-20260914`, 5 of them from
  `CamA_20260914_141546` itself (`data/negatives/sources.csv`). So CamA's gravel
  is in-sample for this checkpoint. The CamB close trio contributed none, and
  its canvas is all Board.

### Detector probe

Same settings. Arrival is the one in the tables above, taken from n, s and m.

**CamA 13–25s:**

| Bullet Hole | arrives | n | n + negatives | Note |
|---|---:|---:|---:|---|
| truth #1 | 15.88s | 100% | 100% | |
| truth #2 | 14.64s | 53% | **~100%** | |
| truth #3 | 16.48s | 96% | 97% | at conf 0.40: n ~92%, n + negatives ~24% |
| truth #4 | 17.08s | 62% | **20%** | first at 17.44s, none after 22.88s |
| truth #5 | 14.00s | 85% | **50%** | blind 20.64–22.32s, none after 23.52s |
| truth #6 | 15.24s | 100% | ~100% | |
| mean | | **83%** | 78% | |

**CamB: saturated, as for the other three.** All ten new Bullet Holes are seen
in every frame from arrival to the end of the clip, or all but a handful.
`_102450` truth #3 is first seen at 31.44s. **There is no numeral flicker
either**: the first Detection near `_102450` truth #2 is the Hit at 32.40s, as
for s and m.

### Pipeline

| Recording | n TP/FP/FN | n + negatives |
|---|---|---|
| CamA 13–25s | 5/1/1 | 4/0/2 |
| `_102250` 0–46s | 4/1/0 | 4/0/0 |
| `_102450` 0–47.76s | 4/0/0 | 4/0/0 |
| `_103223` 0–51.88s | 2/1/0 | 2/0/0 |
| **pooled, 16** | 15/3/1, F1 0.88 | **14/0/2**, F1 0.93 |

Per Bullet Hole, it finds what n finds, except that it also misses CamA truth
#3. Like n, it misses CamA #4.

- **The false negatives are the detector.** `--no-change-filter` loses the same
  two. #4 is at 20% since arrival. #3 is the confidence failure s showed on
  `_102250` #3: seen in 97% of frames since arrival at conf 0.02, but ~24% at
  0.40, against n's ~92%. Over the CamA clip at 0.40, this checkpoint also
  matches a detection to a pre-existing mark 205 times, against n's 725, and it
  holds a different set of them (below).
- **No false positive survives, and none of n's three appears.** It does not
  produce the CamA 830 px mark or `_102250`'s ring 8. Nor does it confirm
  `_103223`'s insect at 19.76s, even without the change filter. None of those
  three is gravel, which is what the 15 negatives are, so nothing here ties the
  gain to them rather than to the confounds above.
- **Before the change filter it is no cleaner.** Its counts are all read
  directly from `--no-change-filter` runs; n's are from the table above, and
  CamA's is re-read the same way:

  | Recording | n | n + negatives |
  |---|---:|---:|
  | CamA | 5 | 7 |
  | `_102250` | 2 | 0 |
  | `_102450` | 0 | 0 |
  | `_103223` | 1 | 2 |
  | **pooled** | 8 | **9** |

  All 9 are `[model only]` and `detector`, and the filter removes every one. On
  CamA, 3 sit on Target 1's printed rings, against n's 4. The other 4 are a
  kind n does not produce: on the backing paper, off any Target. **This
  checkpoint's CamA baseline is not n's.** It misses the four dark marks on the
  backing paper below Target 2 that n's baseline holds, and holds three on
  Target 2 that n's does not. One of those four comes back as a new false
  positive. The other three sit on spots n neither holds nor reports. That was
  checked on both rendered runs (`new_bullet_holes --no-change-filter --out`).
  None is on the gravel. `_103223`'s two arrive at 7.12s and 7.36s, before the
  Hit.

### What this says, and what it does not

- **This run costs some recall on CamA and none on CamB.** CamB is
  saturated. On CamA the mean falls from 83% to 78%: #2 gains, #4 and #5 lose,
  and the pipeline loses #3 to confidence.
- **The precision gain comes through the filter.** There are 0 false positives
  after it, against n's 3, but 9 before it, against n's 8. None of the 9 carries
  change evidence; n's 3 survivors do. None of them is gravel. On CamA its baseline holds a different set of old
  marks, and one that it misses comes back as new.
- **The target failure is not on these clips.** Neither n nor this checkpoint
  confirms anything on CamA's gravel, in-sample or not. Whether the negatives
  fix gravel is still the sealed set's to show.
- **The differences are the size of CamA's grid noise** (above), and these are
  the fitted clips, with every constant fitted to n. Pooled, F1 0.93 against
  0.88 is one Bullet Hole lost and three false positives gone, over 16 Bullet
  Holes and 2 Capture Setups.
