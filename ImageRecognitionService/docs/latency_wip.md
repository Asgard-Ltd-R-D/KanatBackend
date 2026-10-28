# SOW 2.3.1 latency: a WIP measurement on the development Mac

**Measured 2026-10-14: the recordings at `2300284` (#131), the live replay at `4702c0e` (#132).** Spec #128. **A work-in-progress
measurement on development hardware, not an acceptance result.** SOW 2.3.1 asks for "a latency of less
than 40 ms per frame" and does not say where the 40 ms starts or stops.
Asgard asked IAI to agree the measurement points, the statistic (P99 proposed)
and the target hardware (Asgard-26-37a, sections 2.3.1 and 3.2). IAI has not
answered, so **the 40 ms is undefined.** Every reading of it is reported below
side by side. None is named as the requirement, and nothing is compared with
40 ms as a pass or a fail.

The terms are CONTEXT.md's: a **Look** is the pipeline looking at one frame,
**Inference Time** is a Look's detector calls summed, **Look Time** runs from
the frame in hand until Persistence has judged its Detections, and **Frame
Wait** is live only. All figures are milliseconds unless marked.

## Setup

- **Tree:** `main` at `2300284`. The only untracked files were the
  two architecture-review HTML pages under `docs/`, which the pipeline does not read.
- **Host:** `Ronens-MacBook-Pro.local`, Apple M1 Pro, 16 GB, macOS 27.0.1
  (build 26A434), on mains power with the battery charged.
- **Libraries:** Python 3.14.8, ultralytics 8.4.126, torch 2.13.0, torchvision
  0.28.0, numpy 2.5.2. Decoding: `opencv-python==4.10.0.84`, through its
  bundled FFmpeg (avcodec 60.3.100).
- **Weights:** the default, `kanat_yolo26n_v1`, sha256
  `f7e407c67226062d7ddb0a02e4868a06b3c27d56002255f56786036b43b23e3e`.
- **Everything else** is at its value at `2300284`: confidence 0.40, a 5-frame
  baseline, change filter on, merge off. The image sizes are the ones the pipeline derives. The device is the
  only difference between a recording's two runs.
- **Recordings:** the two spent ones with truth. The pipeline's own gate passed both.
  No Sealed recording was opened (ADR-0005), and `data/sealed_runs.log` is
  unchanged.

  > **Superseded by [ADR-0010](../../docs/adr/0010-every-recording-may-be-opened.md) (#270):** no recording is sealed now, and the log is deleted.
- **Conditions:** one run at a time, on mains power. No other heavy job ran, but desktop apps were open.
  At the start a browser tab was taking about 74% of one core; it had closed before the CamB CPU run
  quoted below. Load averages were 2.0–4.8 across the runs. No idle sleep was logged during any run
  quoted here (`pmset -g log`). Two CamB CPU runs that the Mac slept through were set aside; see
  "Two CamB CPU runs set aside" below.

Each run was timed with `/usr/bin/time -l`. The CamB CPU run quoted was also wrapped in `caffeinate -i`,
which keeps the Mac from idle-sleeping:

```bash
.venv/bin/python -m detection.new_bullet_holes data/videos/CamA_20260914_141546.mkv \
    --start 13 --end 25 --stride 1 --device cpu --timing cama_cpu.csv
.venv/bin/python -m detection.new_bullet_holes data/videos/CamA_20260914_141546.mkv \
    --start 13 --end 25 --stride 1 --device mps --timing cama_mps.csv
caffeinate -i .venv/bin/python -m detection.new_bullet_holes data/videos/CamB_20260915_102250.mkv \
    --start 0 --end 46 --stride 1 --device cpu --timing camb_cpu.csv
.venv/bin/python -m detection.new_bullet_holes data/videos/CamB_20260915_102250.mkv \
    --start 0 --end 46 --stride 1 --device mps --timing camb_mps.csv
```

The CSVs and logs were kept out of the repo. This page quotes them. Each CSV's
first line named the host and the device the detector resolved to: `cpu` or `mps`, as asked.

## Every reading, side by side

P50 / P99. n is 295 Looks on CamA and 1,145 on CamB, or 295 and 4,580 for a single call.

| Reading | CamA CPU | CamA MPS | CamB CPU | CamB MPS |
|---|---:|---:|---:|---:|
| A single detector call | 162.8 / 180.0 | 67.7 / 85.9 | 11.6 / 20.1 | 15.9 / 32.6 |
| Inference Time, a Look's calls summed | 162.8 / 180.0 | 67.7 / 85.9 | 48.6 / 67.0 | 74.6 / 86.9 |
| Look Time, the whole Look | 297.6 / 2896.5 | 201.9 / 2782.9 | 706.1 / 794.3 | 735.7 / 811.5 |
| Look Time, mean | 361 | 263 | 507 | 534 |
| Frame Wait | live only: "Frame Wait on a live replay" below | | | |

At 25 fps a frame arrives every 40 ms. So a fourth reading, keeping pace with
every frame, turns on mean Look Time rather than a percentile. Today the live
pipeline does not try to keep pace with every frame: it looks at every 17th frame (ADR-0007).

## CamA_20260914_141546, 13–25 s, CPU and MPS

n/P50/P95/P99/max. 295 Looks past the baseline, none Lost, 1 detector call each.

| Figure | n | CPU P50 | P95 | P99 | max | MPS P50 | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Inference Time | 295 | 162.8 | 175.5 | 180.0 | 183.9 | 67.7 | 73.6 | 85.9 | 91.5 |
| Look Time | 295 | 297.6 | 403.3 | 2896.5 | 2952.5 | 201.9 | 305.0 | 2782.9 | 2841.0 |
| a detector call | 295 | 162.8 | 175.5 | 180.0 | 183.9 | 67.7 | 73.6 | 85.9 | 91.5 |
| registration | 295 | 108.7 | 214.9 | 2690.2 | 2745.0 | 107.5 | 214.2 | 2674.7 | 2724.6 |
| rectification | 295 | 10.7 | 10.9 | 11.1 | 11.6 | 10.8 | 11.1 | 11.3 | 11.5 |
| detector | 295 | 162.8 | 175.5 | 180.0 | 183.9 | 67.7 | 73.6 | 85.9 | 91.5 |
| baseline strip | 295 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.1 | 0.2 |
| change filter | 295 | 12.0 | 13.1 | 14.6 | 19.9 | 12.0 | 13.1 | 14.3 | 17.3 |
| persistence | 295 | 1.0 | 2.3 | 2.9 | 3.6 | 1.0 | 2.2 | 2.8 | 3.7 |

## CamB_20260915_102250, 0–46 s, CPU and MPS

n/P50/P95/P99/max. 1,145 Looks past the baseline, none Lost, 4 detector calls each.

| Figure | n | CPU P50 | P95 | P99 | max | MPS P50 | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Inference Time | 1145 | 48.6 | 54.9 | 67.0 | 78.9 | 74.6 | 81.8 | 86.9 | 140.3 |
| Look Time | 1145 | 706.1 | 739.8 | 794.3 | 965.8 | 735.7 | 765.8 | 811.5 | 1121.6 |
| a detector call | 4580 | 11.6 | 17.8 | 20.1 | 28.8 | 15.9 | 30.5 | 32.6 | 53.3 |
| registration | 1145 | 655.5 | 683.4 | 738.3 | 911.2 | 658.3 | 684.2 | 729.6 | 1032.6 |
| rectification | 1145 | 1.5 | 1.5 | 1.7 | 2.1 | 1.5 | 1.6 | 1.7 | 4.3 |
| detector | 1145 | 48.7 | 55.1 | 67.1 | 79.1 | 74.7 | 82.0 | 87.1 | 140.5 |
| baseline strip | 1145 | 0.0 | 0.0 | 0.1 | 0.1 | 0.0 | 0.0 | 0.1 | 0.1 |
| change filter | 1145 | 0.8 | 0.8 | 1.0 | 1.2 | 0.8 | 0.9 | 1.0 | 3.1 |
| persistence | 1145 | 0.0 | 0.1 | 0.2 | 0.2 | 0.0 | 0.1 | 0.2 | 0.3 |

The detector stage is Inference Time plus merging the band Detections (#128). That is why it sits
0.1–0.2 above Inference Time on CamB and equals it on CamA, which has no bands.

## Detector calls per Look

| Capture Setup | Calls a Look | Each call: image px → imgsz | CPU P50 | MPS P50 |
|---|---:|---|---:|---:|
| `cama-20260914` | 1 | rectified canvas 1282×1636 → 1632 | 162.8 | 67.7 |
| `camb-20260915-close-one-board` | 4 | margin canvas 321×323 → 320; Board bands past it 391×51, 391×105, 102×374 → 384 each (#46) | 17.4; 8.2, 11.2, 11.9 | 28.1; 15.2, 15.4, 15.6 |

This accounts for the gap in Inference Time between the two setups. CamA makes one call on a large
canvas, and CamB makes four on small ones. On CPU, CamA's one call costs 3.3× CamB's four together. MPS cuts
CamA's call 2.4×, to 68 ms, but each of CamB's small calls is 1.3–1.9× *slower* on MPS than on CPU. So CamB's
Inference Time rises on MPS, from 48.6 to 74.6 at P50, and the device moves the two setups in opposite directions.
The same check before #128, on raw frames, found MPS slightly faster at the band size, 14 ms against 16.5. Through the
pipeline it is not. On CPU, CamB matches HANDOVER's record of #46, where one call of 17–19 ms became four totalling 49–50.

## Bullet Holes, CPU against MPS

On each recording, every CPU and MPS run prints identical output except for the
timing lines and the time to build Board space. That covers the baseline, the residuals, the
filter counts, every Bullet Hole with its times, persistence and frame count,
and the Groups. It holds for all three CamB CPU runs. **No difference between the devices.**

- **CamA:** 6 Bullet Holes reported, all Misses. ADR-0007's stride-1 run also reported 6 (5 TP, 1 FP).
- **CamB:** 5 reported, 3 on Target 1. ADR-0007's stride-1 run reported 5 (4 TP, 1 FP),
  and its false positive, #4 at 30.60 s, is here at the same time.

The counts are compared, not rescored: `evaluate.py` was not run.

## What dominates Look Time: registration, and inside it the ECC solve

Share of summed Look Time:

| Run | registration | detector | rectification, baseline strip, change filter, persistence together |
|---|---:|---:|---:|
| CamA CPU | 47.8% | 45.6% | 6.7% |
| CamA MPS | 65.1% | 25.8% | 9.1% |
| CamB CPU | 89.8% | 9.8% | 0.5% |
| CamB MPS | 85.4% | 14.1% | 0.4% |

The device moves only the detector. Registration's distribution is the same on CPU and MPS: P50 108 against 108
on CamA, and 656 against 658 on CamB. Registration runs on OpenCV on the CPU whatever `--device` says.

**Inside registration.** A scratch probe, not committed, ran `process` through the same loop, gate first,
on CamA 13–25 s (all of its window) and CamB 0–10 s (245 Looks). It wrapped timers around `Registration.register` and
the calls it makes: `board.find_targets`, `board.ecc_warp`, `cv2.findTransformECC`, `board.uncovered_view` and
`board.silhouette_disagreement`. `cv2.findTransformECC`, the ECC solve against the baseline frame (#50),
was 94% of registration time on CamA and 98% on CamB's first 10 s. Finding the Targets took about 4 ms a Look.
The timer around the gross-fit silhouette check (#110) never fired, and no run was due a re-anchor
("0 re-anchor attempt(s)"). So neither accounts for the time below.

**CamA's spikes.** 6 Looks of 295 (2%) spend 2.66–2.75 s in registration, where the P50 is 108 ms. They
fall on the same frames on both devices and in the probe: 13.20, 13.32, 20.80, 21.36, 21.44 and 24.84 s (frames
5, 8, 195, 209, 211, 296 from `--start`). Those six Looks are CamA's whole Look Time P99. Without them,
Look Time is P50 296 / P99 466 / max 481 on CPU and 201 / 372 / 391 on MPS. In the probe, 99.6% of each spike's
time is inside `findTransformECC`. Why the solve takes about 25× longer on these frames is **not established**.
This is the pre-spec probe's 2.7 s registration P99 (#128), now located but not explained.

**CamB's two modes.** Registration on CamB is bimodal, frame by frame. 29% of Looks register in under
100 ms, 61% take 600–700 ms, about 3% exceed 700 and 7% fall between. Every frame lands in the same mode
on all the CamB runs, CPU and MPS. With the cut at 300 ms, one frame sits on it, at 277–303 ms. The ECC solve is
inside both modes. The slow mode puts CamB's Look Time P50 (706 / 736) well above its mean (507 / 534).
Why a frame lands in one mode or the other is **not established**. The MPS run's maximum, a 1.03 s
registration at 36.52 s (frame 913), took 667 ms at that frame on CPU. Its cause is not established either.

**Two CamB CPU runs set aside.** The Mac idle-slept through the first two CPU runs of CamB, which
macOS's power log records at 11:08:20–11:12:16 and 11:42:45–11:47:50. The Look clock (`time.perf_counter`)
does not count a sleep, but wall time does. Each run's wall time exceeded its summed Look Time by 239 s and 309 s,
where the quoted runs show 4–8 s for everything outside the timed Looks (step 5 of "Re-measuring on another host"). Each also had its only multi-second Look at the moment of the sleep:
registration 4.65 s at frame 689 and 4.24 s at frame 56. The CPU figures above come from a third run under `caffeinate -i`,
with no sleep logged, 6.5 s outside its Looks and a worst registration of 911 ms. The two set-aside runs agree
with it up to P99: Look Time P50 703.0 and 702.4 against 706.1, P99 825.1 and 784.8 against 794.3. All three
report the same Bullet Holes.

## The stride

The spec assumes Look Time does not depend on the stride, because each Look registers against the baseline frame (#50).
One extra run checked this, on CPU, between the sleeps:

```bash
.venv/bin/python -m detection.new_bullet_holes data/videos/CamB_20260915_102250.mkv \
    --start 0 --end 46 --stride 17 --device cpu --timing camb_cpu_s17.csv
```

It gave n 67 Looks: Look Time P50 691.2, mean 495, max 724.2, and registration P50 641.8. These fall within
the stride-1 runs' distribution, and the run reports the same 5 Bullet Holes. With n 67, its tail is not read.

What this means for the live stride: stride 17 at 25 fps looks at a frame every 680 ms. 61–64% of CamB's
Looks take longer than that, while their mean (495–534) does not. ADR-0007 found 449–488 ms a Look on
CamB at `1d18891`, by differencing wall times, which also counts reading and decoding. These means are higher,
and the gap is not reconciled here. How a live run behaves when most of its Looks overrun the stride interval
is for #132's replay to measure, as Frame Wait and frames dropped late. It is below.

## Frame Wait on a live replay (#132)

**Measured 2026-10-14 at `4702c0e`, on the host and libraries in "Setup".** A WIP measurement on
development hardware, not an acceptance result, and the 40 ms is still undefined. A recording cannot show
Frame Wait, so this is one replay through VideoService's MediaMTX, the path a camera will use.

**What Frame Wait is not.** Frame Wait runs from the reader having a due frame decoded to the loop taking
it: the wait inside the system, and nothing else. It does not include FFmpeg's buffering ahead of the
decoder (about 1.2 s at open, #85), how far the reader runs behind the stream, MediaMTX, the network or the
camera. Those are end-to-end latency (SOW 2.3.4), which is not measured here. A small Frame Wait is not a
small delay from the camera.

**The replay** followed [`live_camera.md`](live_camera.md)'s procedure (#85), steps 1–4:

- **The copy:** step 1's command, on the spent `CamB_20260915_102250.mkv` (sha256 `ed4c3afd…`), made with
  ffmpeg 9.0.2 (Homebrew 9.0.2_1) and libx264 r3222. 1,150 frames, H.264 Main, 1920×1080, 25 fps, GOP 25. The copy
  is spent too, and is not committed. No Sealed recording was opened (ADR-0005), and
  `data/sealed_runs.log` is unchanged.

  > **Superseded by [ADR-0010](../../docs/adr/0010-every-recording-may-be-opened.md) (#270):** no recording is sealed now, and the log is deleted.
- **MediaMTX** v1.21.1 (darwin arm64), started in `VideoService/` with `mediamtx.yml` unchanged. The
  `replay` path was added through the Control API and published on demand by `ffmpeg -re … -c copy`.
- **The run,** at the live stride (17), kept awake with `caffeinate -i`. No sleep was logged. It was stopped
  with SIGINT when it logged `[LIVE] stream dropped` at the end of the file:

  ```bash
  .venv/bin/python -m detection.new_bullet_holes rtsp://127.0.0.1:8554/replay \
      --mm-per-px 0.1763 --device mps --timing live_mps.csv
  ```
- **Where it joined:** file frame 25 (1.0 s), the first keyframe after it connected. Its `[BOARD]` line (ECC
  0.9403, the same canvas and bands) and every Bullet Hole's first-seen time match a file run of the copy
  from 1.0 s at the same stride. Frames were not hashed. Frame numbers below are the live run's indices, and
  file frame = index + 25.
- **The file run** is step 4's `process` call on the copy, with `device="mps"` and a timing path. It is
  the reference below.

### Frame Wait, with and without frame 17

| Frame Wait | n | P50 | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|
| every row past the baseline, as the run printed it | 61 | 0.1 | 176.5 | 458.9 | 827.8 |
| without frame 17, decoded while the reader blocked for the baseline | 60 | 0.1 | 161.5 | 213.0 | 213.0 |

Neither row includes FFmpeg's buffering, the reader's lag, MediaMTX, the network or the camera (above).

**One row carries the baseline's blocking: frame 17, the first past the baseline, 827.8 ms.** Until the
baseline is built, the reader blocks instead of dropping (#83), so frame 17 waited out the baseline's last
Looks. It is the run's max and, with n 61, sets its P99. The reader was holding one more such frame, 34. Frame 51
replaced it while frame 17 was looked at, so it was dropped late and has no row.

**Did Frame Wait stay within about one Look Time?**

- **Every row: no, because of frame 17, measured against the run's typical Look.** Its 827.8 ms is 5.3× the
  run's Look Time P50 (155.5). Against the run's longest Look Time (806.4), it is 21.4 ms (3%) over, so about one
  slow Look. The Looks it waited out were the baseline's, which are not timed.
- **Without frame 17: yes.** The longest wait was 213.0 ms. No frame waited more than 0.43 of the Look before
  it, the Look it arrived during. 40 of the 60 waited under 1 ms, because the loop was already waiting for
  them. Of the other 20, all but frame 85, the first after the reader caught up, followed a Look longer than
  the 680 ms stride interval. Slow Looks in a row add up: frames 272, 289 and 306 waited 102.6, 160.7 and
  213.0 ms. A due frame is dropped late only when a newer one arrives first, which needs a wait of 680 ms. No
  frame came near that.

### The same run's Look Time and Inference Time

n/P50/P95/P99/max, live and in the file run, both on MPS.

| Figure | n | live P50 | P95 | P99 | max | file run n | P50 | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Inference Time | 61 | 85.0 | 100.3 | 106.5 | 107.0 | 66 | 76.5 | 83.9 | 86.3 | 87.2 |
| Look Time | 61 | 155.5 | 776.0 | 791.5 | 806.4 | 66 | 142.0 | 756.1 | 784.6 | 801.3 |
| a detector call | 244 | 21.2 | 32.9 | 38.0 | 46.9 | 264 | 16.3 | 31.8 | 35.2 | 38.2 |
| registration | 61 | 65.1 | 675.7 | 694.6 | 697.0 | 66 | 61.7 | 674.2 | 703.5 | 726.8 |

None of the 61 Looks was Lost, and each made 4 detector calls. Every other stage stayed under 2.1 ms. Inference Time
ran 11% higher live at P50, and why is not established.

**These Looks are not comparable with the CamB tables above.** Their baseline is file frame 25 of the H.264
copy, not frame 0 of the recording. On the copy from 1.0 s, 22 of 66 Looks took longer than 680 ms, against 61–64%
of CamB's from 0 s. Look Time's P50 is 142.0, against 691.2 for the stride-17 run from 0 s. The two runs differ in the
baseline frame, the re-encode and the device (MPS against CPU), and the device did not move registration in #131.
Which of the other two moves it is not established.

### Frames dropped late, frames lost upstream, and MediaMTX

From the run's `[LIVE]` report:

- **66 frames looked at:** the 5 of the baseline and 61 Looks past it. The file run made 71. The 5 fewer are the 3
  late drops, the 1 due frame lost upstream, and the 1 due frame (1122) held when the run was stopped.
- **3 due frames dropped late:** 34, 51 and 68. All three fell during frame 17's Look, while the reader caught up on
  the stream the baseline had held it behind. None was dropped after that, though 20 of the 61 Looks overran the
  680 ms stride interval: each overrun delayed the next frame's Look instead. That answers part of the question
  in "The stride" above. Only a third of the Looks overran here, against 61–64% of CamB's from 0 s, so this replay
  does not show a run where most of them do.
- **Frames lost upstream:** 1 gap of 16 frames (0.6 s of stream, frames 93–108 by the timestamps), 1 of them due (102).
  No frame was untimed. The timestamps stepped at 25.00 fps, and frames were received at 24.64 fps over 45.0 s.
- **A frame that may have decoded corrupt:** `[h264] error while decoding MB 81 56` printed right after the
  baseline. Frames after a gap decode corrupt up to the next keyframe (#117), and frame 119 (file frame 144)
  falls in that window. It was not hashed, so whether it decoded corrupt is not established.
- **Drops:** 1, the end of the file.

**MediaMTX's log for the run** has one discard: `reader is too slow, discarding 471 frames` at 14:05:54, for the
pipeline's session, in the second the baseline was built in (it finished at 14:05:54.8; MediaMTX logs whole seconds). MediaMTX counts RTP packets here,
and at #117's 27–28 packets a frame, 471 is about 17 frames, against the 16 the run reported lost. This is #117's
start-up loss, counted and not prevented (HANDOVER).

### Bullet Holes against #85's replay

| Bullet Hole | #85's run 1, 2026-10-07 | this live run | the copy's file run from 1.0 s |
|---|---|---|---|
| #1 | Miss | Miss | Miss |
| #2 | 7 at +21.0/+65.7 mm | 7 at +21.2/+66.0 | 7 at +21.2/+66.0 |
| #3 | 8 at −26.7/−35.8 | 8 at −29.1/−36.5 | 8 at −27.9/−36.3 |
| #4 | 8 at −21.5/−35.7 | 8 at −22.8/−35.8 | 8 at −22.8/−36.0 |
| #5 | Miss | Miss | Miss |

All three runs report the same 5 Bullet Holes, with the same Targets and scores. Live, each Bullet Hole's first-seen time
matches the file run's to 0.01 s: 1.68, 29.56, 30.92, 30.92 and 31.60 s. **The positions differ by up to 2.4 mm.** The
differences are reported here, not tuned away.

- **From #85, up to 1.3 mm comes from the copy.** #85's merge commit, `4a41652`, run on today's copy gives today's file
  run exactly. It was run on CPU, as #85's run was, and today's file run is identical on CPU and MPS. So neither the
  code since #85 nor the device moved them. The copy was made with the same command, but this host's ffmpeg is 9.0.2_1,
  installed 2026-10-11, after #85's replay. Whether that is why the copy differs is not established.
- **The live path moves #3 by 1.2 mm more.** #85's and #117's replays matched their file runs within 0.1 mm, and this
  one does not. #3 is 1.2 mm off in X. #4 is seen in 18 Looks live, to 43.84 s, and in only 12 in the file run, to
  38.40 s. The live run did not look at 34, 51, 68 or 102, and 119 may have decoded corrupt. 7 of the 61 frames both
  runs looked at took over 600 ms to register in one run and under 220 ms in the other. Frame 136, for example, took
  31 ms live and 673 ms in the file run, and four of the 7 come after frame 400. #131 found every frame in the same mode
  across its runs, which all looked at the same frames. Each Look registers against the baseline frame (#50), but its
  search is seeded from the Look before's fit (`board.track_view`), so the earlier frames looked at may move later fits.
  That is not established. Frame 119 may have decoded corrupt, and 136 is seeded from it. No frame was hashed. For
  Target 1's Group, live MPI is −10.2/−2.1 mm, CEP 39.2 mm and Extreme Spread 114.2 mm. The file run gives −9.8/−2.1,
  38.7 and 113.5.

## Re-measuring on another host

1. Check out the commit and build `.venv` from `requirements.txt` on Python 3.14. That file pins only
   ultralytics and OpenCV, so pin the rest of "Setup"'s versions too:
   `pip install torch==2.13.0 torchvision==0.28.0 numpy==2.5.2`. On a CUDA host, install the CUDA build of
   the same torch. If a version cannot be matched, record the one used: a library change moves the
   figures as much as a host does. Put the default weights at
   `trained_models/kanat_yolo26n_v1/weights/best.pt` and check their sha256. Copy the two recordings
   byte for byte into `data/videos/`: the gate identifies a recording by its content hash and refuses
   one that `config/recordings.json` does not list.
2. On mains power, with nothing else heavy running and the host kept from sleeping (`caffeinate -i` on
   macOS), make the four runs above one at a time. Use `--device cpu` and then the host's accelerator: `mps`
   on Apple silicon, or a CUDA index such as `--device 0` on NVIDIA. Name the device explicitly: without the
   flag, ultralytics picks CUDA if there is one. Registration, rectification and the filters run on the CPU
   whatever the flag says, and on CamB the CPU sets most of Look Time.
3. Read each run's `[TIMING]` lines. Its CSV's first line names the host, the platform and the device.
4. Diff each recording's two outputs, leaving out the `[TIMING]` lines and the Board-space build line. A
   difference in Bullet Holes is reported, never tuned away.
5. Time each run, for example with `/usr/bin/time`, and compare its wall time with the sum of the
   CSV's `look_ms`. The gap is all the run's work outside the timed Looks past the baseline. That includes
   hashing the whole recording at the gate, loading the model, building Board space, the baseline's Looks,
   reading and decoding every frame, and the end-of-run report. It was 4–8 s here. A larger recording,
   slower storage or decoding, or costlier baseline frames all make it larger. So a
   gap well above the host's other runs is a reason to check its power log (`pmset -g log` on macOS) for a
   sleep. It is not proof on its own: set a run aside only when a sleep is logged inside it, as both runs
   set aside on this page were.
6. Record the commit, date, host, chip, OS and library versions, as in "Setup" above.
7. Frame Wait needs a live stream: replay as in "Frame Wait on a live replay" above, by
   [`live_camera.md`](live_camera.md)'s procedure. Read the CSV skipping every `#` line: a live one has two.

## Open questions for IAI

1. **What does the 40 ms measure?** Where does it start and where does it stop? The candidates measured here are:
   - one detector call
   - Inference Time, all of a frame's detector calls
   - Look Time, everything a Look does from the frame in hand to persistence judged
   - keeping pace with a 25 fps stream, one frame every 40 ms

   End-to-end latency from the camera to the operator's screen is a fifth reading. SOW 2.3.4 covers it, and it is not measured here.
2. **Which statistic?** Asgard proposed P99. Every figure here has n, P50, P95, P99 and max.
3. **On what hardware?** These figures come from the development Mac, on its CPU and on its GPU (MPS). The
   target host decides both kinds of figure: its accelerator moves the detector, and its CPU moves registration.
4. **Clock sync with IAI's telemetry.** The SOW's reason for the 40 ms is clock skew against
   telemetry. Today nothing shares a clock. A live frame's time is the detection host's clock plus
   the stream's offset, and IAI telemetry is fetched by Event ID (#105, #108, #109). Which clock should be shared,
   and over NTP or PTP?

## Not here

- **End-to-end latency** (SOW 2.3.4): FFmpeg's buffering, the reader's lag, MediaMTX, the network and the camera.
- **Any optimisation**, any changed threshold, or MPS as the default device (#128, out of scope). The
  default device is unchanged.
