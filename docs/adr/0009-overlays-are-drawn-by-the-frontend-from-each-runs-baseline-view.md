# Overlays are drawn by the frontend from each Run's Baseline View

The WebApp shows where the system placed things by drawing an Overlay over the
camera's picture: the Session's Bullet Holes, and the Baseline View of the Run
watching (its Target outlines and Baseline Marks). The frontend draws it, live
over the WebRTC player and in replay over the recording, from a Baseline View
the Detection Service sends once per Run. Nothing is burned into the video, and
the Overlay does not follow a Board Move.

## Why the frontend, not burned in

Burning it in means decoding, drawing on and re-encoding every 1920×1080 frame
at 25 fps and publishing a second mediamtx path, in or beside a process whose
budget is Look Time and which looks at one frame in 17
([ADR-0007](0007-live-input-is-sampled-at-a-fixed-stride.md)). It adds latency
to the live picture, the recordings would need a second path per camera or lose
the Overlay, and the operator could not turn it off to see the bare hole. Its
one gain, pixel-exact sync with the frame, buys almost nothing: the camera does
not move during a Range (#118), so a Bullet Hole's place in the picture is
fixed for the Run, and its marker is still once it appears.

## Why once per Run, not per Look

The Detection Service holds a template-to-picture homography for every Look,
but the Overlay uses only the baseline's. Streaming each Look's registration
would be a high-rate channel through the backend, which was built on Bullet
Holes arriving slowly, for an operator who cannot act on a Look. The Baseline
View rides on the Service's run view, which `POST /runs` and `GET /status`
already return, so a backend restarted mid-Run gets it too. The backend keeps
one per Run, not one per Session: a later Run's Baseline Marks include the
Session's own earlier Bullet Holes, and replay must not draw them before they
were fired.

## Consequences

- After a Board Move the Overlay stops matching the picture until a fresh Run.
  That shows rather than hides: the Target outlines slide off the printed
  Targets, which tells the operator the markers cannot be trusted. Following a
  Board Move belongs to SOW 2.1.6 (#162).
- Template coordinates stop being clamped to the artwork. A Bullet Hole on
  another Target, or a Miss beyond the artwork, was stored on the artwork's
  border, and the Overlay would have drawn it there. Rows stored before the
  change keep their clamped positions.
- The pipeline's internals (Candidates, Lost Looks, registration quality) stay
  out of the WebApp, in the Detection Service's own tooling on Recordings.
