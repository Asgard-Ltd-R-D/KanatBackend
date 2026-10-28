# Kanat

A shooting-range analysis system: it ingests live weapon and motion telemetry,
and detects bullet holes on paper targets from range camera footage.

## Language

### Sessions and telemetry

**Range**:
One recorded shooting session, from start to stop. Owns the events, hits and
targets captured during it. A Range may start on a Board that already carries
Bullet Holes from an earlier Range. The WebApp names it a Session, in its code
and on screen; it is the same thing.
_Avoid_: session (outside the WebApp), run (the system watching footage is a
Run), act, firing act, range (for the physical site: the range site)

**Shot Distance**:
The distance from a Bullet Hole to its Target's centre, in millimetres.
_Avoid_: range, mean range

### Vision

**Board**:
The physical backing sheet a shooter fires at. Carries one or more Targets.
_Avoid_: paper, sheet

**Target**:
A single printed aiming mark on a Board. A Board commonly carries several.
_Avoid_: bullseye

**Target Sheet**:
The printed page one Target's artwork is on, fixed to a Board. The white
margin around the artwork is part of the sheet, not of the Target.
_Avoid_: A4, page, paper

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

**Recording**:
Footage saved to a file and read back at will: from any point, every frame
available, never late. Only a Recording can be scored against truth.
_Avoid_: clip, file, video

**Stream**:
Footage read live, from wherever it has reached, at the pace it arrives. The
system can be late for a Stream's frames, and frames can be lost before they
arrive. A Recording replayed through the video service is a Stream.
_Avoid_: feed, live source

**Run**:
The system watching footage once, from its baseline frame to its end. The
baseline frame fixes where on the Board the Run places everything it reports:
places from one Run compare directly. Two Runs may register to different
Targets, so places from two Runs compare only through a frame both share: the
camera's picture, or the artwork of one and the same Target. A Range is
watched live by one Run at a time, and by a fresh one after a Run is lost; a
Recording may have many.
_Avoid_: pass, execution, session

**Baseline View**:
Where a Run's baseline frame showed the Board in the camera's picture: how the
Target artwork lay on the picture, the outline of each Target, and the
Baseline Marks. The outlines and Baseline Marks are places on the Board and
hold for the whole Run; where the Board sits in the picture does not, since the
camera creeps and the Board sways or moves.
_Avoid_: geometry, homography, calibration

**Detection Service**:
The system that stays running and holds the detector, and watches each Range
with a fresh Run when the WebApp tells it to. It outlives its Runs: between
Ranges it holds the detector and watches nothing.
_Avoid_: model, detection model, worker, IRS

**Look**:
One frame the system examines for Detections. Live, it looks at a fixed
fraction of the frames and skips the rest (ADR-0007); a skipped frame yields no
Detections and is a gap, not evidence that nothing was there.
_Avoid_: processed frame, sample

**Registration**:
Placing a Look's frame onto the Board as the baseline frame showed it, so that
positions taken from different frames are comparable.
_Avoid_: alignment, tracking

**Lost**:
A Look whose frame could not be registered, or registered onto the wrong scene
altogether. No evidence either way: unlike a Look that saw nothing, it says
nothing about what was on the Board.
_Avoid_: dropped, failed frame, missed frame

**Board Move**:
A sudden change in where the Board sits in the camera's view that persists
afterwards: the stand bumped, the Board re-hung, or the camera re-aimed. The
system cannot tell which moved; only the Board's place in the view changed.
Distinct from the camera creeping, which is gradual, and from the Board swaying
in wind, which comes back.
_Avoid_: jump, re-aim (for the general case)

**Baseline Mark**:
A place on the Board where the baseline Looks showed a Detection, taken to be a
Bullet Hole already there when the Range started. The system's claim, not
truth: a speck the baseline saw is one, and a Bullet Hole it missed is not. A
Baseline Mark is never reported as new in that Range.
_Avoid_: pre-existing Bullet Hole (when the claim is meant), baseline hole,
prior hit

**Candidate**:
Detections from successive Looks at one place on the Board with no Baseline
Mark, gathered while the system decides whether they are a new
Bullet Hole. Most never become one.
_Avoid_: track, blob, hypothesis

**Persistence**:
A Candidate being seen in enough of the Looks over a fixed window after its
first Detection (ADR-0003). It separates a Bullet Hole, which appears once and
stays, from gravel and shadow, which flicker.
_Avoid_: tracking, stability

