# Falsification run on the threshold-work recordings

**Measured 2026-09-27 at `ca7d595`**, `kanat_yolo26n_v1`, `opencv-python==4.10.0.84`,
every constant at its current value. Issue #29. The two recordings are
`CamB_20260915_102450` and `CamB_20260915_103223`, the threshold-work pair
`recordings.json` allocates, each run over its manifest window (the whole clip,
0–47.76s and 0–51.88s). No sealed recording was opened; `sealed_runs.log` is
unchanged.

These recordings may falsify a constant, not optimise one (ADR-0005). Nothing
here moves a value. Two things broke, and each is a defect naming its mechanism:
**#40** (scoring cannot place photograph truth on CamB) and **#41** (the canvas
ends before the Board does).

**Both recordings are the `camb-20260915-close-one-board` Capture Setup**, the
same as `_102250`, which every constant is already fitted to. So this run adds
six Bullet Holes and **no Capture Setup**: the evidence goes from two setups and
nine Bullet Holes to two and fifteen, not the "at most four and seventeen" the
ticket allowed. Anything that is a property of the physical set-up — the hue
gate, the Target area floor, net scale — is exercised here only a second time
on one arrangement, and that is said below per constant.

## Headline, as the tools report it

```bash
.venv/bin/python evaluate.py videos/CamB_20260915_102450.mkv --start 0 --end 47.76 \
    --truth-image ~/Downloads/KanatVideos/CamB_20260915_102450.after.jpeg \
    --truth-labels truth/camb-20260915-102450
# and the same for _103223 over 0-51.88; probe.py with the same arguments
```

| Recording | New (truth) | Reported | TP | FP | FN | F1 | FP attributed | Probe rate, every label |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `_102450` | 4 | 2 | 0 | 2 | 4 | 0.00 | 2 detector | 0.00 |
| `_103223` | 2 | 3 | 0 | 3 | 2 | 0.00 | 3 detector | 0.00 |

**These numbers measure the scoring, not the pipeline.** A probe rate of 0.00
at conf 0.02 over 1194 and 1297 frames, on every label of both recordings, is
not a detector: the detector finds 7 and 9 marks in the baseline of the same
footage. The labels are not on the Board.

`evaluate.truth_in_template` registers the after photograph straight to the
printed artwork. On the CamB photographs that fit correlates 0.69 and 0.74 and
throws labels up to 55 000 template px from where they belong (the
template is ~1 100 px across). CamA's photograph fits at 0.976, and
`truth/camb-25-36` was scored against a **video frame**, never a photograph —
so this is the first time a CamB recording has been scored against its
photograph, and the path has never worked for one. Raised as **#40**.

## Headline, diagnostic: truth placed through a video frame

To get past #40 without fixing it here, the after photograph was registered to
the baseline **video frame** (one ECC, photo → frame, the way the derivation
registers photograph to photograph) and taken to template space through that
frame's own homography — the runtime's frame of reference. Scoring and
attribution are `evaluate.score` and `evaluate.attribute`, unchanged, at the
40 px tolerance.

How far to trust that placement, measured without ground truth: the after
photograph's **pre-existing** marks are the same physical holes the pipeline's
baseline holds, and they land **13–32 template px** from them on `_102450` (6 of
6 paired) and **17–35** on `_103223` (7 of 10 paired). Most of the 40 px
tolerance is spent on placement before the detector is judged.

| Recording | TP | FP | FN | F1 |
|---|---:|---:|---:|---:|
| `_102450` | 2 | 0 | 2 | 0.67 |
| `_103223` | 1 | 2 | 1 | 0.40 |
| `_103223`, adjudicated by eye (below) | 2 | 1 | 0 | 0.80 |

Every mark was then checked in the pixels — crops of the baseline and a late
frame with detections and projected labels drawn, and the after photograph:

- **`_102450` #1, t=32.40s, Target 1, scores 10.** Absent at 32.0s, present at
  32.6s: reported inside the window it arrived in. The probe's earlier sighting
  at 11.04s is the detector on the printed ring numerals for half a second, and
  persistence rejected it, as designed.
