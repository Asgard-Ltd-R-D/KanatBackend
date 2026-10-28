# Every recording may be opened, and each result says whether its footage was seen

No recording is held out any more. Any footage, listed in
`config/recordings.json` or not, may be run, watched, debugged, benchmarked and
tuned on. This supersedes the sealing in
[ADR-0005](0005-the-held-out-set-is-whole-capture-setups.md). Its ground truth
from photographs and its separation of detector from pipeline evaluation still
stand.

## Why

Sealing bought one held-out measurement and blocked everything after it. Of 26
recordings, 14 carried the `sealed` role. Twelve of those were never watched,
so they have no truth and no shooting window. The held-out set came to one
Capture Setup and two Bullet Holes. It was scored once (0 of 2, #31), and by
rule that result could not justify any change. Optimising latency and accuracy
together needs every recording for benchmarks and diagnosis. A gate that
refuses footage, and a log that makes a second look impossible, now cost more
than the one number they protect.

## What replaces it: a label on each result, not a gate

Every reported result names its footage and says which of two kinds it is:

- **Regression:** the footage was in view when something in the measured
  commit was chosen, whether a model, a constant or a threshold. It shows a
  change broke nothing it was checked on. It does not show the change works
  anywhere else.
- **Unseen:** the footage arrived after the measured commit and was scored by
  that commit before anything was changed on it. Only this counts as evidence
  of generalisation. It becomes regression as soon as anything is changed with
  it in view.

No tool enforces the label; the report states it. On 2026-10-28 every
recording with truth is regression, and no unseen evidence stands: the sealed
run's 0 of 2 measured a system that has changed since. A generalisation claim
to IAI (SOW 2.3.6) therefore needs footage that has not arrived yet: the AXIS
camera's first Ranges, or the next customer delivery, scored once before
anything is tuned on it.

## Consequences

- `config/recordings.json` stays as metadata: the Capture Setup, which picks the
  print scale, plus the fps and the window. `role`, `data/sealed_runs.log`,
  `--final-run` and the gate's refusals go. An unlisted recording runs, but it
  has no window and no Capture Setup until it is listed.
- The passages in ADR-0003, ADR-0006 and ADR-0007 that cite the sealed run, or
  refuse to re-measure because of it, stay as history. ADR-0003's
  end-of-run Change Evidence check can now be re-measured. ADR-0007's stride
  table can be re-run on more footage.
- Capture Setup remains the unit evidence is counted in. Three files from one
  afternoon on one camera are one setup's evidence, whichever label they carry.
