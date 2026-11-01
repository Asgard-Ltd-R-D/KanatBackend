# Late drops in the catch-up after the baseline

The live reader drops some due frames late in the catch-up after the
baseline. Nothing is built to keep them: no queue for the catch-up, and no
decoding through the baseline. Late drops after the Run goes `watching` are
still counted, and they still fail #277's criterion.

## Why this is out of scope

Shots count only from "Detection ready", which the Session page shows once the
Run goes `watching` (`WebApp/CONTEXT.md`). The Detection Service answers
`watching` only once the baseline is built.

The catch-up decodes a backlog of older stream time. Until the loop asks for
its first frame past the baseline, the reader blocks, and building Board space
takes about 2.3 s (about 57 frames at 25 fps). Then the reader decodes the
backlog faster than real time, and newest-wins drops due frames from it. The
frames it drops show the Board before the baseline was built, so before any
shot counts. Frame times run about 1.2 s late (#85), which only makes the
margin larger.

Measured 2026-11-01 on `main` at 600c1bd, CPU, through MediaMTX by
`docs/latency_wip.md`'s procedure, at stride 6:

| Replay | Late drops | Frames |
|---|---:|---|
| CamB `_102250` | 4 | 12–30 |
| CamB `_101550` | 5 | 12–36 |

Every drop fell 0.5–1.4 s into the stream, about a second before the baseline
was built. There were none after the catch-up. #132's stride-17 replay had 3,
also in the catch-up.

So #277's criterion is "drops no due frame late after the Run goes
`watching`", and #291 splits the live report's late drops at that moment.

## What stays uncovered

- **A shot fired before "Detection ready".** Past the baseline frames it is
  reported as a new Bullet Hole, and catch-up drops in its window weaken its
  persistence. The page already says shots count only from Ready.
- **The first shot after Ready is looked at late.** Its frame waits until the
  reader reaches it, up to the catch-up time behind the stream. Frame Wait
  excludes this. #291 reports it.
- **#117's start-up loss.** The reader still blocks through the baseline, so
  MediaMTX may still discard for it. Those frames are before Ready too.

## When to reopen

- **A live replay or run drops a due frame late after `watching`** in the
  catch-up (#291's split shows it).
- **The catch-up delays the first shot after Ready** past what the SOW's
  latency allows, once 2.3.1 defines it.

Start from #290. It describes the two ways to keep the catch-up's frames.

## Prior requests

- #290: "Live reader: drop no due frame in the catch-up after the baseline"
