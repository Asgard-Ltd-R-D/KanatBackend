# The delivered recordings, grouped by Capture Setup

**Measured 2026-09-22.** Six `.mkv` files arrived: one CamA and the five CamB
customer recordings ADR-0005 allocates. They now live in `videos/` beside the two
legacy clips, and they are not version-controlled — they run to 1.9 GB and
`.gitignore` reserves `ImageRecognitionService/videos/*.mkv`. The sha256 in
`recordings.json` is the link between a file on disk and its role, and this
document is the grounds for the role. The hashes were re-verified after the move
from the delivery folder: a recording's role travels with its bytes, not its
path.

The before/after photographs the ground truth is derived from stayed in the
delivery folder; `truth/*/board.source.txt` still names them.

## The count

**Three distinct Capture Setups across the six files. Two across the five
customer recordings.** Five files do not collapse to one Capture Setup, as
ADR-0005 allowed they might; they collapse to two, and the boundary does not
fall where file count would put it.

Later arrivals, 2026-09-23: three CamA files join `cama-20260914` and change
neither count; nine more make **two further setups, both sealed** — one Board,
one afternoon, at two framings. See the last two sections.

| Capture Setup | Recordings | Role |
|---|---|---|
| `cama-20260914` | `CamA_20260914_141446`, `_141546`, `_141646`, `_141846` | spent |
| `camb-20260915-wide-two-boards` | `CamB_20260915_101450`, `_101550` | **sealed** |
| `camb-20260915-close-one-board` | `CamB_20260915_102250` (spent), `_102450`, `_103223` | threshold-work |
| `cama-20260914-wide-tight` | `CamA_20260914_153603`, `_153908` | **sealed** |
| `cama-20260914-wide` | `CamA_20260914_154008`, `_154108`, `_161935`, `_162035`, `_162936`, `_163036`, `_163136` | **sealed** |

## What was measured

Frame 0 of each recording, and nothing else. Every figure below comes from one
decode of the first frame plus the container header:

- **sha256** — `manifest.content_hash`, the whole file.
- **Timestamp** — the filename, corroborated by the file's mtime, which lands
  9–15 s after `filename time + duration` on all six. One recorder, one clock,
  and mtime is the moment writing finished. Nothing in the delivery contradicts
  a filename.
- **Geometry** — `board.find_targets` on frame 0: the printed green Targets
  found by the same hue gate the runtime uses, largest first. Centroid is
  camera pose, span is distance.
- **First-frame MAD** — mean absolute difference of the full-resolution
  grayscale first frames, pairwise. The measure `dataset_audit.md` §3 used to
  find near-duplicates across the train/validation boundary, applied here to
  find recordings of one Capture Setup instead.

All six are 1920x1080, 25.0 fps, FMP4. Resolution and frame rate separate
nothing in this delivery and are recorded so that a future one that *does* differ
is visible against them.

| Recording | Capture time | Duration | Targets in frame 0 (centroid, span px) | Mean grey |
|---|---|---|---|---|
| `CamA_20260914_141546` | 2026-09-14 14:15:46 | 51.24 s | (1104, 699) 502 · (1048, 155) 432 | 80.7 |
| `CamB_20260915_101450` | 2026-09-15 10:14:50 | 45.00 s | (142, 405) 166 · (946, 448) 155 · (144, 584) 156 | 126.1 |
| `CamB_20260915_101550` | 2026-09-15 10:15:50 | 48.28 s | (144, 491) 338 · (942, 447) 146 | 126.7 |
| `CamB_20260915_102250` | 2026-09-15 10:22:50 | 46.00 s | (701, 427) 173 | 122.2 |
| `CamB_20260915_102450` | 2026-09-15 10:24:50 | 47.76 s | (700, 426) 171 | 121.7 |
| `CamB_20260915_103223` | 2026-09-15 10:32:23 | 51.88 s | (709, 427) 182 | 123.2 |

### First-frame MAD, full resolution, 0–255

|  | 101450 | 101550 | 102250 | 102450 | 103223 |
|---|---|---|---|---|---|
| **CamA 141546** | 63.55 | 63.79 | 60.54 | 60.42 | 61.23 |
| **101450** | — | **20.16** | 53.72 | 53.95 | 54.04 |
| **101550** | | — | 53.40 | 53.62 | 53.74 |
| **102250** | | | — | **19.86** | 26.25 |
| **102450** | | | | — | **21.71** |

