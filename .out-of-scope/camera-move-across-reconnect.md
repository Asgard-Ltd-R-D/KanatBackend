# Following a camera move across a stream reconnect

Kanat does nothing special to registration when a live stream reconnects. The
first Look after a drop is tracked like any other: no forced re-anchor, and no
extra check of its fit.

## Why this is out of scope

The camera does not move while a Range is being shot. The fixed-view rule
(`ImageRecognitionService/docs/live_camera.md`, "Fixed view during a Range")
holds one PTZ preset, with zoom and focus fixed, for the whole Range: no
operator PTZ, no guard tour, no autotracking. A move mid-Range invalidates the
Range, and a new preset starts a new Range with its own baseline. The SOW asks
for neither PTZ control nor detecting PTZ movement. A stream outage changes
none of that, so a deliberate move across a reconnect means the Range is already
invalid.

That leaves an accidental move during an outage, such as a knock or wind on the
mount. Registration has two defences that run on every Look, whether or not
there was a reconnect. They are tested only on synthetic moves, never on a
physical one:

- **Each tracked fit starts from the Board's shift since the last registered
  Look** (`board.board_shift`, #171). A reconnect leaves `Registration` as it
  was, so the first fit after a drop starts from the last frame registered
  before it. #171's synthetic moves (`tools.board_move`) registered
  translations up to 80x40 frame px and a 2° turn. Those moves warp the whole
  of a recorded frame. `tools.board_move` says they stand in for a Board move
  only inside the Board region Registration reads, and lists a camera move as
  not tested.
- **A fit converging below `REANCHOR_MIN_CORRELATION` (0.9) is checked**
  against an independent silhouette fit. A grossly wrong one is Lost, and
  re-anchored after `REANCHOR_AFTER_LOST` Lost Looks (#110, #80).

The proposal was to check the first fit after every reconnect whatever its
correlation, and to log it. On the dev Mac, that one Look would cost 0.7 s
more on CamB (one Target) and 1.8 s more on CamA (two Targets), against a
680 ms budget a Look at `LIVE_STRIDE`. Testing it on the camera meant moving
the PTZ on purpose, which invalidates the Range.

## What stays uncovered

These are accepted, and not measured:

- **Any physical camera move.** Every move tested was a synthetic warp of a
  recorded frame, with no change in lighting, parallax or exposure.
- **An accidental move that is not a plain shift:** a zoom, a tilt that changes
  the perspective, or a turn past 2°.
- **A shift past 80x40 frame px,** the largest tested (#162's case set). Past
  that, nothing shows the seed still works. Once most of the Board leaves the
  box `board_shift` reads, phase correlation has little of it left to match.
  That box is 533x573 frame px on CamB `_102250`, where one Target is about
  200 px across.
- **A wrong fit after one of those that converges at or above 0.9** is never
  checked. One that is 3.1-66 Board px off is kept, with one warning at the
  end of the run.

## When to reopen

- **A live run shows Bullet Holes displaced, or Baseline Marks reported as new,
  after a reconnect.**
- **The operating rule changes:** PTZ, a guard tour or autotracking during a
  Range.
- **The camera's mount is found to move in the field:** wind, or an unbraced
  pole.

Start from #118. It has the risk list, the measured cost, and the three-drop
camera procedure drafted for #85: no move, a small move, a large one.

## Prior requests

- #118: "Re-anchor right after a stream reconnect?", rewritten in triage as
  "Registration: after a stream reconnect, check the first fit whatever its
  correlation, and log it"
