# Detection is limited to the Target Sheets

The system looks for Bullet Holes only on the Target Sheets, the printed pages
the Targets are on, plus 5 mm. A Hit anywhere else on the Board is not
detected, reported or scored. If it matters, the operator adds it by hand (the
WebApp's Manual source). A Miss now means a hole outside its Target, on a
sheet's white margin or within those 5 mm of its edge. Decided 2026-10-28, while planning the latency and accuracy
work.

## Why

Only the sheet counts. Restricting detection to it is also the cheapest
latency available:

- CamA's detector canvas is 1282×1636 px today. Cut to its two sheets, it
  becomes two equal crops that can share one batched call.
- The ECC region is ±1.5 Target spans around the ring, about 6× a sheet's
  area. It can shrink once nothing off the sheet needs placing.

It also takes away content the detector should not see. On #46, adding Board
around the canvas dropped `_103223` truth #2's confidence from 0.19 to 0.04.
The West Point zeroing paper (arXiv 2601.17062) reports the same direction:
detecting on the rectified target region beat detecting on the full image.

## The cost, measured

Of the 18 truth Bullet Holes on the six recordings with truth:

| Where the hole lies | Bullet Holes |
|---|---:|
| On a sheet | 10 |
| Within 1–4 mm of a sheet's derived edge | 3: CamA #2, #3; `_102450` #1 |
| 21–139 mm off every sheet | 5: CamA #6; `_102250` #1; `_103223` #1; `_102450` #3, #4 |

Those five, over a quarter of the Hits fired in the customer's footage, are no
longer reported. #46's Board bands, built to find `_102450` #3 and #4, go with
them.

## Where the sheet's edge is

The edge cannot be seen: it is white paper on a white Board (HANDOVER, "the A4
edge is unusable"). So it is derived. The sheet is taken as a landscape A4 page
at the Capture Setup's print scale, centred on the artwork. For the reference
Target that is template x −140…1545, y −36…1156; every other Target gets the
same page about itself.

The 5 mm allows for three things: the edge is derived, not seen; SOW 2.3.2
allows 5 mm of placement error; and a 5.56–9 mm hole that close still tears the
sheet.

The centring is not yet confirmed. An eyeball check on #62's photograph
(`ImageRecognitionService/docs/ring_measurement/side_to_side.jpg`) agrees within
2 mm across the shoulders. At head and feet it finds 5–6 mm more margin than the
centred page predicts. Fit it properly before the bound is fixed in code.

## Considered options

- **The Board, as before.** Every Hit stays reported, and latency comes only
  from ECC's settings. Rejected because only the sheet counts.
- **The artwork's own bounds.** This cuts the sheet's ~25 mm side margins, where
  three truth holes lie.
- **Finding the edge in the baseline frame.** It merges with the Board under
  every threshold tried.

## Consequences

- Truth holes more than 5 mm off every sheet are left out of scoring and
  listed as out of scope, not counted as misses. Regression results run on 10–13 holes, not 18.
- ADR-0001's reported counts were a floor on Hits. They are now a floor on Hits
  on the sheets.
- Registration only has to place points on the sheets. #50's Board-texture
  region may shrink, if on-sheet placement holds under the regression rule.
- This reverses #46's bands, and the canvas moves on the model's grid. Marginal
  holes will flip, and the 8/16/32 px canvas-shift control decides whether a
  flip is noise.
