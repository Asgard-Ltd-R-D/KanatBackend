# Kanat

A shooting-range analysis system: it ingests live weapon and motion telemetry,
and detects bullet holes on paper targets from range camera footage.

## Language

### Sessions and telemetry

**Range**:
One recorded shooting session, from start to stop. Owns the events, hits and
targets captured during it.
_Avoid_: session, run

**Shot Distance**:
The distance from a hit to its target's centre, in centimetres.
_Avoid_: range, mean range

### Vision

**Board**:
The physical backing sheet a shooter fires at. Carries one or more Targets.
_Avoid_: paper, sheet

**Target**:
A single printed aiming mark on a Board. A Board commonly carries several.
_Avoid_: bullseye

**Hit**:
One bullet's passage through a Board, as a physical event.
_Avoid_: shot, round

**Bullet Hole**:
The visible mark a Hit leaves on a Board. Distinct from a Hit: one Hit makes one
Bullet Hole, but overlapping Hits may be indistinguishable as Bullet Holes. A
Bullet Hole is on the Board whether or not anything saw it.
_Avoid_: hole

**Detection**:
The system claiming to see a Bullet Hole in a single frame. Evidence about that
frame, not about the Board: a Bullet Hole may go unseen for long stretches while
it is plainly visible, one may be seen as two, and a Detection may answer to no
Bullet Hole at all.
_Avoid_: hit, sighting, hole

**Miss**:
A Bullet Hole on a Board that falls outside every Target on it. A real Hit, and
counted as one, but carrying no Shot Distance and no score.
_Avoid_: stray, off-target hit

**Capture Profile**:
A named, reusable set of detection settings tied to one physical setup —
camera placement and zoom, distance to the Board, and calibre. Selected when a
Range starts; unchanged while the hardware stays put.
_Avoid_: range profile, lane profile, calibration