Within a group 19.9–26.3; between the two CamB groups 53.4–54.0; CamA against
anything 60.4–63.8. There is no pair that makes the boundary ambiguous — the gap
between the largest within-group distance and the smallest between-group one is
a factor of two.

## Why each recording belongs to its setup

### `cama-20260914` — CamA_20260914_141546, alone

A different day, a different camera and a different Board. Two Targets in frame
0 at spans 502 and 432 px, against 146–182 px for every CamB recording: the
camera is three times closer to the artwork, or the artwork is three times
larger. Afternoon light, mean grey 80.7 against CamB's 121.7–126.7. MAD 60.4–63.8
against every CamB frame. Nothing in the delivery groups with it.

ADR-0005 names two further CamA files, `_141446` and `_141846`, as part of this
setup. Neither arrived in this delivery; they arrived later, with a third,
below.

### Three later CamA files — `_141446`, `_141646`, `_141846`

**Measured 2026-09-23**, the same way: frame 0, container header, sha256. All
three are 1920x1080, 25.0 fps, FMP4, and byte-identical to their copies in the
`2026_09_14_Dvira` delivery folder. `_141646` is named in no ADR; it arrived
beside the two that are.

| Recording | Capture time | Duration | Targets in frame 0 (centroid, span px) | Mean grey |
|---|---|---|---|---|
| `CamA_20260914_141446` | 2026-09-14 14:14:46 | 48.64 s | (1064, 719) 502 · (1010, 166) 436 | 92.8 |
| `CamA_20260914_141546` | 2026-09-14 14:15:46 | 51.24 s | (1104, 699) 502 · (1048, 155) 432 | 80.7 |
| `CamA_20260914_141646` | 2026-09-14 14:16:46 | 52.08 s | (1034, 430) 484 · (1088, 949) 416 | 80.9 |
| `CamA_20260914_141846` | 2026-09-14 14:18:46 | 53.00 s | (1008, 405) 482 · (1059, 935) 422 | 79.9 |

First-frame MAD, full resolution: 141446–141546 19.46, 141446–141646 24.97,
141446–141846 25.35, 141546–141646 18.56, 141546–141846 18.77, 141646–141846
**10.19**. Against the CamB close trio (`_102450`), 56.7–60.5. The sealed pair
was not opened for this.

**One Capture Setup.** The same Board — the two green silhouettes stacked, the
ringed panel with its cross to their left, the same pre-existing marks on the
left of the lower silhouette — the same light and the same distance: Target
spans 482–502 px against CamB's 146–182. Every within-CamA MAD, 10.2–25.4, lies
in the within-setup band this document found for CamB (19.9–26.3), none near
the 53–64 that separates setups.

What varies is aim. Between `_141546` and `_141646` the camera tilted up: the
Board sits about 270 px lower in frame, the lower silhouette is cut off at the
bottom edge and the upper one becomes the largest Target. That is a re-aim at
unchanged distance, not the move-in that separates the CamB groups, where the
Targets grew 12–17% and crossed 245 px of frame. And it would change no role:
every CamA file shares the Board and afternoon every current constant was fitted
on, and none of it is sealed.

**`spent`**, all three — the role ADR-0005 gives `_141446` and `_141846` by
name, and which `_141646` must share, sitting one minute between them with a
frame closer to `_141846` than any other pair in this delivery. Spent is the
negative-mining source.

### `camb-20260915-wide-two-boards` — 101450 and 101550

**Same Board, seen from further back, with a second Board in frame.** Frame 0 of
both shows the main Board right of centre and a *second* Board at the left edge
carrying two more green silhouette Targets and a ringed one, already well shot. The
main Board's right-hand Target sits at (946, 448) span 155 in one and (942, 447)
span 146 in the other — a camera that has not moved between them.

101550 reports two Targets where 101450 reports three because the two silhouettes
on the left-hand Board close into a single blob under the hue gate's 9x9
morphology: the merged contour's centroid (144, 491) is the midpoint of the two
it replaces, (142, 405) and (144, 584), and its span 338 is their combined
extent. That is one detection artefact, not a change of arrangement, and the right-hand
Target is unmoved across it.

