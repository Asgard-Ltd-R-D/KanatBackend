# The baseline fit is affine

Board space is built from the baseline frame by fitting the template's green
silhouette to the reference Target's (`board.build_view`). That fit is now an
affine (`cv2.MOTION_AFFINE`, six parameters) instead of a full homography.
Every later frame is still registered to the baseline frame by an ECC
homography on the Board's texture (#50), so H = W · H0 can still carry
perspective. Only H0 cannot. Decided 2026-11-03 in #296.

## Why

The silhouette does not constrain a perspective term (#295). On CamB the
homography's image scale grew 12–25% from the sheet's left edge to its right,
while CamA's stayed flat (0.997). Forcing an affine fit cost at most 0.003 of
ECC correlation and drew the paper square. `_101550`'s fit was degenerate, with
its vanishing line inside the template. The spurious tilt put `_102450`'s
off-paper hole 0.24 mm inside the 5 mm sheet bound (ADR-0011), where it was
reported as a Miss.

## Measured (#296, main 5ead14d against the change, same settings)

| | main | affine |
|---|---|---|
| R/L image scale across the sheet, CamB | 1.115–1.254 (`_101550` 2066) | 1.000 |
| `_102450` off-paper Miss, stride 4, starts 0–31 s | reported from 14 of 32 | 0 of 32 |
| `board_move` | 30/32 | 32/32 (`mid-102250 turn2` s4 and s1 now pass) |
| Regression, stride 4 | baseline | no truth hole lost; `_102250` duplicate FP gone |
| Regression, stride 1 | baseline | CamA #5 lost (52% persistence on main, under 50% here) |
| Position error, radial mean | CamA 1.1, CamB 1.3 mm | CamA 0.9, CamB 1.4 mm |

The CamA #5 loss sits on the persistence threshold. CamA's fit barely changes
(R/L 0.997 → 1.000, same correlation), and the sub-pixel shift tips the
Candidate from 52% to under 50%. Stride 4, the live stride (ADR-0007), finds
it on both sides.

The printed 10-ring still reads 194–210 template px on CamB against CamA's
231. The CamB scale bias is not the perspective term, and #297 owns it.

## Considered

- **Keep the homography and tighten the sheet bound.** Rejected in #295:
  CamA #2 and #3 tear the paper's edge 4.3 and 2.6 mm off the fitted sheet,
  so the bound alone cannot separate them from the off-paper hole.
- **Affine everywhere.** Not needed. Frame-to-frame tracking fits the Board's
  texture, which does constrain perspective. The re-anchor seed,
  `silhouette_disagreement`, `residuals` and the tools' photograph and truth
  registration stay homographies, so ground truth is derived as before.
