# Live input is sampled at a fixed stride, and persistence runs over the samples

Live, the pipeline looks at every 17th frame of a constant 25 fps stream and
treats the frames between as gaps. It does not try to look at every frame, does
not vary the stride with load, and does not retune persistence for the sparser
sampling. [ADR-0003](0003-a-bullet-hole-is-new-when-it-persists.md)'s window
stays 50 frames at 50%; it now holds about 3 looks instead of 50.

## Why sample at all

The frame loop costs 0.3–0.65 s a look on the development Mac, against a frame
every 40 ms. Live, it cannot look at every frame, and a queue of unlooked
frames grows without bound. The only choices are which frames to drop and
whether dropping them costs real Bullet Holes. A fixed stride answers the first
the same way on a recording as live (`--stride`, #81), so the second can be
measured offline before anything goes live.

## The measurement (#82)

Both spent recordings with ground truth, at their native 25 fps, through
`tools/evaluate.py` on `main` 1d18891, 2026-10-06. No threshold moved. No
Sealed recording was opened
([ADR-0005](0005-the-held-out-set-is-whole-capture-setups.md)), and neither were the threshold-work
recordings: only spent footage.

| Recording | Stride | Looks a window | TP | FP | FN | Candidates before change filter |
|---|---:|---:|---:|---:|---:|---:|
| `CamA_20260914_141546` 13–25s (6 truth) | 1 | 50 | 5 | 1 | 1 | 10 |
| | 9 | ~6 | 6 | 0 | 0 | 17 |
| | 13 | ~4 | 6 | 1 | 0 | 17 |
| | **17** | **~3** | **5** | **0** | **1** | **18** |
| | 25 | 2 | 6 | 0 | 0 | 34 |
| `CamB_20260915_102250` 0–46s (4 truth) | 1 | 50 | 4 | 1 | 0 | 6 |
| | 9 | ~6 | 4 | 1 | 0 | 7 |
| | 13 | ~4 | 4 | 1 | 0 | 7 |
| | **17** | **~3** | **4** | **1** | **0** | **7** |
| | 25 | 2 | 4 | 1 | 0 | 8 |

**No stride loses a true Bullet Hole that stride 1 finds.** CamA's one miss at
strides 1 and 17 is the same mark, truth #4, the one that comes and goes with the
pixel grid since #50. Strides 9, 13 and 25 find it, from 1–3 Detections. CamB's
false positive is the same report at every stride: found #4, the detector, 520
template px from anything pre-existing. CamA's at strides 1 and 13 are two
different detector false positives, 830 and 1590 px out. Every true positive
matches its truth label within 1–13 template px at every stride.

**"Lost" means lost against stride 1.** #82's stop rule, "If any stride that
would keep up live loses true Bullet Holes, stop and report", is about what
sampling costs. #78 runs stride 1 as the reference ("at stride 1 and at
candidate strides … compare confirmed Bullet Holes"), and its stop rule is
phrased "If sampling loses real Bullet Holes". A stride loses a Bullet Hole when
it misses one that stride 1 finds. A truth hole stride 1 misses as well is a
miss of the pipeline, not a cost of sampling. Read the other way, as any miss
at all, stride 1 itself would fail the rule on CamA (5/1/1), and the rule would
then measure the detector rather than the stride. Of the strides that keep up
(13 and above, below), 17 is the only one with a miss, and it adds no false
negative to stride 1's.

**Stride 17's miss is the same Bullet Hole as stride 1's, missed the same way.**
Every run places the truth identically: the same `board.new.txt` line 4, the
same `[TRUTH]` registration (correlation 0.9739), at template (−27.2, 428.1),
602 template px from the nearest baseline mark. The pipeline's own loop was
re-run with persistence opened to 0, so that every elapsed candidate reports
its window:

| Stride | Looks past the baseline seeing truth #4 | Its candidate's first Detection | Looks in that window seeing it | Persistence | Change evidence |
|---:|---:|---|---:|---:|---|
| 1 | 41 of 295 | 17.08 s, frame 102 | 9 of 50 | 0.18, fails | yes |
| 17 | 5 of 17 | 17.08 s, frame 102 | 1 of 3 | 0.33, fails | yes |
| 9 | 3 of 33 | 18.76 s, frame 144 | 3 of 6 | 0.50, passes | yes |
| 13 | 2 of 23 | 19.24 s, frame 156 | 2 of 4 | 0.50, passes | yes |
| 25 | 1 of 11 | 19.00 s, frame 150 | 1 of 2 | 0.50, passes | yes |

The mark is detected for two frames at 17.08 s (102–103), then not again until
18.76 s, where its dense run (144–187) begins. Persistence judges a candidate
once, over the 50 frames after its first Detection (ADR-0003). Stride 1 and
stride 17 both look at frame 102, so the window opens on that two-frame blip
and closes at frame 151, before most of the run. At stride 17 the next Detection,
frame 153, falls two frames past it. Strides 9, 13 and 25 do not look at frame
102 or 103, so their windows open inside the dense run. They recover truth #4
because of where their looks happen to fall, not because they sample better.
A live stream's phase against the Hits is arbitrary, so any stride could land
either way on a mark like this one.

That is ten Bullet Holes on two recordings. It shows that sampling does not
visibly break the pipeline. It does not show that sampling is free. The per-mark
differences between strides (truth #4 in and out, a false positive in and out)
are the same marginal marks moving with every perturbation, and they are no
evidence that one stride is more accurate than another.

## The stride: 17

The smallest stride that keeps up is ⌈time per look × 25⌉. Timed sequentially
on the development Mac (`new_bullet_holes`, wall time, model load included):

| Recording | Stride | Looks | Wall | Video |
|---|---:|---:|---:|---:|
| CamB `_102250` 0–46s | 13 | 93 | 47.2 s | 46 s |
| | 17 | 72 | 37.8 s | 46 s |
| | 25 | 50 | 27.1 s | 46 s |
| CamA `_141546` 13–25s | 9 | 38 | 18.1 s | 12 s |
| | 13 | 28 | 15.0 s | 12 s |

The differences between strides give the cost of one look without the fixed
start-up: **449–488 ms on CamB**, 307 ms on CamA. CamB is the slower setup and
sets the stride. At 488 ms, ⌈0.488 × 25⌉ = 13, which keeps up with 6% to spare
(13 × 40 = 520 ms). HANDOVER's per-frame figures for the CamB close pose,
511–646 ms (#46, 250 frames from 10 s at stride 1), give ⌈0.646 × 25⌉ = 17.

**17 is the live default** (`LIVE_STRIDE`, `detection/new_bullet_holes.py`). It
keeps up with the slowest per-frame time on record on this host, with about
28% to spare at the measured per-look cost (680 ms against 488). It also
measured no loss. Stride 13 has too little margin: a busier frame, a slower
host, or the decoding of the 12 skipped frames a live stream cannot avoid
would put it behind. A stride that falls behind live still loses frames
(#83 drops the ones it is late for), but they fall irregularly, and that is the
behaviour this measurement did not cover.

On a different live host, re-derive the stride from the time per look measured
there, using the same differencing.

## The frame rate is load-bearing

The stride is a count of frames, and so are `PERSIST_FRAMES` (50, ~2 s) and
`BASELINE_FRAMES` (5, ~200 ms). All three are set at 25 fps, and every truth
recording is 25 fps. The AXIS Q6315-LE is therefore configured to a constant
25 fps (#85). At 50 or 60 fps every window would halve in duration and the
stride would need re-deriving. Making the windows time-based or FPS-aware is a
separate decision, not taken here.

#117 does not take it either. Live, it derives each frame's index from the
stream's timestamps at the configured 25 fps, for gap accounting: frames lost
upstream become gaps where a 25 fps stream would have had them, instead of
shifting every later index. On a stream at 20, 30, 50 or 60 fps,
timestamp × 25 would make the windows count stream time rather than frames.
That is outside this decision, and supporting other frame rates remains a
separate one.

## Consequences

**Persistence filters less, and the change filter does more.** Candidates
before the change filter rise with the stride: CamA from 10 at stride 1 to 18
at 17 and 34 at 25. With about 3 looks a window, 50% is 2 looks with a
Detection, and a flicker that lands on 2 of 3 looks passes where it would not
pass on 25 of 50. That the false positives did not rise is the change filter's work
(ADR-0003: evidence, not the gate). Precision live now rests more on it than
the recordings' stride-1 numbers suggest.

**At stride 25, one Detection confirms.** With 2 looks a window, 1 of 2 is 50%.
CamA's truth #4 was confirmed that way. The stride flag already refuses 50
or more (one look a window, which filters nothing). 25 sits on the edge of
the same failure and is not used.

**The first Detection is late by up to a stride less one frame.** At 17 that
is 16 frames, 640 ms, on top of the 2 s confirmation window. Reported times fall on looked-at frames: CamB's
30.60 s mark reads 31.00 s at stride 25. SOW 2.3.4's 0.5 s was already out of
reach (ADR-0003).

**Re-anchoring waits longer.** `REANCHOR_AFTER_LOST` (25) counts looked-at
frames (#80), so at stride 17 a lost Board is re-acquired after about 17 s
rather than 1 s. Neither recording lost a frame, so this was not measured. It
belongs to the live drop handling (#84).

**Nothing here is validated.** The thresholds still fit ten Bullet Holes on
two recordings (ADR-0003, ADR-0005). This ADR shows that sampling at 17 does
not visibly break them on that footage, and no more than that.