**Change Evidence**:
A visible change on the Board since the baseline frame, where a Detection lies.
Evidence for a Detection the model already made, never what chooses where the
model looks (ADR-0003). A Candidate that Change Evidence saw is corroborated.
_Avoid_: corroboration, change mask, absdiff

**Confirmed**:
A Candidate the system has judged to be a new Bullet Hole: it persisted, and
Change Evidence corroborated it, unless the Run was told to accept persistence
alone. Reported once and never retracted (ADR-0004). A Candidate that persisted
but still awaits Change Evidence is persisted, not Confirmed.
_Avoid_: accepted, validated, detected

**Inference Time**:
The time one Look spends in the detector, summed over every call the detector
makes on that Look. Not the time one call takes: a Look may need several. A Lost
Look has none, not zero: no detector ran, and its cost is in its Look Time.
_Avoid_: latency, model time

**Look Time**:
The time one Look takes from its frame reaching the system until its
Detections have been judged for persistence: registration, the detector and
every filter. Excludes receiving and decoding the frame, and the time it waited
to be looked at. Contains the Look's Inference Time.
_Avoid_: latency, frame time, processing time

**Frame Wait**:
How long a live Look's frame, once received and decoded, waited before the
system started looking at it. Only the wait inside the system: the time the
frame took to arrive — the camera, the network, the video service, the
buffering ahead of the decoder — is end-to-end latency, not Frame Wait.
_Avoid_: latency, lag, buffering, delay

**Miss**:
A Bullet Hole on a Target Sheet, or within 5 mm of its edge, that falls
outside the Target printed on it. A real Hit, and counted as one, but carrying
no Shot Distance and no score. A Bullet Hole further than 5 mm off every Target
Sheet is not a Miss: the system does not look there (ADR-0011).
_Avoid_: stray, off-target hit

**Position**:
A Bullet Hole's offset from its Target's centre, as (X, Y) in millimetres along
the Target's printed axes, not the camera's. Its length is the Shot Distance. A
Miss has no Position.
_Avoid_: hit coordinates, location, point of impact

**Position Error**:
The error in where the system places a Bullet Hole on the Board, per axis
along the Target's printed axes: the system's place minus the true one. For a
Bullet Hole on a Target, it is the error in its Position; a Miss has one too.
Only as independent as the truth it is measured against: truth carried into
the footage's own frame of reference shares its registration to the artwork
and its print scale, so errors in those cancel out of it.
_Avoid_: accuracy, localisation error, offset error

**Group**:
The new Bullet Holes on one Target during one Range, after the operator's
corrections. Bullet Holes that were already on the Board when the Range
started, and Misses, belong to no Group. Since a Group counts Bullet Holes,
not Hits, a tight Group can be under-counted (ADR-0001); its MPI, CEP and
Extreme Spread carry the same caveat, with no fixed direction of error.
_Avoid_: grouping, cluster, string

**MPI** (Mean Point of Impact):
The mean position of a Group's Bullet Holes, as an offset from the Target's
centre in millimetres.
_Avoid_: centroid, group centre

**CEP** (Circular Error Probable):
The radius of the circle around the MPI that contains half the Group's Bullet
Holes. Where another dispersion measure is meant, it is named: Mean Radius
(the mean distance from the MPI) or RMS radius.
_Avoid_: dispersion, spread radius

**Extreme Spread**:
The largest centre-to-centre distance between any two Bullet Holes of a Group.
_Avoid_: group size, max spread

**Capture Profile**:
A named, reusable set of detection settings tied to one physical setup —
camera placement and zoom, distance to the Board, and calibre. Selected when a
Range starts; unchanged while the hardware stays put.
_Avoid_: range profile, lane profile, calibration

**Capture Setup**:
One physical arrangement that footage was shot in — camera pose, Board,
lighting, distance. The unit evidence is counted in: three files from one
afternoon on one camera are one Capture Setup, and a result on all three is one
setup's evidence, not three. Distinct from a Capture Profile, which is the
settings chosen for a setup rather than the setup itself.
_Avoid_: scene, clip, session

**Registration Displacement**:
A Detection reported at the wrong place on the Board because the frame
registered imperfectly, not because the detector was wrong. A pre-existing
Bullet Hole displaced far enough stops matching the baseline and is reported as
a new one — a false positive that persists perfectly, which persistence is
structurally unable to filter. Named as one of the three causes a false positive
is attributed to, beside the detector and `unknown`.
_Avoid_: drift, registration error, misregistration
