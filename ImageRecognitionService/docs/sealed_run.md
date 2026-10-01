# The sealed run

**Run once, 2026-10-01, at `54a49a8`.** Issue #31. This is the one evaluation
of the frozen system on footage nothing was tuned or chosen on (ADR-0005). The
model, the constants and the commit were written down in #31 before any sealed
recording was opened:

- **Model:** `kanat_yolo26n_v1`, sha256 `f7e407c6…b23e3e`.
- **Constants:** every constant at its value at `54a49a8`, with no CLI overrides.
- **Environment:** opencv-python 4.10.0.84, ultralytics 8.4.126, torch 2.13.0.

**Nothing here moves a constant or a model, and neither recording is run
again.** The result is reported as it came out.

**1 genuinely distinct Capture Setup, 2 Bullet Holes.** The result rests on
that sample. It is **not a statistically meaningful validation** of anything.
It is the first, and only, reading on a camera pose nothing was fitted to.

## Scope

At `54a49a8`, `config/recordings.json` seals 14 recordings in four Capture
Setups. Only the `camb-20260915-wide-two-boards` pair has photograph truth, so
only that pair was run. The other 12 are all CamA: 2 `-wide-tight`, 7 `-wide`
and 3 `-close-cross`. They have no truth, they were **not opened**, and they
stay sealed. The probe was not run: #31 does not require it, and it would have
been a second pass over the same recordings.

```bash
.venv/bin/python -m tools.evaluate data/videos/CamB_20260915_101450.mkv --start 0 --end 45.0 \
    --truth-labels data/truth/camb-20260915-101450 --final-run
.venv/bin/python -m tools.evaluate data/videos/CamB_20260915_101550.mkv --start 0 --end 48.28 \
    --truth-labels data/truth/camb-20260915-101550 --final-run
```

The windows are the manifest's provisional whole-clip windows, fixed before the
run. The run checks added to `data/sealed_runs.log` are the two entries in it.
The second entry reads `54a49a8-dirty`. That was predicted in #31 before the run:
the first run created the log, which is a tracked path. `git status` confirmed
the log was the only change before the second run started.

## Headline

| Recording | New (truth) | Reported | TP | FP | FN | Precision | Recall | F1 | FP attributed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `_101450` | 1 | 0 | 0 | 0 | 1 | — | 0% | 0.00 | — |
| `_101550` | 1 | 1 | 0 | 1 | 1 | 0% | 0% | 0.00 | 1 displacement, 32 px |
| pooled | 2 | 1 | 0 | 1 | 2 | 0% | 0% | 0.00 | 1 displacement |

(`evaluate.py` prints precision 0% for `_101450` when nothing is reported. 0/0
is shown as "—" here.)

**Registration residual**, template px, censored at the 20.0 px match radius:

| Recording | Baseline-matched detections | Median | Max |
|---|---:|---:|---:|
| `_101450` | 14 759 | 4.2 | 20.0 |
| `_101550` | 1 073 | 11.7 | 20.0 |

On both recordings the max sits on the ceiling. The fitted clips show the same
thing (HANDOVER). `_101550`'s median is just above the 7.9–11.1 recorded on every
unsealed clip (HANDOVER, `falsification_run.md`). `_101450`'s is below that range.

## What each run disclosed

These are the runs' own lines, restated. No cause is adjudicated here beyond
what the tooling printed.

**`_101450`.** 3 Targets. ECC converged at 0.952. The baseline held 21
pre-existing marks. Two candidates persisted, and the change-evidence filter
removed both (`2 -> 0`). The output does not say whether either was the truth
mark. The truth label lands on the canvas: `evaluate.py`'s off-canvas truth
warning did not fire. 22.2% of the camera's view is off the canvas short of any
Board edge (up to 0.37 Target spans right, 0.41 over the run). The truth names
no pre-existing mark, so placement is unverified.

**`_101550`.** 2 Targets. ECC converged at only **0.641**. "The camera's view
does not map onto the Board plane", so how much of the view is off the canvas
is unknown. The baseline held 3 pre-existing marks. The one reported Bullet
Hole was first detected at 0.84 s and seen in 18% of frames after that. It is a
Miss, attributed to **displacement**: it is 32 template px from a mark the
baseline already held. **Placement is doubtful:** the photograph's one
pre-existing mark lands on nothing the baseline holds (0 of 1 within 40 px).
Either the truth placement is off or the baseline missed that mark, and the
score carries that doubt.

## What this cannot say