- **`_102450` #2, t=32.92s, Miss**, above the Target sheet. Matched at 20 px.
- **`_102450` truth #3 and #4, never reported.** Two new holes on the white
  Board ~1.7 Target-spans below the Target, visible in the late frame and
  labelled in the photograph. They project to Board y 341 and 353 on a 315 px
  canvas: **outside the image the detector is given**. Raised as **#41**.
- **`_103223` #1, t=11.20s, Miss**, high on the white Board. Scored FP + FN: the
  label lands 73 px from it (42 under a second fit). The crops settle it — one
  hole, absent at t=0, present late, with the label's cross one hole-width below
  it. It is the labelled Bullet Hole, and **placement** error pushed it past the
  tolerance. It sits on the canvas edge (Board y 13 of 348), see #41.
- **`_103223` #2, t=11.20s, Target 1, outside rings** — the top of the green
  silhouette. Matched at 19 px.
- **`_103223` #3, t=19.76s, Miss — a real false positive, and not a
  hallucination.** Something dark lands on clean paper at ~20s, with streaks
  that move between frames, and stays through 45s; the after photograph shows
  clean paper there. An insect or debris on the Board. It persists (96%) and it
  is a real change (`[changed]`), so persistence and change evidence both pass
  it **by construction**. `[ATTRIBUTION]` calls it `detector` at 255 px from
  anything pre-existing, which is right about where the error entered and
  says nothing about what the object was.

**Pooled: 6 new Bullet Holes, 4 found, 1 false positive.** All 4 on the canvas
were found; both misses are off it. Recall 67%, 100% of what was in the image.

**`[ATTRIBUTION]` cannot tell a placement miss from a detector error.** It asks
only how far a false positive is from a mark the baseline held, so `_103223` #1
— a correct detection the scoring could not credit — reads `detector, 490 px`.
Under #40's placement every false positive on both recordings reads `detector`.
Its causes are displacement, detector, unknown; a truth-placement miss is none
of them and lands in `detector`. Recorded, not changed: #40 is the cause, and
attribution is only as good as the truth it reads.

## Detector probe, per Bullet Hole

`probe.py --at`, conf 0.02, at the diagnostic placements. The rate's
denominator is every frame from t=0, so a mark arriving mid-clip cannot reach
1.0; "since arrival" is the share of frames from its first sighting.

| Recording | Bullet Hole | Rate | First | Last | Since arrival | Note |
|---|---|---:|---:|---:|---:|---|
| `_102450` | #1 (above sheet) | 0.29 | 32.92s | 47.72s | ~94% | |
| `_102450` | #2 (10-ring) | 0.32 | 11.04s | 47.72s | ~97% from 32.40s | 11.04s is the numeral flicker |
| `_102450` | truth #3 | 0.00 | — | — | — | off canvas, #41 |
| `_102450` | truth #4 | 0.00 | — | — | — | off canvas, #41 |
| `_103223` | #1 (high Board), at the label | 0.00 | 13.36s | 14.24s | — | label 73 px off the mark |
| `_103223` | #1, at the mark itself | 0.42 | 11.20s | 51.72s | ~54% | canvas edge |
| `_103223` | #2 (silhouette) | 0.78 | 11.20s | 51.84s | ~99% | |
| `_103223` | the object, not a Bullet Hole | 0.58 | 19.76s | 50.04s | ~94% | |

Every Bullet Hole in the image is seen by the detector. The one weak rate,
~54% (the pipeline counts 45%), is the mark on the canvas edge.

## Registration residual

| Recording | median | max | match radius |
|---|---:|---:|---:|
| `_102450` | 1.1 Board px / **7.9** tpl px | 2.9 / 20.0 | 2.9 / 20.0 |
| `_103223` | 1.7 Board px / **11.1** tpl px | 3.1 / 20.0 | 3.1 / 20.0 |

