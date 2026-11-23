# False Bullet Holes after the camera is fully covered

Kanat does nothing special when the whole view is covered for a moment and
then uncovered. Registration keeps tracking Look by Look as usual. Sometimes
the Looks just after the cover are fitted a few Board px off, and Bullet Holes
that were already on the sheet are then reported as new, many at once.

## What was measured (2026-11-17)

The evidence is a screen recording of the WebApp's Video Overlay: two full
occlusions, an arm at ~16.6 s and a hand at ~27.4 s. Live, the first gave no
reports and the second gave 17. Every one of the 17 is a hole that was already
on the sheet, drawn 15-20 screen px from it, all offset the same way.

- **Registration, not the detector.** Hole blobs measured straight off the raw
  frames moved at most 1-2 px (scale 0.998) across the first occlusion. The
  registration fit for the same frames moved 5-7 px, which takes a Baseline
  Mark past the 7 Board px match radius.
- **Replaying the recording** at stride 1 reports 31 holes that were already
  on the sheet right after the first occlusion, all at persistence 95-100%. At
  stride 4 it reports neither burst. Which frames get looked at decides it,
  which is why it happens only sometimes.
- **Mechanism.** After the cover the camera spends several seconds refocusing
  and re-exposing:
  - Covered frames with sharpness from 0.15 to 0.19 of the baseline frame's
    pass the defocus gate (`DEFOCUS_RATIO`, #351). Their fits come out
    300-1300 px off, yet `silhouette_disagreement` reads 4-43 px on them,
    under the 66 px gross limit, so they are kept and seed the next fit.
  - Soft, re-exposed frames after the cover (sharpness 0.15-0.31) converge
    5-7 px off at ECC 0.97-0.99. That is above `REANCHOR_MIN_CORRELATION`
    (0.9), so they are never checked (the `ponytail:` note in
    `Registration._grossly_wrong`).
  - In one stride-4 trial a wrong fit from a covered frame seeded every later
    fit, which stayed 957 px off to the end.
- **A stricter defocus gate is no fix.** At 0.35 most of the bad fits become
  Lost, but a frame at sharpness 0.75 just after the cover still fit 6 px off.
- **Older than recent work, but #321 tipped it over.** The same stride-1
  replay of 0-20 s gives 0 reports on `5ead14d` (before #296), 2 on `9034ae7`
  (the parent of #321's merge), 26 on `2703c95` (#321's merge, ECC on the
  sheets only), 26 on `582df3b` (before #351) and 30 on `main`. The fits after
  the cover drift before #321 too, a median of 5.3 frame px against 6.1 after
  it. #321 adds about 1 px, enough to take the Baseline Marks past the match
  radius on this clip. Reverting #321 would bring back the chair-move false
  positives it removed (7 to 0 on `Second.mp4`).
- **A lighting change alone gave no reports** (2026-11-18, on the AXIS camera,
  live). For 26 s the lighting changed repeatedly, from warm to cool to grey
  and once to near dark, with nothing covering the camera. No Bullet Hole was
  reported. Repeated full covers on the same camera still gave a burst on some
  covers and nothing on others.
- **Not reproduced:** the live burst at 27 s itself. Twelve offline trials
  (stride phases and random dropped Looks) all recovered within ~0.1 s.

The recording is a re-encoded 1264 px screen capture, not the camera's stream,
so none of the sharpness or drift figures above is the camera's own.

## Since #383 (2026-11-22)

On `198ed00`, the same recording replayed from 2.1 s at stride 4 reports 36
false Bullet Holes at 17.43 s. A covered frame converged at correlation 0.23
with its sheet corners ~130 Board px off. `silhouette_disagreement` read it
at the reference Target's centre, 16 Board px, so it was kept. Every later
Look was seeded from it and stuck ~720 px off at ~0.2. A fit under 0.5 is now
Lost without the check (`MIN_FIT_CORRELATION`): 36 becomes 1, an existing hole
the replay's baseline missed. The 5-7 px drift at ECC 0.97 described above
still passes unchecked, and the rest of this record stands.

## Why this is out of scope

A shooting range does not cover its camera. Nothing in a normal Range puts
something right up against the lens. The fixed-view rule
(`ImageRecognitionService/docs/live_camera.md`, "Fixed view during a Range")
holds focus at the preset, which rules out the refocusing seen here. A hand
held only partly in front of the lens (~8 s in the same recording) gave no
reports. If a camera is covered mid-Range, Retake baseline (#327) starts a new
Run with a clean baseline.

A fix would mean checking fits that converge at 0.9 or above, at least the
first ones after a run of Lost Looks. That costs 0.5-1 s per checked 1080p
frame (#110). Its thresholds would also have to be set from the camera's own
footage, which this recording is not.

## What stays uncovered

These are accepted, and not measured on the camera:

- **A full occlusion of the camera,** followed by its exposure recovering.
- **A lighting change other than the one tried:** one 26 s live test passed,
  watched in the WebApp and not replayed from a recording.
- **A camera whose focus is not held,** contrary to the fixed-view rule.
- **A covered frame that still passes the defocus gate.** Its fit is
  kept, wrong, whenever `silhouette_disagreement` stays under 66 px.

## When to reopen

- **Reports of Bullet Holes that were already on the sheet, many at once,
  on a Range where the camera was not covered,** for example after a lighting
  change.
- **Exposure or focus is found to change during a Range** on the deployed
  camera.

Start from the `ponytail:` note in `Registration._grossly_wrong`, and record
the camera's own stream (MediaMTX) through the event: a screen capture cannot
set the thresholds.

## Prior requests

- None filed. Reported 2026-11-17 with a screen recording of the Video Overlay.
