# Model bench: yolo26n, s and m, and yolo26n with background negatives

**Measured 2026-09-30 at `542abd3`**, issue #30. `opencv-python==4.10.0.84`,
`ultralytics==8.4.126`, inference on CPU (the runtime's default device), every
constant at its current value. No sealed recording was opened and no
`--final-run` was passed; `data/sealed_runs.log` still does not exist.

**Nothing is promoted.** `DEFAULT_MODEL` is still `kanat_yolo26n_v1`. The four
recordings below are the fitted clips and the threshold-work pair. The standing
order is not to move anything on them, and a model is not an exception. The
comparison that could choose a model is the sealed set, and it has not been run.

## The checkpoints

Read from each checkpoint's own `train_args`. **Every run is a fresh training run
from the COCO-pretrained weights of its size. None continues from the shipped
checkpoint.** All train at image size 960 on the same dataset, `pibh`. Its copy
is now local (6557 train / 1605 val / 96 test images, one class,
`bullet_hole`), so the recipe can be re-run. It is no longer only a path on
Kaggle.

| Checkpoint | Local path (`trained_models/`, not committed) | sha256 | Started from | imgsz | Epochs (best) | Batch | Where, ultralytics |
|---|---|---|---|---:|---:|---:|---|
| n, shipped | `kanat_yolo26n_v1/weights/best.pt` | `f7e407c6…` | `yolo26n.pt`, fresh | 960 | 100 (100) | 8 | Kaggle, 8.4.130 |
| s | `kanat_yolo26s_v1/weights/best.pt` | `511ca5c4…` | `yolo26s.pt`, fresh | 960 | 100 (99) | 8 | Kaggle, 8.4.158 |
| m (the "in-flight" run) | `kanat_yolo26m_v1/weights/best.pt` | `1a6a5a86…` | `yolo26m.pt`, fresh | 960 | **200** (198) | **4** | the Linux GPU box, 8.4.165 |
| n + negatives | *pending* | | `yolo26n.pt`, fresh | 960 | 100 | 8 | the Linux GPU box |

Seed 0, patience 20, `close_mosaic` 10, default augmentation and `optimizer=auto`
on all of them.

**m is not only a capacity step.** It trained twice as many epochs at half the
batch, so m against n confounds capacity with schedule. **s is the like-for-like
capacity step**: same recipe, same platform, only the size changes.

Validation mAP50-95 (0.870 / 0.885 / 0.904) is on `pibh`'s own val split.
Nobody has audited that split for the frame leakage `dataset_audit.md` found
in the Roboflow export it did audit (3830 train images, not `pibh`'s 6557). It
is listed for identity, not for comparison.

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
recording and the rates compare directly. **Since arrival** is hits over the
frames from the earliest first detection any of the three checkpoints made,
taken from the printed rate (±1 point of rounding).

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
| | truth #3 | 1.64s | ~100% | **89%** | ~100% | s's last sighting is 45.72s |
| | truth #4 | 30.60s | ~100% | ~100% | ~100% | |
| `_102450` | truth #1 | 32.92s | ~100% | ~100% | ~100% | |
| | truth #2 | 32.40s | ~100% | ~100% | ~100% | n also fires near it on and off from 8.60s to 15.48s, before the bullet: the ring-numeral flicker `falsification_run.md` records. s and m do not |
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

Each Bullet Hole, ✓ found and ✗ missed:

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

**The misses are the detector, not the change filter.** Rerun with
`--no-change-filter`, CamA gives the same misses for every checkpoint: s never
confirms #1, #2 or #4 at conf 0.40, and m never confirms #2 or #6. Each is a
mark the probe shows fading for that checkpoint. s's `_102250` truth #3 is not
confirmed without the filter either, and it is the one miss the conf-0.02
probe does not explain: s sees it in 89% of frames there. Probed again at the
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
- `_103223`: all three report the insect or debris that lands at ~19.8s. It is
  a real object, which persistence and change evidence pass by construction
  (`falsification_run.md`).

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
change against the baseline). The filter removes all but the six false
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

## yolo26n with background negatives — pending

The training-data experiment, kept apart from capacity: the shipped n recipe
with the #28 negatives added and nothing else changed.

- **Fresh from `yolo26n.pt`, imgsz 960, 100 epochs, batch 8, seed 0, patience
  20**, on the Linux GPU box that trained m. This re-runs the recipe with data
  added; it does not fine-tune the shipped checkpoint. On this Mac's MPS the
  recipe measured ~1.4 s an iteration, about 33 h.
- **Data:** [`config/pibh_negatives.yaml`](../config/pibh_negatives.yaml),
  placed in the `pibh` root with `data/negatives` copied in beside it as
  `negatives/`:

  ```bash
  yolo train model=yolo26n.pt data=pibh_negatives.yaml imgsz=960 epochs=100 batch=8 \
      seed=0 patience=20 close_mosaic=10 workers=2 device=0 name=bullet_hole_negatives
  ```

  The train scan should read `6572 images, 18 backgrounds`. That is the 15
  negatives plus 3 `pibh` train images that ship without a label file. If
  Kaggle's copy matched, the shipped n trained on those 3 as well. Before this
  run, `pibh` held no intentional background at all.
- **Dose.** 15 negatives in 6572 images is 0.23%. A null result would say that
  these 15 at that weight changed nothing. It would not say that background
  negatives cannot work.
- **Where they come from.** All 15 are `cama-20260914`, 5 of them from
  `CamA_20260914_141546` itself (`data/negatives/sources.csv`). So CamA's
  gravel is in-sample for this checkpoint. The CamB close trio contributed
  none, and its canvas is all Board.
- **What can show the effect.** The probe measures recall only, so it shows
  whether the negatives cost any. The target failure, gravel, is not what any
  false positive above is made of, so the pipeline score has little room to
  show a gain on these clips either.

When the checkpoint arrives it goes to `trained_models/kanat_yolo26n_neg_v1/`
and runs through the same two commands on the same four recordings.