MAD 20.16 between them, 53.4–54.0 to anything else. One minute apart. One setup.

### `camb-20260915-close-one-board` — 102250, 102450 and 103223

**The same Board, the same morning, the same light — after the camera moved in
and re-aimed.** The second Board is gone from frame entirely and the main Board
fills it, its single Target at (701, 427) / (700, 426) / (709, 427), spans
173 / 171 / 182. Against the wide group's (946, 448) span 155, that is a Target
that has crossed 245 px of frame and grown 12–17%: the camera is closer and
pointed elsewhere.

The plastic bottles and blue sheeting taped below the silhouette, the two
sprayed X panels and the two ring panels are identical in both groups, and the
Bullet Holes on the green silhouette accumulate monotonically across all five
recordings — the photograph-derived truth counts 0, 1, 2, 6 and 10 pre-existing
marks in timestamp order, each equal to the previous recording's after-count.
**Same Board, one continuous morning of shooting.** What separates the groups is camera pose
and distance, which is exactly what ADR-0005 makes the unit.

Within the trio, 103223 has drifted 9 px right and 6% larger over the eight
minutes since 102450 — a nudged tripod, not a new setup, and an order of
magnitude smaller than the move that separates the groups. MAD 19.9–26.3 across
the three.

The timestamp gaps do not carry this on their own, and are not asked to: the
7-minute gap between 101550 and 102250 brackets the camera move, but the
7.5-minute gap between 102450 and 103223 brackets nothing. Framing is the
evidence; the gaps only corroborate it.

## Why the allocation is not two-to-threshold-work

The obvious reading of ADR-0005 — two recordings for threshold work, the rest
sealed — would put the wide pair on threshold work and seal the close trio. That
is the wrong way round, and the reason is that **`CamB_20260915_102250` has
already been analysed at length.**

It is one of the two clips in HANDOVER's results table, scored F1 0.86 over
25–36 s. The registration drift figures, the ECC medians, the 0.59x merge
measurement and the residual censoring that ADR-0006 rests on were all taken on
it, and HANDOVER's own instruction is "do not move any constant further on CamA
and CamB alone." Every current constant in the pipeline is jointly fitted to
CamA and this recording.

Sealing `_102450` and `_103223` would therefore hold out two files of a session
the constants were fitted to — the precise error ADR-0005 was written to
prevent: *"holding out a file from a tuned session measures re-detection of a
scene already fitted, and reports it as generalisation."* The setup is spent
whether or not two of its three files have been opened, because what was fitted
was the arrangement in front of the camera.

So the whole close trio takes `threshold-work`: it may falsify a constant, and
it may not optimise one. `_102450` and `_103223` have never been opened and can
still break something on a variation within the setup, which is worth having; what they
cannot do is measure generalisation.

That leaves the wide pair as the only footage in the delivery with a camera pose
nothing has been fitted to. **They are the held-out set: one Capture Setup, two
recordings, roughly two Bullet Holes.** It is a thin held-out set, and it is the
only one the delivery contains. Sealing the larger group instead would have
produced three recordings that measure nothing.

The five customer recordings therefore split two sealed / three threshold-work
rather than two threshold-work / three sealed. Setup integrity is what forces
it, and ADR-0005 makes setup integrity the rule that outranks the file count.

## What was looked at, and what that spends

Frame 0 of the two sealed recordings was decoded, and its Target geometry, mean
grey and MAD against the others are in the table above. That is the allocation
itself — ADR-0005 asks for grouping by camera pose, Board, lighting and
distance, and none of those can be established without seeing one frame. No
constant was moved on it, no model saw it, and nothing beyond frame 0 was read.

Every later run is gated: `recordings.json` now carries all six files, both
sealed recordings are refused without `--final-run`, and a permitted run appends
its date, model and commit to `sealed_runs.log`.

## Nine CamA files from the afternoon — two setups, both sealed

**Measured 2026-09-23**, frame 0 and the container header only; no detector,
scoring, sweep or mining touched them. They arrived in the `2026_09_14_Dvira`
delivery folder, and their copies in `~/Downloads` are byte-identical. All nine
are 1920x1080, 25.0 fps, FMP4. Every mtime lands 19–25 s after filename time
plus duration: one recorder, one clock, filenames trusted.

