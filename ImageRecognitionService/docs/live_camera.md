# The AXIS Q6315-LE through the video service

**Issue #85.** This page covers how the production camera reaches the pipeline, the stream settings selected for it, and the rule that keeps its view fixed for a Range. It also covers the manual acceptance. The replay half of the acceptance ran on 2026-10-07 and is recorded at the end. The camera half is **blocked, waiting for the physical camera**.

Credentials never go in this file, in an issue, or on a pipeline command line. `<user>`, `<password>`, `<camera-ip>`, `<mtx-host>` and `<alias>` are placeholders.

## The path

```
AXIS Q6315-LE ──RTSP/TCP :554──▶ VideoService MediaMTX, path <alias> ──rtsp://<mtx-host>:8554/<alias>──▶ new_bullet_holes
                                              └──WebRTC (WHEP) :8889──▶ KanatFrontend operator view
```

The MediaMTX is `VideoService/`'s, and nothing in it changes:

- **Config.** `mediamtx.yml` as checked in. Reading needs no credentials.
- **Start.** `python composer.py up <env> --mediamtx` runs the `mediamtx` binary placed next to `mediamtx.yml`, with `VideoService/` as the working directory. Composer starts the Docker stack first; on a host without Docker, running `./mediamtx` from `VideoService/` starts the same MediaMTX.
- **Paths.** Camera paths are added at runtime through the Control API, the way KanatFrontend provisions cameras. They are not written back to `mediamtx.yml`, so they are gone when MediaMTX restarts.

### Add the camera: RTSP pull, the acceptance path

MediaMTX holds the camera connection and reconnects it itself.

The account is never typed into the URL or the JSON by hand:
- **Percent-encoded.** A reserved character in the user name or password (`@ : / ? # %`, for example) would otherwise change what the URL means.
- **Serialised by `json.dumps`.** A quote or backslash would otherwise break the request body.
- **Prompted for.** It stays out of shell history, and `curl` reads the body on stdin, so the account is not on any command line.

```bash
read -r -p 'AXIS viewer user: ' AXIS_USER; read -r -s -p 'AXIS viewer password: ' AXIS_PASS; echo
AXIS_USER=$AXIS_USER AXIS_PASS=$AXIS_PASS python3 -c '
import json, os, sys
from urllib.parse import quote
user, password = (quote(os.environ[k], safe="") for k in ("AXIS_USER", "AXIS_PASS"))
print(json.dumps({"source": f"rtsp://{user}:{password}@{sys.argv[1]}:554/axis-media/media.amp"
                            "?videocodec=h264&resolution=1920x1080&fps=25&videozfpsmode=fixed"
                            "&videozgopmode=fixed&videokeyframeinterval=25",
                  "rtspTransport": "tcp", "sourceOnDemand": False}))' '<camera-ip>' |
curl -X POST http://<mtx-host>:9997/v3/config/paths/add/<alias> \
  -H 'Content-Type: application/json' --data-binary @-
unset AXIS_USER AXIS_PASS
```

MediaMTX decodes the percent-encoding before it authenticates. This was checked on v1.21.1 against a stand-in RTSP server that requires user `view@er`, password `p#ss@x&y`. The encoded source went ready, and the stand-in refused no credentials or wrong ones with 401. The same source unencoded was rejected with a 400, and that error echoes the URL, password and all, back to the caller.

Check the path before running anything on it:

```bash
curl http://<mtx-host>:9997/v3/paths/list        # <alias> is listed with "ready": true
ffprobe -v error -rtsp_transport tcp -select_streams v:0 \
  -show_entries stream=codec_name,profile,width,height,r_frame_rate,has_b_frames \
  rtsp://<mtx-host>:8554/<alias>                   # h264, 1920, 1080, 25/1
# Keyframes over 10 s: consecutive times 1.000 apart (GOP 25 at 25 fps)
ffprobe -v error -rtsp_transport tcp -read_intervals %+10 -select_streams v:0 \
  -skip_frame nokey -show_entries frame=pts_time -of csv=p=0 rtsp://<mtx-host>:8554/<alias>
```

To remove the path, run `curl -X DELETE http://<mtx-host>:9997/v3/config/paths/delete/<alias>`. On MediaMTX v1.21.1 a delete must use DELETE: a POST gets a 404.

### Or: multicast through the existing ingest

The site may distribute the camera as H.264 RTP multicast. In that case its KanatFrontend camera entry (alias, multicast group and port, NIC) creates a path that `run_record.sh` feeds, and the pipeline reads the same `rtsp://<mtx-host>:8554/<alias>`.

