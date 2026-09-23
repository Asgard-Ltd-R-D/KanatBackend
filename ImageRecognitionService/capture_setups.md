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
customer recordings.** Five files do not collapse to one Capture Setup, as ADR-0005
allowed they might; they collapse to two, and the boundary does not fall where
file count would put it.

| Capture Setup | Recordings | Role |
|---|---|---|
| `cama-20260914` | `CamA_20260914_141546` | spent |
| `camb-20260915-wide-two-boards` | `CamB_20260915_101450`, `_101550` | **sealed** |
| `camb-20260915-close-one-board` | `CamB_20260915_102250` (spent), `_102450`, `_103223` | threshold-work |

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
setup. Neither arrived in this delivery; they get entries when they do.

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
