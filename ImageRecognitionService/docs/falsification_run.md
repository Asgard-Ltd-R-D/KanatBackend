# Falsification run on the threshold-work recordings

**Measured 2026-09-27 at `7ef2ffe`** (after #34 and #40), `kanat_yolo26n_v1`,
`opencv-python==4.10.0.84`, every constant at its current value. Issue #29. The
two recordings are `CamB_20260915_102450` and `CamB_20260915_103223`, the
threshold-work pair `config/recordings.json` allocates, each run over its manifest
window. No sealed recording was opened and no `--final-run` was passed, so no
sealed run was logged.

These recordings may falsify a constant, not optimise one (ADR-0005). Nothing
here moves a value. One constant breaks, and it is a defect naming its
mechanism: **#41** (the canvas ends before the Board does).

**This replaces the first run of this record**, made at `ca7d595` before #40.
That run's headline — F1 0.00 on both recordings, probe rate 0.00 on every
label, every false positive `detector` — was the photograph registration
throwing labels up to 58 000 template px off the Board, **not a pipeline
result**, and is not reproduced here as one. What changed, and why, is at the
end.

**Both recordings are the `camb-20260915-close-one-board` Capture Setup**, the
same as `_102250`, which every constant is already fitted to. So this run adds
six Bullet Holes and **no Capture Setup**: the evidence goes from two setups and
ten Bullet Holes to two and sixteen, not the "at most four and seventeen" the
ticket allowed (its starting nine predates the derived truth, which gives
`_102250` four). Anything that is a property of the Capture Setup — the hue
gate, the Target area floor, net scale — is exercised here only a second time
on one arrangement, and that is said below per constant.

## Headline

```bash
.venv/bin/python -m tools.evaluate data/videos/CamB_20260915_102450.mkv --start 0 --end 47.76 \
    --truth-labels data/truth/camb-20260915-102450
.venv/bin/python -m tools.evaluate data/videos/CamB_20260915_103223.mkv --start 0 --end 51.88 \
    --truth-labels data/truth/camb-20260915-103223
# tools.probe with the same arguments. --truth-image comes from board.source.txt (#34).
```

Truth is placed through the baseline video frame (#40): photograph → frame at
correlation 0.9947 and 0.9806, then the frame's own homography to template.

| Recording | New (truth) | Reported | TP | FP | FN | Precision | Recall | F1 | FP attributed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `_102450` | 4 | 2 | 2 | 0 | 2 | 100% | 50% | 0.67 | — |
| `_103223` | 2 | 3 | 2 | 1 | 0 | 67% | 100% | 0.80 | 1 detector, 255 px |
| pooled | 6 | 5 | 4 | 1 | 2 | 80% | 67% | 0.73 | 1 detector |

**Both false negatives are off the canvas** — Board y 346 and 359 on a 315 px
canvas, so no detector setting could have found them (#41). Every new Bullet
Hole the detector was shown was found and scored, by the scorer, with no
adjudication by eye.

**How far to trust the placement**, measured on every run without ground truth
(`[PLACEMENT]`): the after photograph's pre-existing marks are the Bullet Holes
the baseline holds, and they land **3–16 template px** from them on `_102450`
(6 of 6) and **6–12 px** on `_103223` (8 of 10). The matches themselves sit at
5–23 px. Placement now uses under half the 40 px tolerance, where the frame
diagnostic of the first run used 13–35 of it.

`_103223`'s two unpaired pre-existing marks are **not a placement error**: they
land at Board y 381 and 396 on a 348 px canvas, below it, where no baseline can
hold them. `[PLACEMENT]` warns "the truth placement is off, or the baseline
missed them" — neither; the canvas ends first (#41). The warning cannot tell
the cases apart because it does not exclude off-canvas marks, as the scoring
`[WARN]` does. Recorded, not changed here; since fixed under #41, which
leaves off-canvas marks out of `[PLACEMENT]` and names them.

### Every mark

- **`_102450` truth #2, found #1, t=32.40s, Target 1, scores 10.** Matched at
  5 px. The earlier pixel check stands: absent at 32.0s, present at 32.6s. The
  probe's first detection at 11.04s is the detector on the printed ring
  numerals for half a second, and persistence rejected it, as designed.
- **`_102450` truth #1, found #2, t=32.92s, Miss**, above the Target. Matched at
  23 px.
- **`_102450` truth #3 and #4, never reported.** Two new Bullet Holes on the
  white Board ~1.7 Target-spans below the Target, visible in the late frame and
  labelled in the photograph, **outside the image the detector is given**
  (#41).
- **`_103223` truth #1, found #1, t=11.20s, Miss**, high on the white Board.
  Matched at 18 px. The first run could credit it only by eye (the frame
  diagnostic put the label 73 px out); the corrected placement credits it.
  It sits on the canvas edge, Board y 1 of 348, and was confirmed only because
  its first 50-frame window ran at 80% — 45% of the frames after it.
- **`_103223` truth #2, found #2, t=11.20s, Target 1, outside rings** — the top
  of the green silhouette. Matched at 11 px.
- **`_103223` found #3, t=19.76s, Miss — a real false positive, and not a
  hallucination.** The same detection the first run checked in the pixels:
  something dark lands on clean Board at ~20s, with streaks that move between
  frames, and stays through 45s; the after photograph shows clean Board there.
  An insect or debris. It persists (96%) and is a real change (`[changed]`), so
  persistence and change evidence both pass it **by construction**.
  `[ATTRIBUTION]` calls it `detector` at 255 px from anything pre-existing,
  which is right about where the error entered and says nothing about what the
  object was.

**The ADR-0006 gap the first run flagged** — a truth-placement miss has no
cause of its own and lands in `detector` — does not arise on the corrected
run: no correct detection is scored false. It remains true in principle, since
`attribute` only asks how far a false positive is from a baseline mark, and it
is the reason `[PLACEMENT]` exists.

## Detector probe, per Bullet Hole

`probe.py`, conf 0.02, radius 40 template px, at the corrected placements. The
rate's denominator is every registered frame from t=0 (1194 and 1297, none
lost), so a mark arriving mid-clip cannot reach 1.0; "since arrival" is hits
over the frames from its arrival, from the printed rate (±1 point of rounding; ±5 for truth #2, whose count includes the numeral flicker).

| Recording | Bullet Hole | Board (x, y) / canvas | Rate | First | Last | Since arrival | Note |
|---|---|---|---:|---:|---:|---:|---|
| `_102450` | truth #1 (above the Target) | 228, 73 / 315² | 0.28 | 32.92s | 47.72s | ~90% | |
| `_102450` | truth #2 (10-ring) | 151, 158 / 315² | 0.32 | 11.04s | 47.72s | ≥95% from 32.40s | 11.04s is the numeral flicker; blind 11.52–32.36s |
| `_102450` | truth #3 | 203, 346 / 315² | 0.00 | — | — | — | **off canvas**, #41 |
| `_102450` | truth #4 | 211, 359 / 315² | 0.00 | — | — | — | **off canvas**, #41 |
| `_103223` | truth #1 (high Board) | 219, 1 / 364×348 | 0.40 | 11.20s | 51.72s | ~51% | canvas edge |
| `_103223` | truth #2 (silhouette) | 181, 103 / 364×348 | 0.78 | 11.20s | 51.84s | ~99% | |

Every Bullet Hole on the canvas is seen by the detector at a rate that
persistence can confirm. The one weak rate, ~51% (the pipeline counts 45% at
conf 0.40), is the mark on the canvas edge. Net scale 0.91 and 0.87.

## Registration residual

| Recording | median | max | match radius | baseline-matched detections |
|---|---:|---:|---:|---:|
| `_102450` | 1.1 Board px / **7.9** tpl px | 2.9 / 20.0 | 2.9 / 20.0 | 7 555 |
| `_103223` | 1.7 Board px / **11.1** tpl px | 3.1 / 20.0 | 3.1 / 20.0 | 9 827 |

Unchanged from the first run — the residual never depended on truth placement.
The medians sit with CamA's 11.1 and `_102250`'s 10.1 template px, and the max
is on the censoring ceiling on both: displaced pre-existing marks are reaching
the threshold here too. None crossed it: no false positive attributes to
displacement.

## Every provisional constant, against this footage

**Supports** means this footage exercised the constant and it held.
**Breaks** means it failed on this footage and a defect names the mechanism.
**Says nothing** means nothing here could have shown it wrong.

| Constant | Value | Verdict | Grounds |
|---|---|---|---|
| `PERSIST` | 0.50 | supports | All 4 on-canvas Bullet Holes confirmed, at 80–100%; the 11.04s numeral flicker rejected. Thinnest margin: `_103223` truth #1 at 80% in its window and 45% over the rest of the clip — a window starting later would have lost it. A physically present non-hole object passes it by design (`_103223` found #3). |
| `PERSIST_FRAMES` | 50 | says nothing | No Bullet Hole arrived near either clip's end, and nothing here compares window lengths. |
| `DEFAULT_CONFIDENCE` | 0.40 | supports | No on-canvas Bullet Hole lost to the floor; the only false positive is a real object, not a low-confidence box. Says nothing about the optimum. |
| `BASELINE_FRAMES` | 5 | supports, weakly | No Hit in the first 200 ms, no 0.04s-style re-detection. The baselines hold every on-canvas labelled pre-existing mark: 6 of 6 and 8 of 8 (the other two are off canvas). |
| `REQUIRE_CHANGE_EVIDENCE` | True | says nothing | 2 → 2 and 3 → 3: it removed nothing. The one false positive is a real change. |
| `ABSDIFF_SIGMA` | 2.0 | supports | Every confirmed detection is `[changed]`; the evidence channel is alive. |
| `MATCH_TPL_PX` | 20.0 | supports | No real new Bullet Hole suppressed, no displaced mark reported. Residual max on the ceiling on both, as on CamA and `_102250`. |
| `DUP_CENTER_FACTOR` | 0.5 | says nothing | No split marks and no close pairs of new Bullet Holes in either recording. |
| `OVERLAP_THRESHOLD` | 0.5 | says nothing | Same. |
| `TARGET_NET_SCALE` | 0.90 | supports, same setup | Net scale 0.91 and 0.87; detection healthy. One Capture Setup, already fitted. |
| `BOARD_MARGIN` | 0.50 | **breaks — #41** | 2 of 6 new Bullet Holes and 2 of 16 labelled pre-existing marks are below the canvas; a third new one is on its edge (y 1 of 348). On both recordings the Board below the Target takes Bullet Holes and is not in the image. |
| `GREEN_LO` / `GREEN_HI` | — | supports, same setup | Target found in every frame, 0 lost. Same light and artwork as `_102250`. |
| `MIN_TARGET_AREA_PX` | 5000 | says nothing | One large Target, same pose as `_102250`. |
| `MATCH_TOLERANCE_TPL` | 40 | supports, weakly | Scoring tolerance, not a pipeline threshold. Placement error 3–16 px, matches 5–23 px, the one false positive 255 px out: every correct detection credited, nothing falsely credited. Nothing landed between 23 and 255 px, so the boundary itself is not tested. |
| `UNKNOWN_FACTOR` | 2.0 | says nothing | No false positive fell between 40 and 80 px. |
| `NON_COOCCURRENCE_MERGE`, `MAX_DISPLACEMENT_FRACTION` | off, 0.35 | says nothing | Off by default, and no displaced pair appeared. Still one Target, so the distance scaling cannot be re-derived. |

The measured artwork landmarks (`RING_*_TPL`) are readings, not tunables. The
ring score on `_102450` truth #2 (10) is the third real Hit on a Target, after
`_102250`'s two, and agrees with the crop.

## What the corrected run changed

| First run (before #40) | Corrected | Why |
|---|---|---|
| Tool headline F1 0.00 / 0.00, every label FN, probe 0.00 on every label | F1 0.67 / 0.80, probe 0.28–0.78 on every on-canvas label | The 0.00s were the photograph registered straight to the artwork (ECC 0.69–0.74), labels 52 000–58 000 tpl px out. They measured scoring, never the pipeline (#40, closed). |
| Every false positive `detector`; `_103223`'s high mark `detector, 490 px` | One false positive, the real object; the high mark is a TP at 18 px | Same cause: no label was on the Board. |
| `_103223` 0.40 by the scorer, 0.80 only with the high mark credited by eye | 0.80 by the scorer | The frame diagnostic's placement error (13–35 px, one mark 73) is gone; the corrected placement is 6–12 px. |
| `MATCH_TOLERANCE_TPL`: says nothing until #40 | supports, weakly | Placement no longer spends most of the tolerance. |
| `[ATTRIBUTION]` cannot tell a placement miss from a detector error — a case on this footage | Not exercised: no placement miss | Still true in principle; no longer evidenced here. |
| `BOARD_MARGIN` breaks: 2 new Bullet Holes off canvas, one on the edge | breaks, and wider: also 2 pre-existing marks off canvas on `_103223` | Seen only once pre-existing marks were placed correctly. Adds nothing to FN (they are not new), but shows the uncovered region on both recordings, and makes `[PLACEMENT]` misread it as a placement doubt. |

Every other verdict, the residual, the pooled "4 found of 4 on the canvas" and
the ruling on `_103223` found #3 are unchanged.

## What this run does not show

- **Generalisation.** One Capture Setup, already fitted. The sealed wide pair is
  the only held-out pose (#31).
- **Recall over the whole Board.** A third of the new Bullet Holes here are
  outside the image the detector sees (#41). The pooled 67% is a canvas bound,
  and on-canvas recall (4 of 4) says nothing about the Board below it.
- **Anything about the ring scoring beyond one Hit.**
