# Live input is sampled at a fixed stride, and persistence runs over the samples

Live, the pipeline looks at every 17th frame of a constant 25 fps stream and
treats the frames between as gaps. It does not try to look at every frame, does
not vary the stride with load, and does not retune persistence for the sparser
sampling. [ADR-0003](0003-a-bullet-hole-is-new-when-it-persists.md)'s window
stays 50 frames at 50%; it now holds about 3 looks instead of 50.

*Amended 2026-11-02 (#277): the stride is 4, not 17. ECC's stopping rule
(#274), the Target Sheet canvases (#275) and the per-Look cleanups (#276) cut
Look Time to a tenth, and the stride is re-derived by this ADR's own rule
below, in "Re-derived: stride 4". The decision is unchanged: a fixed stride,
persistence over the samples. The window now holds about 12 Looks. "The stride:
17" and the stride-17 consequences are kept as the record they were.*

*Amended 2026-11-08 (#314): ADR-0003's window is 25 frames, not 50 (ADR-0003,
amended 2026-11-08). At stride 4 it holds 7 Looks, of which 4 are needed. The
decision is unchanged: the window is still counted in frames and was not
retuned for the stride. At 25 frames, stride 4 still loses nothing against
stride 1 (#310).*

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

## Re-derived: stride 4 (#277, 2026-11-02)

**The rule is the same: the slowest setup's Look Time P99 × 25, with about
28% spare.** Only in-scope footage decides it: one Board and one Target per
camera (#288, `.out-of-scope/more-than-one-board-or-target-per-camera.md`).
That is the close CamB recordings `_102250`, `_102450` and `_103223`. CamA
shows two Targets on one Board, and the wide CamB `_101450`/`_101550` two
Boards, so they do not set the stride. **Once in-scope footage from a
CamA-style camera exists, re-derive the stride from it.**

Look Time at stride 1, CPU, from the regression bench below (`main` 6e18728,
development M1 Pro):

| Recording | In scope | Look Time P50 | P99 | max |
|---|---|---:|---:|---:|
| CamB `_102250` 0–46 s | yes | 35.5 | **94.6** | 95.9 |
| CamB `_102450` 0–47.76 s | yes | 35.0 | 39.9 | 41.4 |
| CamB `_103223` 0–51.88 s | yes | 36.3 | 47.5 | 78.1 |
| CamA `_141546` 13–25 s | no: two Targets | 163.9 | 487.8 | 729.6 |
| CamB `_101450` 0–45 s | no: two Boards | 48.6 | 57.7 | 128.1 |
| CamB `_101550` 0–48.28 s | no: two Boards | 75.0 | 471.7 | 641.1 |

`_102250`'s 94.6 ms decides. ⌈0.0946 × 25⌉ = 3 would leave 21% spare (120 ms);
**4 gives a 160 ms interval and 41% spare**, the smallest stride that keeps
the ~28%. CamA's P99 would give 13–17, and #268 would gain nothing.

**The stride table**, on #268's regression bench (`tools.regression`, all six
truth recordings over their manifest windows, CPU). Stride 1 ran with the
8/16/32 px canvas-shift control. Strides 3, 4 and 5 were ruled against it by
#268's rule, with `compare --across-strides`: no truth Bullet Hole stride 1
finds is lost, no false positive is added, and no matched Position Error moves
over 1 mm or reaches 5 mm. "Lost" is against stride 1, as above.

| Stride | Looks a window | TP / FP / FN at 0 px, all six | FP before the change filter, CamA | Rule against stride 1 |
|---:|---:|---|---:|---|
| 1 | 50 | 10 / 1 / 2 | 12 | the reference |
| 3 | ~17 | 10 / 1 / 2 | 13 | **PASS**: 0 failing, 0 noise |
| **4** | **~12** | **10 / 1 / 2** | **10** | **PASS**: 0 failing, 0 noise |
| 5 | 10 | 10 / 2 / 2 | 20 | **FAIL**: `_101550` adds a false positive at template (750, 674) |

The 6 truth Bullet Holes off every Target Sheet are out of scope at every stride
(ADR-0011). The one false positive at every stride is `_102250`'s, and the two
misses are CamA's truth #4 (above) and `_101550`'s truth #1. At strides 3 and 4
every recording keeps its true positives, misses and false positives. Stride
5's added false positive is on out-of-scope footage, but it is the first sign
of the flicker this ADR's consequences predict as the Looks a window fall. Stride
5 also raises CamA's FP before the change filter from 12 to 20, and adds one on
three CamB recordings. Hit-to-report, from each truth hole's arrival
frame (#273): 1.96 s at stride 1 on every clean CamB hole, 2.08–2.20 s at
stride 4.

**The live replay at stride 4** (`docs/latency_wip.md`'s procedure: H.264
copies of the three in-scope recordings published through VideoService's
MediaMTX v1.21.1, ffmpeg 9.0.2, CPU, eight runs). Late drops are split at
the Run going `watching` (#291). The catch-up before it is out of scope
(`.out-of-scope/catch-up-drops-before-detection-ready.md`):

| Recording | Runs | Late drops before / after `watching` | Look Time P99 | Frame Wait P99 / max | Behind the stream at the first frame past the baseline | Live edge after `watching` |
|---|---:|---|---:|---|---:|---:|
| `_102250` | 3 | 6–7 / 0, 1, 1 | 46–50 ms | 0.8–33.1 / 69–70 ms | 1.23–1.36 s | 0.08–0.09 s |
| `_102450` | 3 | 6 / 1, 1, 1 | 45–47 ms | 0.5–1.9 / 68–70 ms | 1.18–1.24 s | 0.08–0.10 s |
| `_103223` | 2 | 7 / 0, 0 | 97 ms | 0.1–0.4 / 69–70 ms | 1.29–1.32 s | 0.07–0.08 s |

**Every late drop after `watching` is the replay ending, not the loop
falling behind.** In each, the dropped frame is the second-to-last due frame of
the file (1120 of 1124 on `_102250`, 1188 of 1192 on `_102450`). A probe timing
every grab showed the last ~9 frames arriving within ~15 ms (gaps of 4, 0, 0, 0,
4 ms, against 40 ms before), as the publisher ends. Two due frames in one burst
replace one another. The Looks around them took ~40 ms against the 160 ms
interval. A camera's stream does not end, so this is reported and not counted
(decided 2026-11-02). Apart from it, no due frame was dropped late after
`watching`, and Frame Wait P99 stayed under one Look Time. **The catch-up #291
gives:** the first frame past the baseline is 1.2–1.4 s behind the stream, and
the reader is at the live edge 0.07–0.10 s after the Run goes `watching`.

**Live, `_103223`'s Look Time P99 was 97 ms**, above the bench's 94.6 ms that
set the stride. At 97 ms, stride 4 still leaves 39% spare. The table and the
replays ran on CPU only. MPS was not measured, and on CamB the CPU sets most of
Look Time (`docs/latency_wip.md`).

Every run of a recording reports the same Bullet Holes: 4 on `_102250`, 1 on
`_102450` and 1 on `_103223`. The exception is one `_102450` run, which also
reported a Miss at 69% persistence. Positions differ between runs by up to 2.2 mm,
as each run looks at different frames. The replays were not compared with
file runs of the copies.

**`REANCHOR_AFTER_LOST` (25 looked-at frames) is now about 4 s** at stride 4,
against about 17 s at 17 and 1 s at stride 1. It is unchanged and still
provisional (#80, #84).

**Nothing here is validated either.** It is the same footage the thresholds
were tuned on (ADR-0010: regression, not unseen). It shows that stride 4 does
not visibly break them there.

## The frame rate is load-bearing

The stride is a count of frames, and so are `PERSIST_FRAMES` (25, ~1 s, 50 until #314) and
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
