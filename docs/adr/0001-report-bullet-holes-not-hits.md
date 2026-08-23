# Report Bullet Holes, not Hits

The vision pipeline detects Bullet Holes — the visible marks on a Board — and
reports those. It does not report Hits. Two Hits passing through nearly the same
point leave one visible mark and are counted as one, because the information
needed to separate them is not present in a single frame.

## Considered options

**Temporal analysis across video frames** — track the Board over successive
frames and count a Bullet Hole as new when it appears where there was none
before, recovering the second Hit of an overlapping pair. Rejected: it is a
substantially larger change (frame-to-frame Board registration, per-frame state,
sensitivity to camera and Board movement) and stands outside this work. It
remains the upgrade path if true Hit counts are ever required.

## Consequences

Reported counts are a floor on Hits, not an exact count. This particular error is
one-sided — a tight group can be under-counted, never over-counted. It says
nothing about the pipeline's other error modes: a low confidence threshold emits
more boxes than there are Bullet Holes and over-counts.

This is a ceiling, not a defect. State it to operators and instructors rather
than letting them discover it: the system counts visible marks, not Hits. Shot
Distance figures derived from Bullet Holes carry the same caveat.

Under-reporting caused by anything *other* than overlapping Hits is a bug, and is
addressed separately — over-merging in de-duplication by
[ADR-0002](0002-single-de-duplication-gate.md), and a fixed inference size that
does not fit the capture by the Capture Profile work still open at the time of
writing.