| Recording | Capture time | Duration | Targets in frame 0 (centroid, span px) | Mean grey |
|---|---|---|---|---|
| `CamA_20260914_153603` | 15:36:03 | 40.00 s | (1543, 475) 202 · (1845, 86) 172 · (56, 566) 212 · (42, 320) 192 | 95.7 |
| `CamA_20260914_153908` | 15:39:08 | 40.48 s | (1547, 277) 202 · (45, 113) 198 · (52, 364) 200 | 84.7 |
| `CamA_20260914_154008` | 15:40:08 | 37.44 s | (1491, 126) 164 | 85.8 |
| `CamA_20260914_154108` | 15:41:08 | 33.28 s | (1480, 143) 158 | 86.3 |
| `CamA_20260914_161935` | 16:19:35 | 35.04 s | (1498, 133) 166 · (1228, 480) 160 | 95.0 |
| `CamA_20260914_162035` | 16:20:35 | 22.80 s | (1495, 132) 168 · (1219, 478) 164 | 82.6 |
| `CamA_20260914_162936` | 16:29:36 | 39.60 s | (1481, 132) 168 · (1216, 474) 160 | 81.6 |
| `CamA_20260914_163036` | 16:30:36 | 39.88 s | (1488, 147) 166 | 82.0 |
| `CamA_20260914_163136` | 16:31:36 | 39.44 s | (1498, 144) 164 · (1231, 494) 156 | 81.3 |

References were unsealed only — `CamA_141546`, `CamA_141846`, `CamB_102450`.
The sealed CamB pair was not opened.

**MAD does not carry this grouping.** The frame is mostly dry-grass ground, and
first-frame MAD runs 13.3–28.7 between any two of the nine *and* 22–30 against
the CamA close-ups; only CamB stands apart, at 53–61. Within `-wide` it is
13.3–23.7, the high end all `_161935`, whose exposure is brighter (grey 95.0).
The evidence is Target geometry and what is in frame.

### What the frames show

A wide view of a large plywood Board: a sprayed black cross, three small green
silhouettes on its right panel, a ringed panel top left, taped bottles, dry
grass all round and a second Board's edge at the left of frame. Target spans of
156–212 px against `cama-20260914`'s 482–502: the camera is about three times
further back, an hour and a half later, in afternoon light. Nothing in the
pipeline has been fitted to this pose. Whether it is the close-up's Board
re-dressed cannot be told from frame 0, and does not need to be: ADR-0005
already sealed the CamB wide pair on exactly those terms — same Board, same
day, a pose nothing was fitted on.

### `cama-20260914-wide-tight` — 153603 and 153908

Spans 172–212, the Board running off the right edge. Between the two files the
lead Target moves 198 px vertically at an unchanged span of 202 — a tilt, as
between `_141546` and `_141646`, not a move.

### `cama-20260914-wide` — 154008 through 163136

In the 20 s between `_153908` and `_154008` the camera zooms out about 20%
(span 202 → 164) and re-aims; the Board is then wholly in frame, and the lead
Target holds at (1480–1498, 126–147), span 158–168, for fifty minutes across
all seven. From `_161935` a blue-taped dummy stands against the Board. That is
Board dressing, not a Capture Setup: pose, distance and light are unchanged.

### Two setups, one scene

The split follows the CamB precedent, where a 12–17% zoom and a re-aim were a
boundary. But these are one Board in one session, 20 s apart at the join, so
as held-out evidence they are **one scene at two framings**, and must be
reported that way — not as two independent Capture Setups.

### Roles

**Both sealed.** Neither pose has been analysed, and both are what the
held-out set is for. Making `-wide-tight` threshold-work to mine its ground was
considered and rejected: it is 20 s and one zoom step from the sealed block, so
its gravel and light are the sealed set's, and ADR-0005 forbids exactly that.
They add no negatives to #28; the miner refuses them.

This roughly quadruples the held-out footage: until now it was one setup and
about two Bullet Holes.

Still unallocated and unopened: `_144747`, `_145047` and `_150248`–`_150548`,
in `2026_09_14_Dvira` only. With no manifest entry, every tool refuses them.
