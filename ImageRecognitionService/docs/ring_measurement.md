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
