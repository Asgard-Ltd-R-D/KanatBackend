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

The main side ran in a worktree whose only changes were symlinks to the
git-ignored models and test data, so `compare` labels it `5ead14d-dirty`.

| | main | affine |
|---|---|---|
| R/L image scale across the sheet, CamB | 1.115–1.254 (`_101550` 2066) | 1.000 |
| `_102450` off-paper Miss, stride 4, starts 0–31 s | reported from 14 of 32 | 0 of 32 |
| `board_move` | 30/32 | 32/32 (`mid-102250 turn2` s4 and s1 now pass) |
| Regression, stride 4 and 1 | | no truth hole lost at stride 4; `_102250` duplicate FP gone at both |
| CamA #5, stride 1 | TP at 52% persistence | missed (under 50%) |
| Radial error, holes found on both sides | | `_101450` #1 1.1 → 1.4 mm (moved 1.7 mm: the bench's one FAIL); `_102250` #4 1.8 → 1.4; the rest within 0.4 mm |

The `_102250` FP was a second report of truth #4: found at template (524, 836),
28 px from the report matched to #4 (551, 831), on the same hole (543, 824).

`_101450` #1 moves because H0 moved: on CamB the affine fit places Board
space differently, and `compare`'s 1 mm limit assumes unchanged geometry.
Its radial error grows 0.3 mm, while `_102250` #4's shrinks 0.4 mm. No CamB
hole leaves the 5 mm figure.

CamA's fit barely changes (R/L 0.997 → 1.000, same correlation), but the
detector is sensitive to sub-pixel changes in the canvas (#46, #299). The same
holes' persistence moves both ways: at stride 4, #3 85 → 69% and #5 92 → 77%,
but #1 85 → 92% (#2 unchanged at 85%). CamA #5 at stride 1 sits on the 50% threshold and tips
under it. At stride 4, the live stride (ADR-0007), it is found on both sides.
CamA #2 and #3 are detected and in scope at both strides.

No run, on either side, re-anchors: the move cases are tracked without a lost
frame. Re-anchoring is covered by the unit tests alone, and its seed
(`reanchor_view`'s silhouette fit) stays a homography.

`_101550` stays unusable: its correlation is 0.62 (0.64 on main), and the
10-ring cannot be read on either fit.

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
