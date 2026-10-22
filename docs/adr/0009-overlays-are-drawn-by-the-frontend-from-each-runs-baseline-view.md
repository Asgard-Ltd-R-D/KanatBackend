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

The Baseline View and the latest of those mappings ride on the Service's run
view, which `POST /runs` answers with and the backend already reads every 5 s
through `GET /status`. That needs no new endpoint, but it does extend the run
view (below): today it carries only `session_id`, `state`, `since` and a
`baseline_marks` count, and the backend's client keeps only the first two. The
backend keeps a place only when it has moved by more than a couple of px since
the last one it kept: a few rows a minute while the Board creeps, and none
while it holds. Replay draws the place kept last before the moment on screen,
and only while that Run was watching (its end, below).

A stream of every Look's registration (in-process detail, at Look rate, for an
operator who cannot act on a Look) stays out. So does following sway, which
comes back within the 5 s.

The backend keeps one Baseline View per Run, not one per Session: a later
Run's Baseline Marks include the Session's own earlier Bullet Holes, and replay
must not draw them before they were fired.

## The run view's extension

The control API (ADR-0008) is not versioned. The Detection Service and the
backend ship together from this repo, and both ends change in one release.
Three fields are added to the run view; every existing field keeps its meaning.

```jsonc
"baseline_view": {                          // null until the Run is watching
  "taken_at": "2026-10-22T10:15:02.120Z",   // the baseline frame's time, on first_seen_at's clock
  "picture": {"width": 1920, "height": 1080},
  "template_to_picture": [[a, b, c], [d, e, f], [g, h, i]],  // template px → baseline frame px
  "targets": [[[x, y], ...], ...],          // one outline per Target, index = target_index, template px
  "baseline_marks": [[x, y], ...]           // template px
},
"registered": {                             // null until watching; a Lost Look leaves it as it was
  "at": "2026-10-22T10:15:47.880Z",         // the latest registered Look's frame time, same clock
  "template_to_picture": [[a, b, c], [d, e, f], [g, h, i]]
},
"looked_at": "2026-10-22T10:15:48.560Z"     // null until watching; the latest Look's frame time, registered or Lost
```

The end's answer (`POST /runs/{session_id}/end`, today `{session_id, state}`)
also carries the Run's final `registered` and `looked_at`. A Board Move in the last seconds
before an end, where a Bullet Hole confirmed in the closing window then sits,
is therefore not left at the previous poll's place. A move between two reads is
still not kept, as between any two polls.

The backend persists one `runs` row per Run: its Session, the alias of the
camera it watched, `taken_at`, the Baseline View as JSON, the places it kept,
each an `at` and a `template_to_picture`, starting with the baseline's, and
`watched_until`.

## A Run's end

A Run watches only part of its Session when it is lost and a later Run takes
over, so replay must know when each one stopped. `watched_until` is the latest
`looked_at` the backend has read from the Run: the frame time of its latest
Look, registered or Lost, on the same clock as `taken_at`. Every status read
that shows the Run moves it on, and the end's answer gives the last one. It
stops moving when the Run stops, whatever stopped it, so the backend never has
to notice an end, and a backend restart loses nothing it had stored.

Replay draws a Run only between its `taken_at` and its `watched_until`, so
nothing is drawn while no Run watched; live, the Overlay shows only while the
Session reads `watching` or `ending`. A Run that is lost, rather than ended,
loses its Overlay for up to its last 5 s, the time since the last read. One that
stopped while the backend was down loses it from the backend's last read. A
Lost stretch, mid-Run or at its end, is drawn at the last place registered, as
any time between two reads is; one a Board Move caused shows as outlines off
the printed Targets.

## Bullet Holes from an earlier Run

Each Run's template coordinates hang on the Target that was largest at its
baseline (`board.build_view`), and that can change from one Run to the next.
On CamA `_141546` the lower Target is the largest at frame 0, and the upper
one after the camera's re-aim at 1–3 s, once the lower one is partly out of
the picture (#240). As CONTEXT.md's Run says, places from two Runs do not
compare directly, so an earlier Run's Bullet Holes cannot be drawn through a
later Run's mapping as they stand.

A Bullet Hole belongs to the Session's latest Run whose `taken_at` is at or
before its `first_seen_at`. A later Run's baseline frame is newer than any
frame of an earlier one, so that is the Run that reported it. A manual Bullet
Hole follows the same rule, by the time the operator gave it, and one from
before the Session's first Run belongs to that first Run: it was fired before
that Run's baseline, which saw it as a Baseline Mark. Over its own
Run, a Bullet Hole goes through that Run's place. Over a later Run `c`, a
Bullet Hole `p` of Run `r` goes onto the picture through `r`'s last kept place,
back into `c`'s template coordinates through `c`'s baseline mapping, and out
through `c`'s place at the moment:

```text
picture = H_c(t) · H_c(taken_at)⁻¹ · H_r(last) · p
```

Its error is how far the Board moved in the picture between the two Runs. That
gap is normally seconds: under ~10 px of CamA's creep.

A Baseline Mark within `MATCH_TPL_PX` (20 template px) of a Bullet Hole drawn
over the same Run is not drawn, because the Bullet Hole stands for it. After a
restart the new Run's Baseline Marks include the Session's earlier Bullet
Holes, which would otherwise show twice, numbered and grey. The rule also
hides the grey ring once the operator adds by hand a hole fired while no Run
watched.

## Consequences

- The Overlay follows a Board Move as far as Registration does, within one
  status read. A move Registration loses leaves the Overlay at the last place
  until a re-anchor or a fresh Run. A wrong fit shows rather than hides: the
  Target outlines sit off the printed Targets, which tells the operator the
  markers cannot be trusted.
- The bullet contract's `position` loses its 0–1405 × 0–1120 bounds: the
  publisher stops clamping, and the backend's schema accepts any finite x/y.
  That widens what `v1` accepts and narrows nothing, so every `v1` payload
  stays valid and the version stays `v1`. The contract doc changes with that
  code, not before it. Until then a Bullet Hole on another Target, or a Miss
  beyond the artwork, is stored on the artwork's border, where the Overlay
  would draw it. Rows stored before the change keep their clamped positions.
- The pipeline's internals (Candidates, Lost Looks, registration quality) stay
  out of the WebApp, in the Detection Service's own tooling on Recordings.