- With 2 Bullet Holes in 1 Capture Setup, 0/2 recall is no more an estimate of
  the pipeline's recall than 2/2 would have been.
- On `_101550`, a doubtful placement, a low ECC correlation and a
  displacement-attributed false positive all appear together. These are
  disclosures, not a diagnosis, and none of them is followed up on these
  recordings. ADR-0005 rules that out: anything changed on what this shows
  would have no held-out set left to test it.
- The 12 sealed CamA recordings remain unspent. Scoring them needs photograph
  truth, or the operator-labelled first frame ADR-0005 allows. Opening them is a
  separate human decision, not a continuation of this run.

## Raw output

`_101450`:

```text
[TRUTH] 1 labelled Bullet Holes from board.new.txt, registered to the baseline frame at correlation 0.9793 (convergence, not geometry)
[BOARD] 3 Target(s), ECC converged at 0.9520 (convergence, not geometric accuracy)
[BOARD] rectified 1684x1142, imgsz 1696, net scale 0.91
[WARN] 22.2% of the camera's view is off the canvas short of any Board edge found, up to 0.37 right (view, no edge found) (Target spans). Board there is never searched: a Bullet Hole on it is a miss no setting can recover (#41, #46)
[INFO] baseline: 21 pre-existing Bullet Holes over 5 frame(s) from 0.0s
[WARN] registered frames put the view further off the canvas than the baseline did, up to 0.41 right (Target spans): the camera moved, or registration far from the Targets wandered. A Bullet Hole there is a miss no setting can recover (#41)
[REGISTRATION] residual on 14759 baseline-matched detection(s): median 0.6, max 2.8 Board px, censored at the 2.8 Board px match radius — beyond it a displaced mark is reported as new, so a max at the ceiling means displaced marks are reaching the threshold. Not a pass/fail bar; none is validated
[FILTER] change evidence required: 2 -> 0 Bullet Holes
[INFO] 0 new Bullet Holes (0 on a Target, 0 Miss)
[WARN] placement unverified: the truth names no pre-existing mark to check it against, and the registration correlation is not a geometry check. A wrong placement would change this score silently.

[SCORE] TP 0  FP 0  FN 1   precision 0%  recall 0%  F1 0.00
   missed: truth #1
[REGISTRATION] residual on 14759 baseline-matched detection(s): median 4.2, max 20.0 template px, censored at the 20.0 template px match radius — beyond it a displaced mark is reported as new, so a max at the ceiling means displaced marks are reaching the threshold. Not a pass/fail bar; none is validated
```

`_101550`:

```text
[TRUTH] 1 labelled Bullet Holes from board.new.txt, registered to the baseline frame at correlation 0.9790 (convergence, not geometry)
[BOARD] 2 Target(s), ECC converged at 0.6407 (convergence, not geometric accuracy)
[BOARD] rectified 837x701, imgsz 832, net scale 0.89
[WARN] the camera's view does not map onto the Board plane; how much of it is off the canvas is unknown (#41)
[INFO] baseline: 3 pre-existing Bullet Holes over 5 frame(s) from 0.0s
[REGISTRATION] residual on 1073 baseline-matched detection(s): median 3.3, max 5.7 Board px, censored at the 5.7 Board px match radius — beyond it a displaced mark is reported as new, so a max at the ceiling means displaced marks are reaching the threshold. Not a pass/fail bar; none is validated
[FILTER] change evidence required: 1 -> 1 Bullet Holes
[INFO] 1 new Bullet Holes (0 on a Target, 1 Miss)
  #1  t= 0.84s  MISS      persistence 60%  [changed]
      first detected: 0.84s   last detected: 41.08s   detected in 215 frame(s), 18% of frames since
[PLACEMENT] 0 of 1 pre-existing mark(s) in the photograph land within 40 template px of a mark the baseline holds
[WARN] 1 pre-existing mark(s) land on nothing the baseline holds: the truth placement is off, or the baseline missed them. Scores below carry that doubt.

[SCORE] TP 0  FP 1  FN 1   precision 0%  recall 0%  F1 0.00
   missed: truth #1

[ATTRIBUTION] 1 false positive(s): 1 displacement, 0 detector, 0 unknown (displacement within 40 template px of a mark the baseline already held, detector beyond 80)
   found #1  displacement nearest pre-existing mark 32 px
[REGISTRATION] residual on 1073 baseline-matched detection(s): median 11.7, max 20.0 template px, censored at the 20.0 template px match radius — beyond it a displaced mark is reported as new, so a max at the ceiling means displaced marks are reaching the threshold. Not a pass/fail bar; none is validated
```
