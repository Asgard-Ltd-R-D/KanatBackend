# The printed 10-ring, in millimetres

**Measured 2026-10-04.** Issue #62. A fresh A4 print of
`data/targets/kanat_silhouette_a4.png` (sha256 `0b4e8cb4…f68170`), printed with
*Scale to Fit*, landscape, and photographed with a tape measure along both axes
of the Target:

- [`side_to_side.jpg`](ring_measurement/side_to_side.jpg): the tape runs shoulder
  to shoulder over the left half of the white 10-ring.
- [`head_to_feet.jpg`](ring_measurement/head_to_feet.jpg): the tape runs head to
  feet. Its millimetre edge lies along the 10-ring's widest chord.

It is the repo artwork. It registers at ECC 0.999, against 0.990 for the
lookalike under "What the value depends on", item 3. The print app and printer
model were not recorded.

## Result

| | Side to side (template x) | Head to feet (template y) |
|---|---|---|
| Print scale, mm per template px | 0.1758 | 0.1768 |
| Printed white 10-ring | 37.9 mm | 39.1 mm |

The printed white 10-ring is the second row. Millimetre output takes the first:
the print scale, passed as `--mm-per-px` or configured per Capture Setup in
`config/print_scale.json` with its source (#69). The ring's ruler reading is not
it.

| Print | `--mm-per-px`, mm per template px |
|---|---|
| This one | **0.1763**, the mean of both axes |
| The earlier test print, under item 1 | **0.1810** |

The footage takes **0.1763**: on 2026-10-04 the user confirmed the Boards' Targets
were printed from this artwork with this A4 *Scale to Fit* setup. It is configured
for every CamA and CamB Capture Setup in `config/print_scale.json`.

## Method

The tape is not flat on the sheet. Its hook rests past the sheet edge, so the
blade sits above the sheet. Against the sheet's own edges it reads the 297 mm
side as 286.7 mm and the 210 mm side as 205.4 mm, 3.5% and 2.2% short. So the
sheet is the ruler: each reading is scaled by the sheet's A4 size along the same
line, and the tape only interpolates along it.

How each reading was taken:
- **Ticks.** The tape's millimetre ticks are located as a run of minima along its
  millimetre edge, to a fraction of a pixel.
- **Straight edges.** Each edge is fitted above and below the tape, as a line, or
  as an arc for the head. Its reading is where it crosses the tick run.
- **Head-to-feet 10-ring.** The widest chord sits just above the millimetre
  edge, so it is read directly.
- **Side-to-side 10-ring.** The tape covers half the disk, and its millimetre
  edge passes well off the centre. So a circle is fitted to the visible half. Its
  two extremes are carried 98 px across the blade, perpendicular to the tape on
  the sheet (the direction the body sides give), to the tick run.

Readings, in tape millimetres:

| Edge | Side to side | Head to feet |
|---|---|---|
| Sheet | 6.1 → 292.8 (286.7) | 5.1 → 210.4 (205.4) |
| Target outline | body sides 61.1 → 238.4 (177.3) | head top 8.2 → feet 193.3 (185.1) |
| White 10-ring | 131.9 → 168.5 (36.6) | 97.5 → 135.7 (38.2) |

Scale = outline reading × (sheet mm ÷ sheet reading) ÷ outline in template px.
The outline is 1044.8 px between the body sides, and 1070.6 px from head top to
feet on the column the tape crosses.

## What the value depends on

**1. Which print path the Targets on the Boards came from.** The earlier test
print was the lookalike (item 3). It shares this artwork's 1405 × 1120 canvas, so
its scale is comparable. It was also A4 *Scale to Fit*, and came out at 0.1810 mm
per px, 2.7% larger. Its margins were about 3.6 mm per edge, against 6 mm here,
because fit margins depend on the app and its settings.
- **Same printer, probably.** Both prints sit about 4.5 mm off-centre in the same
  direction, which points to one printer with two fit settings.
- **What was reported about the Boards.** They were printed A4 *Scale to Fit* on
  the same printer as the earlier test print. That favours 0.1810, but this print
  shows "same printer" does not fix the scale. So the app or settings the Targets
  on the Boards went through decide between 0.1763 and 0.1810.
- **Settled 2026-10-04.** The user confirmed the Targets on the recorded Boards
  were printed from the repo artwork with the same A4 *Scale to Fit* setup as this
  print, so the footage takes 0.1763. 0.1810 belongs to the lookalike's print.
- **What the footage shows.** The spent CamA Board (`141546`) carries this
  artwork's 10-ring, not the lookalike's.

**2. `RING_DIAMETER_TPL` was not the disk.** The PNG's white 10-ring is 221.1 px
side to side and 224.6 px head to feet, at half-level edges. The constant was
227, 1.1–2.7% larger; #70 set it to 223.0, twice the disk's median radius
(`tools/ring_landmarks.py`). Three things follow:
- **The millimetre value was tied to the constant.** It was `--ring-mm`, the
  constant × the scale: 40.0 and 41.1 with 227. #69 replaced it with the scale
  itself, `--mm-per-px`, so the constant no longer reaches millimetres.
- **The CLI told people otherwise.** The `--ring-mm` help and the `NotCalibrated`
  message asked for the ring's ruler reading. Here that is 37.9–39.1 mm, which
  under-scales every millimetre figure. #69 fixed both.
- **Scoring uses the same reading.** `RING_RADII_TPL[0]` is half the constant
  and `score()`'s 10/9 boundary. At 113.5 it sat 1–3 px outside the disk. #70
  moved it to the artwork's disk edge, 111.5, and the ring lines past it to
  their measured centres, which had been stored 1.5–6 px small.

The printed disk also reads 1.6–2.4% under the artwork's, which is consistent
with ink spread. The scale therefore comes from the outline, which is what
registration fits.

**3. The lookalike.** A photo-like render of the Target ("Codex Image", sha256
`e2a0fcb3…`, not in the repo) shares the canvas. Its 10-ring is about 211 px, and
its background is grey. The first two attempts at #62 printed it. A grey
rectangle behind the silhouette means the wrong file.

## Where the sheet lies around the artwork

**Measured 2026-10-28.** Issue #271, for ADR-0011's bound: the Target Sheet plus
5 mm. Both photographs above, re-read for the sheet's four edges against the
green silhouette.

### Result

The artwork is not centred on the page. It sits **4.5 mm off-centre toward the
head**, 3.3 mm from the sheet's edge there and 17.4 mm at the feet. Across the
shoulders it is centred within 1 mm.

| Margin, mm | Side to side | Head to feet | Centred page predicts |
|---|---|---|---|
| Left body side (template x) | 55.4 | 55.7 | 55.1 |
| Right body side | 57.5 | 57.3 | 56.9 |
| Head apex (template y) | 3.2 | 3.4 | 8.0 |
| Feet | 17.4 | 17.4 | 13.0 |

The sheet in template px, the mean of both photographs (they agree within
2.6 px, 0.5 mm):

| | x0 | y0 | x1 | y1 |
|---|---|---|---|---|
| Fitted | **−145** | **−9** | **1548** | **1180** |
| Centred page at 0.1763 | −140 | −36 | 1545 | 1156 |
| Difference, mm | 0.9 | 4.7 | 0.5 | 4.2 |

Head and feet differ by more than 1 mm, so the fitted rectangle is configured
for every Capture Setup in `config/print_scale.json` (`sheet_tpl_px`, with its
`sheet_source`). The Boards' Targets were printed the same way as this print
(item 1 above).

### Why head and feet disagreed with the centred page

It is the page's placement:
- **Not the print scale.** The fit gives 0.1755 mm per template px along x and
  0.1766 along y, the scales measured above. Head and feet margins together
  come to 20.7 mm, against 21.0 mm for a centred page. The difference is in how
  they split.
- **Not this reading.** The tape readings above put the head 3.2 mm and the feet
  17.5 mm from the sheet's edges, within 0.2 mm of the fit.
- **The earlier eyeball reading was wrong at the head.** It gave 14.0 mm there
  and 17.7 mm at the feet. Both photographs show the head apex 3–4 mm from the
  sheet's edge.

The earlier test print sat about 4.5 mm off-centre in the same direction
(item 1), which points to the printer rather than to this sheet.

Across the shoulders the tape readings give 57.0 / 56.4 mm, 0.9–1.6 mm away from
the fit in opposite directions, with the same sum. That is a shift along the
tape, which fits the hook end's parallax. The fit does not use the tape.

### Method

`tools/sheet_fit.py` (`.venv/bin/python -m tools.sheet_fit`):
- **The sheet is the ruler.** Each of the sheet's four edges is fitted as a line
  through its outermost pixels, away from the tape, with a residual of 0.4–1.0
  px. The corners map the photograph onto a 297 × 210 mm page, which removes
  perspective.
- **The artwork is fitted onto the page.** The template's green mask is
  registered to the page's by an affine ECC (correlation 0.988–0.991), with the
  tape masked out. The silhouette's extremes give the margins: the body sides
  at template x 172.5 / 1221.5, the head apex at y 9.5, the feet at y 1081.5.
- **The page corners, carried back through the fit,** give the rectangle. Each
  side is the mean of its two corners. The fit is rotated 0.08–0.14°, which
  moves a corner at most 0.4 mm.

`tests/test_board.py` re-fits both photographs and checks the configured
rectangle against them.

### Against the Boards' own photographs

The after photographs of the recorded Boards show some sheet edges, but too
coarsely to fit them: about 1.3 mm per pixel on CamB, and blurred, low-contrast
edges on CamA. On `_102450`'s after photograph the head runs to the sheet's
top edge, which looks folded over it. Truth #1 there lies clearly above that
edge, off the sheet. The fitted page agrees (6.0 mm beyond the edge). The
centred page did not (1.3 mm).