The stream settings below must then be set on the camera itself, or by whoever starts the multicast, because there is no URL of ours to carry them. A multicast that goes silent need not close the RTSP session. The pipeline's read timeout (`STREAM_TIMEOUT_MS`, #84) turns that silence into a drop.

## Camera settings

The capabilities come from the Q6315-LE datasheet and VAPIX. The URL arguments were checked on 2026-10-07 against Axis's VAPIX URL options (developer.axis.com, *Parameter management for video channels*, "URL options").

| | Q6315-LE | Selected | Why |
|---|---|---|---|
| Codec | H.264 (Baseline/Main/High), H.265 (Main), Motion JPEG | H.264, `videocodec=h264` | The video service's multicast ingest is H.264 only. Most browsers cannot decode H.265, and the WebRTC operator view runs in one. A reader joining H.264 mid-GOP gets its first frame at the next IDR, decoded clean (measured below). |
| Resolution | 1920x1080 down to 320x180 | `resolution=1920x1080` | Full resolution, the same as the truth recordings. |
| Frame rate | up to 50 fps (50 Hz variant) or 60 fps (60 Hz variant), at all resolutions | constant 25 fps, `fps=25` | `PERSIST_FRAMES`, `BASELINE_FRAMES` and `LIVE_STRIDE` are frame counts set at 25 fps (ADR-0007). |
| Zipstream dynamic FPS | available, off by default | off, `videozfpsmode=fixed` | Dynamic FPS lowers the frame rate when the scene is still, and a Board between Hits is exactly that. |
| Zipstream dynamic GOP | available, off by default | off, `videozgopmode=fixed` | VAPIX says `fixed` means "the product's default GOP length", so the keyframe check above is what confirms 25. |
| GOP | configurable | 25 frames, `videokeyframeinterval=25` | After a (re)connect, the first decodable frame is at most 1 s away. |
| Transport | RTSP on :554, RTP/RTCP, RTSPS/SRTP, multicast (IGMP v1–v3) | RTSP over TCP, `"rtspTransport": "tcp"` | A lost UDP packet corrupts frames the detector would then see. |
| Authentication | no default account; digest | a dedicated viewer-only account | Its credentials live only in the path's `source`. |
| ONVIF | Profiles G, M, S and T | not used | The VAPIX RTSP URL is fixed and documented; there is nothing to discover. |
| Low latency mode | available | not required | Latency (SOW 2.3.4) is out of scope. |

The URL does not set Zipstream strength (`videozstrength`), compression or bitrate mode, so the camera's own settings apply. Every frame the pipeline has seen came from the truth recordings' recorder. Whether Zipstream's detail reduction affects a small Bullet Hole is untested (see "To confirm" below).

## Fixed view during a Range

Registration anchors to the Range's baseline frame, and Board space is built once, at the start of the Range. #80's re-anchoring recovers a Board lost for a while against that same baseline; it cannot recover a different view. So the camera holds one PTZ position for the whole Range:

- One preset, chosen before the Range starts, with zoom and focus held there. No operator PTZ during the Range.
- No guard tour, autotracking, gatekeeper or motion-triggered preset on this camera during a Range: each of them moves the view on its own.
- No mid-Range change to settings that change the image geometry: zoom, EIS, rotation, capture mode.
- Day mode held. The pipeline has only seen colour daylight footage, and a switch to night mode (IR, black and white) is untested.

A move mid-Range invalidates the Range. Moving to another preset starts a new Range with its own baseline and Board space. PTZ control and detecting PTZ movement are out of scope; the SOW requires neither.

## Running the pipeline on the camera

```bash
cd ImageRecognitionService
.venv/bin/python -m detection.new_bullet_holes rtsp://<mtx-host>:8554/<alias> --mm-per-px <scale>
```

- **Stride.** `LIVE_STRIDE` (17) unless `--stride` gives another.
- **Print scale.** A stream has no Capture Setup on record, so the print scale comes from `--mm-per-px` only. Measure it for the printed Target in use (`docs/ring_measurement.md`). Without it, positions stay in Board px.
- **Stopping.** Ctrl-C or SIGTERM ends the run and prints the report.

