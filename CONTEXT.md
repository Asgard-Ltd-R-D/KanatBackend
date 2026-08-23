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
The visible mark a Hit leaves on a Board — what the vision model detects.
Distinct from a Hit: one Hit makes one Bullet Hole, but overlapping Hits may
be indistinguishable as Bullet Holes.
_Avoid_: hole, detection

**Capture Profile**:
A named, reusable set of detection settings tied to one physical setup —
camera placement and zoom, distance to the Board, and calibre. Selected when a
Range starts; unchanged while the hardware stays put.
_Avoid_: range profile, lane profile, calibration