Over 7 555 and 9 827 baseline-matched detections. The medians sit with CamA's
11.1 and `_102250`'s 10.1 template px, and the max is on the censoring ceiling
again, on both — displaced pre-existing marks are reaching the threshold here
too. None of them crossed it: no false positive attributes to displacement in
either reading.

## Every provisional constant, against this footage

**Supports** means this footage exercised the constant and it held.
**Breaks** means it failed on this footage and a defect names the mechanism.
**Says nothing** means nothing here could have shown it wrong.

| Constant | Value | Verdict | Grounds |
|---|---|---|---|
| `PERSIST` | 0.50 | supports | All 4 Bullet Holes in the image confirmed, at 80–100%; the 11.04s numeral flicker rejected. Thinnest margin: `_103223` #1 at 80% in its window and 45% over the rest of the clip — a window starting later would have lost it. A physically present non-hole object passes it by design (`_103223` #3). |
| `PERSIST_FRAMES` | 50 | says nothing | No Bullet Hole arrived near either clip's end, and nothing here compares window lengths. |
| `DEFAULT_CONFIDENCE` | 0.40 | supports | No Bullet Hole in the image was lost to the floor; the only false positive is a real object, not a low-confidence box. Says nothing about the optimum. |
| `BASELINE_FRAMES` | 5 | supports, weakly | No hit in the first 200 ms, no 0.04s-style re-detection. Baselines hold 7 and 9 marks against 6 and 10 labelled pre-existing. |
| `REQUIRE_CHANGE_EVIDENCE` | True | says nothing | 2 → 2 and 3 → 3: it removed nothing. The one false positive is a real change. |
| `ABSDIFF_SIGMA` | 2.0 | supports | Every confirmed detection is `[changed]`; the evidence channel is alive. |
| `MATCH_TPL_PX` | 20.0 | supports | No real new Bullet Hole suppressed, no displaced mark reported. Residual max on the ceiling on both, as before. |
| `DUP_CENTER_FACTOR` | 0.5 | says nothing | No split marks and no close pairs of new holes in either recording. |
| `OVERLAP_THRESHOLD` | 0.5 | says nothing | Same. |
| `TARGET_NET_SCALE` | 0.90 | supports, same setup | Net scale 0.91 and 0.87; detection healthy. One Capture Setup, already fitted. |
| `BOARD_MARGIN` | 0.50 | **breaks — #41** | 2 of 6 new Bullet Holes outside the canvas, a third on its edge. The Board extends well past half a Target-span and gets shot. |
| `GREEN_LO` / `GREEN_HI` | — | supports, same setup | Target found in every frame, 0 lost. Same light and artwork as `_102250`. |
| `MIN_TARGET_AREA_PX` | 5000 | says nothing | One large Target, same pose as `_102250`. |
| `MATCH_TOLERANCE_TPL` | 40 | says nothing until #40 | Photograph placement error on this footage is 13–35 px, one case 73. The tolerance cannot be judged while placement uses most of it. |
| `UNKNOWN_FACTOR` | 2.0 | says nothing | No false positive fell between 40 and 80 px under either placement. |
| `NON_COOCCURRENCE_MERGE`, `MAX_DISPLACEMENT_FRACTION` | off, 0.35 | says nothing | Off by default, and no displaced pair appeared. Still one Target, so the distance scaling cannot be re-derived. |

The measured artwork landmarks (`RING_*_TPL`) are readings, not tunables. The
ring score on `_102450` #1 (10) is the second real hit on a Target after
`_102250`'s two, and agrees with the crop.

## What this run does not show

- **Generalisation.** One Capture Setup, already fitted. The sealed wide pair is
  the only held-out pose (#31).
- **A pipeline F1 that stands without adjudication.** The diagnostic scores
  depend on a placement whose error is most of the tolerance, and one mark was
  credited by eye. The tool's own headline is 0.00 until #40 lands.
- **Anything about the ring scoring beyond one hit.**
