# The WebApp controls a Detection Service that stays running

The Detection Service is started once, beside mediamtx, in its own Python
environment, and stays up between Ranges holding the detector. The WebApp
backend starts and ends each Range's Run over an HTTP API on 127.0.0.1. A Run
is still one per Range, from its own baseline. This reverses
`WebApp/CONTEXT.md`, which kept starting, stopping and configuring detection out
of the WebApp.

## Why

Until now a live Run was a process launched by hand with `--session-id`, and it
ended only on a signal. A first version that started one per Session from the
backend reported about 11 s without detection at every Session start, and a
Python version error: the backend's environment (≥ 3.12) ran detection code that
CI tests on 3.11 and that only ever ran on 3.14.

The 11 s was not reproduced. On the development Mac (M1 Pro, CPU, yolo26n,
`main` 3e098b5, 2026-10-21, median of three fresh interpreters), launch to
baseline built takes 4.6 s against a replayed RTSP Stream:

| Part | Seconds | Staying up |
|---|---:|---|
| Imports (torch via ultralytics 0.62) and weights load | ~0.85 | saved |
| RTSP open, including the wait for a keyframe | 1.34 | per Run |
| Board space from frame 0 | 0.64 | per Run |
| Baseline, 5 Looks | 1.25 | per Run |
| First Look after the baseline | 0.3 | per Run |
| Persistence before a Confirmed Bullet Hole | ≥ 2.04 | per Bullet Hole |

Staying up saves 0.85 s of that here, about 1.5 s with the larger v2.0 or
yolo26m weights, plus whatever a launcher adds to every start. The rest belongs
to the Run: its baseline fixes where it places everything (`CONTEXT.md`,
**Run**), so it must come from the Range's own first frames. The case for
staying up is therefore not the seconds:

- **Detection code never runs in the backend's environment.** The Detection
  Service has its own, pinned to Python 3.14, and CI moves to it.
- **The backend has something to control.** Bullet Holes are lost when no Run
  watches while shots are fired, and nobody sees it. So the backend:
  - starts the Run when the Session starts. *Start* returns once the Run is
    watching, and the Session page shows it. A shot before that lands in the
    baseline and becomes a Baseline Mark.
  - re-asserts the Run every 5 s, as it re-applies mediamtx paths. A Run
    started late takes a fresh baseline, and the gap shows on the page.
  - ends the Run before it completes the Session. *End* returns once open
    Candidates are decided (at most one persistence window) and posts are
    drained, so the last shot is not dropped on a 409.

## Considered options

- **The backend spawns a Run per Session as a child process.** It pays imports,
  weights and the launcher every Session, ties detection to uvicorn's lifetime
  (`--reload` restarts on every save), and runs it in the backend's Python.
- **One Run that never ends, across Ranges.** No per-Range cost, but Baseline
  Marks are per Range: a Bullet Hole from one Range would be new in the next,
  or the Run would re-baseline mid-Run.
- **The Detection Service polls the backend for active Sessions.** It keeps the
  dependency pointing one way, as `POST /sessions/{id}/bullets` does, but adds
  a poll interval before the baseline even starts.
- **Arm the Run at the end of the previous Session.** No wait at Session start,
  but a Board swapped or re-hung between Sessions invalidates the baseline
  without a sign.
- **Keep each camera's Stream open between Runs.** Saves the 1.34 s RTSP open,
  at the cost of reading frames between Sessions and moving Stream ownership
  off the Run. Deferred until operators find the wait a problem.

## Consequences

**A Session names its camera.** Optional, and fixed for the Session's life.
Without one there is no Run. Disabling or deleting the camera ends the Run; the
Session goes on.

**One Run at a time.** A second Session that wants detection while a Run is
active gets none, and its page says so. Concurrent Runs need a detector per Run
or a lock around one (ultralytics models are not thread-safe), and the
process-wide signal handlers moved out of `Stream`
(`detection/new_bullet_holes.py:744`). That is its own decision, for when a
second camera arrives.

**Starting a Run carries the Session and the Stream, nothing else.** Model,
template, stride and print scale stay the Detection Service's defaults, so
`x_mm`/`y_mm` stay empty until a scale is configured. Per-camera settings are
the Capture Profile, not decided here.

**Nothing restarts it.** Like mediamtx, composer starts it detached, and
`/status` reports `detection_service` beside `video_service`. Reconcile
restores the Run within 5 s of it coming back.

**Every Range still waits about 3.7 s before it is watched**, and every Bullet
Hole at least 2.04 s for persistence
([ADR-0003](0003-a-bullet-hole-is-new-when-it-persists.md)). Staying up changes
neither.
