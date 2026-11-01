# More than one Board, or more than one Target, in a camera's view

Kanat is tuned for one Board per camera with one Target on it. Nothing is
built to make a view of two Boards register correctly, or to split Targets
that touch, which `board.find_targets` merges into one. Nor is anything built
to make #110's silhouette check cheap where such views trigger it.

Targets that stand apart on one Board are not part of this exception. They
keep the support they have: each is found, gets its own Target Sheet and
`target_index`, and has its own Group in the WebApp (`WebApp/CONTEXT.md`). A
break in that path is a regression.

## Why this is out of scope

On a real Range, each camera sees one Board, and each Board carries one
Target. Some recordings show more than that. They stay in the regression set
for scoring, but nothing is tuned for them and they do not set
`LIVE_STRIDE`:

- **Two Boards:** CamB `camb-20260915-wide-two-boards` (`_101450`, `_101550`).
- **Two Targets on one Board:** CamA `cama-20260914`. It is out of scope
  only for setting the stride and for the check's cost. Its per-Target scoring
  stays supported.

Measured 2026-11-01 on `main` at 600c1bd, for #277 and #288, on such views:

- **Touching Targets are merged.** On `_101550` the two stacked Targets on the
  left Board nearly touch. `board.find_targets`' 9x9 close joins them, so Board
  space is built with 2 Targets where the frame shows 3. The reference Target
  is that merged pair, and its centre falls between the two real ones. A
  silhouette fit seeded from any contour then disagrees by 178-220 Board px,
  so every fit the check sees is called gross. All 18 Lost Looks at stride 1
  were such false losses: the left Board sat where registered Looks put it.
- **One homography spans two Boards.** On `_101550` the right-hand Board's
  Target is placed 50-240 px off its own outline on every frame, registered
  ones included.
- **The silhouette check is slow.** It took 430-750 ms on each of those 18
  Looks, and 634 ms on one Lost Look of a CamA live replay at stride 6, which
  dropped the next two due frames late.

On the in-scope footage (CamB `camb-20260915-close-one-board`: `_102250`,
`_102450`, `_103223`) the check never fired at stride 1. The slowest
registration there was 24-81 ms.

## What stays uncovered

- **A gross fit on a one-Target view.** It still runs the check, which costs
  about 0.7 s on CamB (#118's record) and drops the due frames behind it.
  None has been seen on in-scope footage.
- **The misplacements above on the out-of-scope recordings.** They are scored
  as before. A change caused by merged Targets or by the one homography across
  two Boards is not read as a regression. A change in how separate Targets are
  told apart, or in their Groups, is.

## When to reopen

- **A Range puts two Boards in one camera's view, or touching Targets on a
  Board.**
- **A one-Target live run logs Lost Looks from the silhouette check** often
  enough to drop due frames late at `LIVE_STRIDE`.

Start from #288. It has the timings, and the probe that seeded the check from
every contour.

## Prior requests

- #288: "Registration: make the gross-fit silhouette check cheap enough not
  to set the stride"