Each drop is logged when it starts, and again when the stream is back with that drop's duration (`[LIVE] stream back at … after X s without a frame`). Those lines are the per-drop durations #78 asks for. Frames lost upstream are logged when found, by the stream's timestamps (`[LIVE] N frame(s) lost upstream, X s of stream before …`, #117). Before the Bullet Hole report, four `[LIVE]` lines give the totals:

```
[LIVE] configured 25 fps; by the stream's timestamps, frames step at F fps, and were received at R fps over T s of stream. ...
[LIVE] L frame(s) looked at; D due frame(s) dropped: the loop was too late for them, ...
[LIVE] K drop(s), S s down in all, M frame(s) missed ...
[LIVE] G gap(s) upstream, U frame(s) lost, V of them due a look; W frame(s) untimed ...
```

**The rate comes from the stream's timestamps** (`CAP_PROP_POS_MSEC`, #117), not from when frames were read, so FFmpeg's buffering at `open` no longer inflates it. F is the commonest step between consecutive timestamps: the rate the camera sends at, which is "measured 25 fps". R is the frames received over the stream time they span, so it falls short of F by any frames lost upstream. Both read 25.00 fps on the replay with nothing lost; R read 21.33 fps with 165 frames lost. W counts frames whose timestamp was not later than the frame before's. Each was indexed one past the frame before, as was each frame after it until a timestamp advanced again, and later frames were indexed from that one. A backend with no usable timestamps therefore counts frames as read. The run then prints `[WARN] the stream's timestamps never advanced: no timestamp-based indexing`, and the first line reports the wall-clock arrival rate instead (`frames arrived at R fps by the wall clock`), which reads high on a short run by FFmpeg's ~1.2 s of buffering at `open`. Indices are counted from the timestamps at the configured 25 fps, for gap accounting (ADR-0007). Another frame rate is unsupported: below 25 fps every frame interval the stream skips would be logged as a gap, and persistence and the stride would count stream time rather than frames. ffprobe's `r_frame_rate` and the keyframe spacing are the other two readings.

## Manual acceptance

### 1. Replay of a spent recording: done 2026-10-07

1. **Make an H.264 copy of the spent `CamB_20260915_102250.mkv`, with the camera's stream settings.** The recording itself cannot be replayed, because it is MPEG-4 Part 2 (FMP4).
   - A reader that joins MPEG-4 Part 2 mid-GOP gets a first frame decoded off a missing reference (`[mpeg4] warning: first frame is no keyframe`). `open` cannot find the Board on that frame, and the run exits.
   - An H.264 reader gets nothing until the next IDR.

   The copy is of a spent recording, so it is spent too (ADR-0005). It is not in the manifest and is not committed.
   ```bash
   ffmpeg -i data/videos/CamB_20260915_102250.mkv -map 0:v -c:v libx264 -preset medium \
     -profile:v main -bf 0 -g 25 -keyint_min 25 -sc_threshold 0 -b:v 8M -maxrate 8M -bufsize 8M \
     replay.h264.mkv
   ```
2. **Publish it on demand** on the video service's MediaMTX, the way its `loopdemo` path starts its publisher:
   ```bash
   curl -X POST http://127.0.0.1:9997/v3/config/paths/add/replay \
     -H 'Content-Type: application/json' \
     -d '{"source": "publisher", "runOnDemand": "ffmpeg -re -i <absolute path>/replay.h264.mkv -map 0:v:0 -c copy -rtsp_transport tcp -f rtsp rtsp://127.0.0.1:$RTSP_PORT/$MTX_PATH"}'
   ```
   With `-c copy` the live frames are the file's own frames, so any difference from a file run comes from the live path.
3. **Run live** on `rtsp://127.0.0.1:8554/replay` with `--mm-per-px 0.1763`. Stop the run when it logs `[LIVE] stream dropped`: the publisher has reached the end of the file.
4. **File-run the copy** at the same stride, from the frame the live run started on. That is the first IDR after the reader joined. With nothing else reading the path it was file frame 25 (1.0 s) in both runs that started the publisher; the record below identified it by hashing frames. The copy is not in the manifest, so the CLI refuses it; call `process` directly. **Only ever on a copy of a spent recording:** the gate cannot trace a copy to its source, so check the source's role in `config/recordings.json` first (`_102250` is sha256 `ed4c3afd…`, spent).
   ```bash
   .venv/bin/python -c "from detection import new_bullet_holes as n; \
     n.process('replay.h264.mkv', 1.0, 46, n.DEFAULT_MODEL, mm_per_tpl_px=0.1763, stride=17)"
   ```
5. **Compare** the Bullet Holes, their positions, and the number of looks: live, the `[LIVE] … frame(s) looked at` line; in the file run, the `[REGISTRATION] … of N converged fit(s)` count plus 1 for frame 0, plus any Board-lost frames. The only allowed differences are the counted late drops and the one due frame held when the stream ended.

The results are recorded below and were posted to #78.

### 2. The camera: blocked, waiting for the physical AXIS Q6315-LE

**To confirm before the camera run:**
- **The 50 Hz or 60 Hz variant.** On a 60 Hz unit, 25 fps does not divide the capture rate, so frames would arrive unevenly spaced. If 25 fps cannot be held, #82's stop condition applies.
- **How the site delivers the camera to the video service:** RTSP pull (above), or multicast through the existing KanatFrontend camera entry.
- **Whether another consumer**, such as the customer's VMS, already uses the camera's default stream or its multicast. The selected settings must not disturb it.
- **The camera's Zipstream strength.** Note it. If Bullet Holes are missed on camera footage, `videozstrength=off` is the first thing to rule out.

**Steps.** Each one is blocked until the camera is available:

1. **Measured 25 fps.** With the camera at a fixed preset looking at a Board, add the path. Then check it: `ready` in the path list, and ffprobe showing H.264 at 1920x1080, `r_frame_rate` 25/1, and keyframes 1.000 s apart.
2. **The real AXIS → MediaMTX → pipeline path.** Run the pipeline live on `rtsp://<mtx-host>:8554/<alias>` for at least 10 minutes. Keep MediaMTX's log.
3. **WebRTC running at the same time.** Keep the operator's WebRTC view of the same path open for the whole run: KanatFrontend, or `http://<mtx-host>:8889/<alias>`.
4. **A forced drop, recovered.** Pull the camera's network cable for about 10 s, or `DELETE` the path and re-add it. Watch for `[LIVE] stream dropped`, the reopen attempts, and `[LIVE] stream back … N frame(s) missed`. Registration resumes in the same Board space (#84); note any Board-lost frames after it.
5. **Registration when the camera moves during an outage (#118).** Photograph the Board before the run and after it, as for the truth recordings (`tools.derive_truth`), and decide the footage's role (below) before comparing anything with that truth. Drop the stream again, and move the PTZ while it is down. Do this last, because the fixed-view rule says it invalidates the Range. Then check two things. Does the first fit after the reconnect fall into #110's check, and is it rejected (`[REGISTRATION] … checked`, `[WARN] silhouette disagreement`)? Do Bullet Hole positions after the reconnect still match the photographed truth?
6. **#117 on the camera.** Look in MediaMTX's log for `reader is too slow, discarding` against the pipeline's RTSP session in the first seconds of the run. Check it against the pipeline's `[LIVE] … frame(s) lost upstream` lines: at 8 Mbit/s, about 27 discarded RTP packets make a frame. A discard smaller than a frame shows no gap. Look in the pipeline's output for `[h264 …] error while decoding`. Record how long the baseline took on that host: `[REGISTRATION] Board space built in`, and the time from frame 0 (named in `[INFO] baseline … from`) to that line printing, read by timestamping the output (for example `| ts` from moreutils).
7. **Post the report to #78:** stride, configured and measured frame rate, frames looked at, late drops, drops with their durations, and Bullet Holes. Post the observations for #117 and #118 on those issues. Then #85 closes.

Footage from this camera is a new Capture Setup. Its role under ADR-0005 (spent, threshold-work or sealed) is decided before anyone scores it. Recording the Range with the video service (`record: true` on the path) waits for that decision, and acceptance does not need a recording.

**Security.** The Control API (:9997, on all interfaces) is unauthenticated, and it returns a path's `source` with the camera credentials in clear (#89). For acceptance, use the viewer-only camera account and keep :9997 off untrusted networks. Fixing it is not part of #85; it is tracked in #89. The pipeline's URL carries no credentials, because reading from MediaMTX is anonymous, and `_redacted` keeps any URL credentials out of its output.

## The replay, 2026-10-07

**Environment:** MediaMTX v1.21.1 (darwin arm64, checksum-verified release) with `VideoService/mediamtx.yml` unchanged, ffmpeg 9.0.2, `opencv-python` 4.10.0, on the development Mac. The copy is 1150 frames, H.264 Main, 1920x1080, 25 fps, GOP 25, no B-frames, 8.0 Mbit/s. Only the spent `_102250` and this copy of it were streamed.

**Instrumentation.** The live runs were instrumented by a scratch wrapper, not committed. The wrapper logged the stream timestamp (`CAP_PROP_POS_MSEC`) of every frame grabbed. It also hashed every frame decoded against the copy's own 1150 decoded frames, which are all distinct. A match names the frame and shows it decoded clean.

**The copy against the original.** At stride 17 from 0 s, the H.264 copy's file run gives the original `.mkv`'s 5 Bullet Holes, with the same Targets, scores and first-seen times. Positions are within 3 mm, and the Extreme Spread is 113.0 mm against 109.0 mm. The 8 Mbit/s encode moves positions by a few millimetres and changes nothing else.

**The live result matches the file run at the same stride.** Each live run is compared with a file run of the copy from the live run's first frame:

| Run | Live from | Bullet Holes, live and file | Looks, live and file | Late drops | Drops |
|---|---|---|---|---|---|
| 1, stride 17 | file frame 25 | 5 and 5: MISS; 7 at +21.0/+65.7 mm; 8 at −26.7/−35.8; 8 at −21.5/−35.7; MISS. Every position within 0.1 mm | 68 and 71 | 2 | the end of the file |
| 2, stride 17, joined a running stream, forced drop | file frame 125 | 4 and 4: the same, less the Miss first seen at 1.7–2.0 s, which is in this run's baseline. Positions within 0.1 mm | 49 and 65 | 4 | the forced drop, plus the end of the file |
| 3, stride 5 | file frame 25 | 5 and 5: the same as run 1. Positions within 0.1 mm | 111 and 229 | 117 | the end of the file |

- **Run 1.** Looks are file frames 25 + index, so they are the file run's own frames. The 3 looks fewer are the 2 late drops plus the due frame held when the publisher ended. The MPI, CEP and Extreme Spread match to 0.1 mm.
- **Run 2.** The 16 looks fewer are 4 late drops, the 11 due frames the drop's content gap held, and the 1 held at the end. The pipeline's own count of due frames missed was 13; see the missed count below. Before the drop, looks were file frames 125 + index, the same as the file run's. Run 2 is compared with a file run from 5.0 s.
- **Run 3.** It stresses the count: 229 frames were due in indices 0–1124, and 111 looked at + 117 late + 1 held = 229. Half the due frames were dropped late, and the result is still the file run's.
- **Clean frames.** In all three runs, every frame looked at hash-matched the file: none was decoded corrupt.
- **Persistence filters less live.** Before the change filter, runs 2 and 3 had 1–2 more persistent candidates than their file runs: 5 against 4, and 8 against 6. A late drop or a drop gap leaves fewer looks in a window, so one Detection goes further. The change filter removed every extra one. This is ADR-0007's "persistence filters less, and the change filter does more", made stronger by late drops.

**The forced drop (run 2) recovered:**
- **Detected.** The path was deleted through the Control API, and the pipeline logged `stream dropped` 18 ms later.
- **Reopen attempts.** While the path was gone, each reopen failed at once with OpenCV's warning, which names no URL. Attempts fell 1.03 s apart.
- **Back.** The path was re-added, seeked to where a camera that kept running would be. The stream was back 1.2 s later, after 9.2 s without a frame: 228 frames missed, 13 of them due a look.
- **After the reconnect.** Every fit of the run, 48 of them, converged at or above 0.9 (none checked, none lost). Every frame decoded clean, and the 4 Bullet Holes matched the file run.
- **The missed count.** 228 is a wall-clock estimate. The content gap was 194 frames (file frames 456–649), so the estimate is 1.4 s long, and it counts 13 due frames where the gap held 11. The first frame back is timed after FFmpeg's buffering at the reopen, as frame 0 is. Indices after a reconnect are therefore approximate by about that much (#84 counts missed frames at `LIVE_FPS` from the last frame received, by design).

**Measured for #117, frames lost upstream while the baseline is built:**
- **Instrumented runs.** In runs 1–3, frame 0 to baseline built took 1.6–2.3 s, against the 3–5 s estimated before. The reader fell at most 0.6–1.2 s behind the stream. No frame was lost: `CAP_PROP_POS_MSEC` ran in unbroken 40 ms steps, and run 1 received 1125 frames, exactly file frames 25–1149. MediaMTX logged no discard for those readers.
- **A slow start loses frames.** One uninstrumented run was slower: 2.8 s from frame 0 to baseline built, and 3.99 s for `[REGISTRATION] Board space built in` (measured from opening the source), against 2.4 s in the instrumented runs. MediaMTX then logged `reader is too slow, discarding 507 frames` and `… 399 frames` for the pipeline's session. Those counts are RTP packets, not video frames. The pipeline printed `[h264] error while decoding MB 109 48` right after the baseline.
- **A probe.** A probe reader that paused 4 s after its first frame, twice, showed the shape of it. About 2.6 s of stream (at 8 Mbit/s) stayed buffered. Then 71–74 frames (about 3 s) were lost, seen as `POS_MSEC` jumping, for example from 3320 to 6320 ms. After that, 11–12 frames decoded corrupt up to the next IDR.
- **What it means.** Loss starts once the reader is about 2.6 s behind at 8 Mbit/s. A lower bitrate buffers longer. The arrival rate hides a small loss on a short run, because it reads high anyway (above); a large one shows (21.12 fps with 199 frames lost, below). MediaMTX's log is the evidence.
- **Forcing it.** A replay with `--baseline-frames 30` holds the reader for the whole 30-look baseline. MediaMTX discarded for it throughout, and `POS_MSEC` jumped from 3880 to 11880 ms: 199 frames lost, with 926 of 1125 received. Every look after the gap fell 12 frames off the file run's stride phase (199 mod 17), the index shift #117 describes. Its Bullet Holes were run 1's within 0.1 mm, less the Miss its longer baseline absorbed, because they come 27 s later and persist for seconds. No file run was made at that baseline.
- **The timestamps are usable.** `CAP_PROP_POS_MSEC` was monotonic in 40 ms steps within an RTSP session and restarts with each new one (880 ms after run 2's reconnect).

## #117's replay, 2026-10-07: frames indexed by the stream's timestamps

**Setup.** The same as #85's: MediaMTX v1.21.1 with `VideoService/mediamtx.yml` unchanged, ffmpeg 9.0.2, a fresh H.264 copy of the spent `_102250` made with step 1's command (1150 frames, 1080p25, GOP 25), and stride 17. The same scratch wrapper, not committed, hashed every frame looked at against the copy's decoded frames. Each live run joined at file frame 25 and is compared with a file run of the copy from 1.0 s, at the same stride and baseline.

| Run | Lost upstream, as the run reported it | MediaMTX discarded | Looks hashed | Bullet Holes, live and file | Looks, live and file |
|---|---|---|---|---|---|
| `--baseline-frames 30` | 2 gaps: 100 + 65 frames, 10 of them due | 4441 RTP packets over 8 s | all 84 are file frame 25 + index | 4 and 4: positions identical to 0.1 mm | 84 and 95: 10 due in the gaps + 1 late |
| `--baseline-frames 30`, again after review | 2 gaps: 139 + 39 frames, 11 of them due | 4867 packets | all 83 are file frame 25 + index | 4 and 4: positions within 0.1 mm | 83 and 95: 11 due in the gaps + 1 held at the end |
| default baseline (5) | 1 gap: 5 frames, none due | 117 packets | 68 of 69 are file frame 25 + index; index 68 decoded corrupt | 5 and 5: positions identical to 0.1 mm | 69 and 71: 2 late |
| default baseline (5) | none | 25 packets | 67 of 68 are file frame 25 + index; index 68 decoded corrupt | 5 and 5: positions identical to 0.1 mm | 68 and 71: 3 late |

- **No shift.** Every look that decoded clean is the file frame its index names, plus the join offset, after the gaps too. Before the fix, the 30-frame baseline put every later look 12 frames off the file run's stride phase.
- **The counts agree.** In the first 30-frame run, the timestamps spanned 45.0 s, 1125 frames, and 960 were received: 1125 − 165. MediaMTX's 4441 packets are about 27 a frame for those 165, and 4867 for 178 in the second, which matches #85's probe (28). MediaMTX counts RTP packets, so the match is to a frame or two, not exact.
- **Times follow the timestamps.** Each Bullet Hole's time after frame 0 is the file run's to 0.01 s (28.56 s, for example), with frame 0's wall clock as the origin.
- **The rate.** 25.00 fps by the timestamps on every run, for the step and, with nothing lost, for the frames received too. 21.33 fps received in the 30-frame run.
- **What is still uncounted.** In the last run MediaMTX discarded 25 packets, less than one frame. That left no gap in the timestamps, only a frame that decoded corrupt (`error while decoding`) and the frames after it up to the next keyframe. In both default-baseline runs one look, index 68 (file frame 93), landed on such a frame. The Bullet Holes were the file run's all the same. Skipping corrupt frames stays out of scope until the camera run shows a gap followed by false Detections.
