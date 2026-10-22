# Overlays are drawn by the frontend from each Run's Baseline View

The WebApp shows where the system placed things by drawing an Overlay over the
camera's picture: the Session's Bullet Holes, and the Baseline View of the Run
watching (its Target outlines and Baseline Marks). The frontend draws it, live
over the WebRTC player and in replay over the recording. The Detection Service
sends the Baseline View once per Run, and where its latest Registration places
the Board in the picture on every status read, every 5 s; the backend keeps
each place that moved. Nothing is burned into the video.

## The Board does not hold still in the picture

The camera's view is fixed during a Range (#118), but the Board's place in the
picture still moves. On the four Recordings with truth that may be opened, a whole-length
`tools.registration_reach` run (`main` 1bfaa59) locates each mark already on
the Board in the raw frames, and a per-Look scratch check at `LIVE_STRIDE` maps each
Target's outline through the Look's homography against the baseline's:

| Recording | Raw-frame move of a mark, max | Per-Look, median / p95 / max | Shape |
|---|---:|---:|---|
| CamB `_102250`, 46 s, 2 marks | 7.4–7.6 px | 1.1 / 4.1 / 6.3 px | sway, back to 2 px |
| CamB `_102450`, 48 s, 6 marks | 1.5–2.4 px | — | still |
| CamB `_103223`, 52 s, 10 marks | 5.2–6.1 px | 1.6 / 3.3 / 5.2 px | one sway at 9 s, back to 1.7 px |
| CamA `_141546`, 46 s after its re-aim at 1–3 s, no marks | — | 20 / 42 / 47 px | creep, ~1 px/s, still growing |

The live page shows the 1920×1080 picture at about half size, and a marker is
drawn at a fixed size on screen. CamB's sway moves a hole at most ~4 screen px
from its marker and comes back within a few seconds. CamA's creep moves it ~23
screen px within the minute, and further for as long as it creeps. A Baseline
View alone would leave CamA's markers beside their holes.

## Why the frontend, not burned in

Burning it in means decoding, drawing on and re-encoding every 1920×1080 frame
at 25 fps and publishing a second mediamtx path, in or beside a process whose
budget is Look Time and which looks at one frame in 17
([ADR-0007](0007-live-input-is-sampled-at-a-fixed-stride.md)). It adds latency
to the live picture, the recordings would need a second path per camera or lose
the Overlay, and the operator could not turn it off to see the bare hole. Its
one gain, the drawing moving with every frame, buys little: the Board creeps at
about 1 px/s, and a place refreshed every 5 s stays within a few px of it.

## Why the Baseline View once, and the Board's place every 5 s

Everything the Overlay draws is a place on the Board, in template coordinates:
the Bullet Holes, the Target outlines, the Baseline Marks. None of them moves
on the Board during a Run, so the Baseline View is sent once, when the Run
starts watching. Only the mapping from template coordinates onto the picture
changes, and the Detection Service already computes one for every registered
Look.

Its latest rides on the Service's run view, which the backend already reads
every 5 s through `GET /status`, so following the Board needs no new endpoint
and no new contract. The backend keeps a place only when it has moved by more
than a couple of px since the last one it kept: a few rows a minute while the
Board creeps, and none while it holds. Replay draws the place kept last before
the moment on screen.

A stream of every Look's registration (in-process detail, at Look rate, for an
operator who cannot act on a Look) stays out. So does following sway, which
comes back within the 5 s.

The backend keeps one Baseline View per Run, not one per Session: a later
Run's Baseline Marks include the Session's own earlier Bullet Holes, and replay
must not draw them before they were fired.

## Consequences

- The Overlay follows a Board Move as far as Registration does, within one
  status read. A move Registration loses leaves the Overlay at the last place
  until a re-anchor or a fresh Run. A wrong fit shows rather than hides: the
  Target outlines sit off the printed Targets, which tells the operator the
  markers cannot be trusted.
- Template coordinates stop being clamped to the artwork. A Bullet Hole on
  another Target, or a Miss beyond the artwork, was stored on the artwork's
  border, and the Overlay would have drawn it there. Rows stored before the
  change keep their clamped positions.
- The pipeline's internals (Candidates, Lost Looks, registration quality) stay
  out of the WebApp, in the Detection Service's own tooling on Recordings.
