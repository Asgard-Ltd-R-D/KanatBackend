# Every Bullet Hole has a Position

There is no Miss. A detected Bullet Hole belongs to the Target whose outline
holds it, or else to the Target printed on the Target Sheet it lies on (its
bound, 5 mm included, ADR-0011). It is measured from that Target's centre like
any other, so it has a Position in millimetres and is in that Target's Group.
This replaces the Miss of ADR-0011, a hole outside its Target that carried no
millimetres, no score and no Group. Decided 2026-11-26 in #422.

## Why

The operator wants every new Bullet Hole's X and Y in millimetres, whether or
not it hit the silhouette. No SOW item asks for a Target/Miss verdict. Each
sheet carries exactly one Target, and detection only looks on the sheets, so
"which sheet" names a Target for every detected hole with no new geometry.
The millimetres are the existing ones (`board.to_millimetres`); only
`BoardView.assign` changed.

## Consequences

- A wide shot now widens its Target's Group: MPI, CEP and Extreme Spread
  include it.
- An off-outline hole scores "outside rings" (`board.score`), as one inside
  the outline beyond the 6-ring already did.
- The Overlay draws every detected new Bullet Hole in one colour.
- Rows stored as Misses before #422 have no Target or millimetres. They are
  not backfilled and are counted as Bullet Holes without a Position.
