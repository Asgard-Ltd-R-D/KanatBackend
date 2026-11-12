# WebApp — Domain Context

Read this before working on anything in `WebApp/`. For the detection pipeline's domain (Bullet Hole detection, Board geometry, registration, persistence), see `ImageRecognitionService/HANDOVER.md` and `docs/adr/`.

---

## What this is

The WebApp is the operator-facing layer for a live shooting range. It consists of:

- **`backend/`** — Python + FastAPI service. Tells the Detection Service when to watch a Session, receives the confirmed Bullet Hole detections, stores them per Session in SQLite, and serves a REST API to the frontend.
- **`frontend/`** — Electron desktop app (React + TypeScript + Vite + Tailwind). The operator uses it to start and close Sessions, review results, and export reports.

The two components in this repo that matter for day-to-day range operation are `ImageRecognitionService/` (the Detection Service) and `WebApp/` (everything the operator touches). The others (`PacketProcessingService/`, `Composer_cli/`, `MotionSimulator/`) are out of scope here.

---

## Glossary

**Session**
The WebApp's name for a Range (see the root `CONTEXT.md`): one shooting session at the range site, from start to stop. An operator starts a Session before firing begins and closes it when done. A Session has a `status` of `active` or `completed`. At most one Session is active at a time: starting a Session, or reopening a completed one, while another is active is refused (409, naming the active one), the session list's New Session button is disabled meanwhile, and the database holds it too, for two requests at once (`uq_sessions_one_active`, a unique index on the active rows). All Bullet Holes reported during a Session belong to it. A Session is the unit of export (PDF report) and the unit displayed in the session list. A Session spans every enabled camera, one board each: the Detection Service watches them all at once, and each Bullet Hole names the board it was seen on by that camera's alias (`bullet_holes.camera_alias`; the Session no longer names a single camera, `sessions.camera_id` is gone), placed on that camera's picture from the baseline of the Run that reported it. A Session with no enabled camera has its Bullet Holes added by hand. Deleting a camera leaves the Bullet Holes it already reported on their board (the alias stays on them), off any live camera.

**Detection** (of a Session)
Whether a Run of the Detection Service watches the Session: `none` (no camera), `starting`, `watching` (the Session page says "Detection ready": shots count from here), `not_watching` with its reason (the Detection Service did not answer, the Run failed on the Stream, another Session's Run still holds the service, until the next reconcile ends it, or the Session's camera was disabled or deleted; none for a Run lost while the service answers, until it is started again), `ending` (the page says "Closing…"), or `end_unconfirmed`. When a Session starts, the backend answers at once with each enabled camera's board `starting` and asks the Detection Service for a Run on each camera's `rtsp://127.0.0.1:8554/<alias>` in the background; the Detection Service answers once each Run's baseline is built, a few seconds later. Completing the Session ends every board's Run first, while the Session is still active: a Run looks on until every Candidate it has open is judged, opening none, up to about 3 s, so a Bullet Hole fired just before the end is still posted and stored. If the Detection Service does not answer the end within 15 s, or no longer has the Run, the Session completes anyway. If a Run watched it and no end of its Run has been confirmed since, even if it reads not watching by then, it reads `end_unconfirmed` (its last shots may be missing) until it is reopened. Every 5 s, beside the camera sync, the backend reconciles the Detection Service's Runs with the boards to watch: one Run per enabled camera of the active Session, there being one active Session at a time. It ends a Run of any other board — another Session's (one completed while the Detection Service could not be told), or one whose camera was disabled or deleted — and starts a board that has none, so a Run lost to a restart or a failed Stream comes back by itself, and a reopened Session is watched again. Each new Run takes a fresh baseline: anything fired while none watched is a Baseline Mark, which the operator adds by hand. After re-hanging a Target Sheet, the operator retakes that board's baseline (its Retake baseline button, `POST /sessions/{id}/baseline/{camera}`): that board's Run is stopped, its open Candidates dropped unposted rather than judged as at completion (they are the re-hang's change, not shots), and a new one is asked for at once, the Session staying active. If the stop goes unanswered, no new Run is asked for (the old one would be handed back): the Session reads not watching, and the next tick that finds the old Run stops it before starting a new one. It reads `starting` from the click until the new Run is watching, so Detection ready shows only once the new baseline is built, and no tick starts or ends a Run in between; it is refused (409) unless the Session is active, its camera enabled, and no start or end is under way. The holes already on the sheet are the new Run's Baseline Marks, so none is reported twice. The state is held in the backend's memory (`backend/app/services/detection_sync.py`, the client is `detection_client.py`), returned with the Session and pushed on its live stream.

**Bullet Hole** (web app sense)
A confirmed detection reported by the Detection Service to the backend. One row in the `bullet_holes` table. Carries a position (template coordinates x/y), the absolute timestamp when it was first detected (`first_seen_at`), a source (`"model"` or `"manual"`), and an insertion-order rank within the session. Optional fields (`target_index`, `x_mm`, `y_mm`) are populated when the Detection Service provides them. Ring scores, target/miss classification, and per-detection confidence/frame metadata are outside the current WebApp scope.

This is distinct from a **Hit**: two bullets through the same point leave one Bullet Hole. The system counts Bullet Holes, not Hits. See `docs/adr/0001-report-bullet-holes-not-hits.md`.

**Group** (web app sense)
As in the root `CONTEXT.md`: one Target's Bullet Holes, with their MPI, CEP (beside it Mean Radius and RMS radius) and Extreme Spread, in millimetres. A completed Session shows one Group per Target on its page and in its PDF and Excel exports. The backend computes them from the Session's stored Bullet Holes each time it is read (`backend/app/services/groups.py`, ported from the Detection Service's `detection/groups.py`), so the operator's corrections apply: a deleted Bullet Hole leaves its Group. A Group takes the Bullet Holes with a `target_index` and both `x_mm` and `y_mm`. The Misses, and the Bullet Holes without a Position (every manual one, since its form takes no Target or millimetres, and a detected one when the print scale is not configured), are in no Group and are counted beside them. An active Session shows none.

**Template coordinates**
The coordinate system of the printed Target artwork (`ImageRecognitionService/data/targets/kanat_silhouette_a4.png`, 1405×1120 px), laid over the whole Board through its largest Target, the one a Run registers to. Which Target that is can change from one Run to the next (#240), so two Runs' coordinates compare only through the camera's picture. All Bullet Hole positions are reported and stored in these coordinates. The artwork bounds only that one Target: a Bullet Hole on another Target, or a Miss beyond the artwork, lies outside 0–1405 × 0–1120. It is stored there all the same; rows stored before #241 were clamped onto the artwork's border and stay there.

**Target / Miss**
A Bullet Hole is a **Target** hit if it landed on a scoring silhouette. It is a **Miss** if it hit a Target Sheet (the printed page a Target is on), or within 5 mm of its edge, outside its Target; nothing further than 5 mm off every Target Sheet is detected (root `docs/adr/0011-*`). Ring scores 6–10 are Target hits; score 0 is a Miss.

**Capture Setup / mediamtx**
The WebApp configures the cameras, and starts and ends the Detection Service's Runs, but not the Detection Service itself. The operator enters each camera (alias, multicast group and port, network interface) in Settings; the alias is fixed once the camera exists, since it names the camera's stream (`rtsp://<host>:8554/<alias>`, which the Detection Service reads), so it is unique whatever its case and never a name Windows keeps for a device (`CON`, `NUL`, `COM1`...); the backend stores them in the `cameras` table and keeps mediamtx in step through its Control API (`backend/app/services/camera_sync.py`): each enabled camera becomes a mediamtx path whose source is the camera's H.264 RTP multicast (`udp+rtp://group:port?interface=card`), which mediamtx joins and reads directly, so no GStreamer runs. A disabled camera keeps a sourceless path, its name reserved. The paths `mediamtx.yml` defines (e.g. `loopdemo`) belong to mediamtx: the backend reads their names from the file and never patches or deletes them, and refuses a camera of the same name. Paths added through the API live only in mediamtx's memory, so the backend re-applies them on startup and every 5 s. The live camera view in the frontend is a WebRTC stream from mediamtx per enabled camera (WHEP, `frontend/src/components/Camera/WhepPlayer.tsx`), retried every 5 s while a camera has no signal.

**The backend runs on the same PC as mediamtx, not in a container.** It reaches mediamtx's Control API on 127.0.0.1. So the compose files run only its database; the backend is started on the PC (`uv run uvicorn ...`, see CLAUDE.md), as the installer will.

**Overlay**
The Session's Bullet Holes, numbered by rank as in the log and coloured Target, Miss or manual, and its Run's Baseline View (the Target outlines, and the Baseline Marks in grey), drawn by the frontend over the live picture of the board's camera, where the Run's latest Registration places the Board in the picture, read every 5 s (`docs/adr/0009-overlays-are-drawn-by-the-frontend-from-each-runs-baseline-view.md`). A Baseline Mark that a drawn Bullet Hole stands for is not drawn. The operator can turn it off to see the bare picture. While no Run watches a board (before its first Run, or between a lost Run and the next, or unless its detection reads `watching` or `ending`) there is none.
_Avoid_: annotation, markers (for the whole), burn-in

**API contract**
The JSON schema the Detection Service uses when calling `POST /sessions/{id}/bullets`. Defined in `backend/docs/api_contract.md` and versioned (`v1`). The backend rejects any payload whose `version` field does not match.

---

## Architecture

```
Camera
  └─► mediamtx (VideoService) ──WebRTC (WHEP)──► Frontend (Electron) — operator watches live
            │
            ▼ RTSP stream
  ImageRecognitionService (Detection Service)
            │
            │  POST /sessions/{id}/bullets  (one call per confirmed Bullet Hole)
            ▼
       WebApp/backend  (FastAPI)
            │
            ├─► SQLite — sessions, bullet_holes, cameras, runs tables
            │
            ├─► Detection Service control API (127.0.0.1:8010) — start a Session's Run, end it,
            │   and read its status every 5 s to reconcile the Run with the Session to watch.
            │   The run view carries the Run's Baseline View once it is watching (ADR-0009); the
            │   backend stores each Run the first time it sees it watching, before it pushes
            │   `watching`, as a `runs` row with the camera's alias. The run view, and the end's
            │   answer, also carry how far it watched (`registered`, `looked_at`): each moves the
            │   row's `watched_until` on, and keeps the place once it moved more than 2 px at the
            │   Target outlines, then pushes `run_moved`
            │
            ├─► mediamtx Control API (127.0.0.1:9997) — camera paths
            │
            ├─► GET /sessions, GET /sessions/{id} (with its Runs, for the Overlay), GET /sessions/{id}/export/pdf
            │
            ├─► GET /sessions/{id}/live (Server-Sent Events) — pushes each change to the frontend
            │
            ├─► GET /status — whether mediamtx and the Detection Service are up, for the frontend's
            │   status indicator: from each one's last answer (under 12 s old), asking it only without one;
            │   and the detector's device and model, as the Detection Service's last status answer named them
            │
            └─► logs/backend.log ──┐
            logs/frontend.log ─────┼─► the app's Logs tab reads the files
            logs/detection.log ────┘   (WebApp/frontend, electron/logreader.ts)
```

---

## Key design decisions

**Live detections are pushed, not polled.** While a Session is active, the frontend holds a Server-Sent Events stream from `/sessions/{id}/live` (`backend/app/routers/live.py`). Live traffic only ever goes backend → frontend: corrections to a Session's Bullet Holes happen after it ends. The backend pushes an event when a Bullet Hole is created or deleted, the Session's status changes, or its detection does (`backend/app/schemas/live.py`); the frontend applies it to the session it already holds (`frontend/src/hooks/useSessionLive.ts`). The browser reconnects a dropped stream by itself, and on every (re)connect the frontend refetches the Session once, so nothing published while it was not listening is lost. The backend pings an idle stream every 15 s; after 40 s without a ping or an event the frontend assumes a frozen backend and reconnects. uvicorn must run with `--timeout-graceful-shutdown`: an open stream never finishes, and without it a restarting backend never exits and keeps the frontend attached to it. It must also run a single worker: the open streams live in that process's memory, so with several workers a bullet reported to one never reaches a frontend listening on another. A detection reaches the screen as soon as the backend stores it; the delay that remains is the Detection Service's own persistence window. The camera stream is separate: WebRTC, handled by the browser's video player.

**Bullet Holes arrive slowly.** The Detection Service requires a 25-frame persistence window (~1 second at 25 fps; a clean one is confirmed after ~0.5 s) before confirming a Bullet Hole. Confirmed detections arrive seconds apart, not milliseconds. The backend endpoint for receiving them does not need a queue or any special throughput design.

**The frontend is an Electron desktop app**, not a web app. It is installed on the operator's machine at the range site. It talks to the backend over 127.0.0.1 (not `localhost`, which on Windows tries IPv6 first). There is no public internet exposure. `npm run dist:win` builds its Windows installer (electron-builder, NSIS); installed, it reads `kanat-config.json` from its user's folder, else `%ProgramData%\Kanat`, and runs once at a time.

**PDF export is backend-generated.** The frontend calls `GET /sessions/{id}/export/pdf` and receives a file download. The backend renders the PDF using WeasyPrint from an HTML template. The frontend has no PDF logic.

**Logs go to files the app reads itself.** The backend and the app each write their own log, one JSON object a line, in one folder: `WebApp/logs` while developing, `C:\ProgramData\Kanat\logs` on the range PC (mounted as `/var/log/kanat` in the containers), where the installer sets it for each (the backend's `LOG_DIR`, the app's `logDir` in `kanat-config.json`, and `KANAT_LOG_DIR` for `docker-compose.yml`). Each rotates once a day, keeping about a week of past days. The backend writes `backend.log` (`backend/app/core/logs.py`), and a readable line to its console. Every request is logged as its answer is sent, with its method, path, status and duration (work it leaves to run after the answer, such as asking for a Session's Run, is not counted, and logs its own error if it fails; a client gone before an answer is a warning, not a 500), and every line logged while it ran carries its `request_id`, also sent back as `X-Request-ID` (`core/request_log.py`); the status poll and the health check only at DEBUG unless they fail. A request refused as invalid (422) is logged with what was wrong. The services log what happens in an operator's words, with the ids as fields: a Session created, completed, reopened, renamed or deleted; a Bullet Hole received (with its position and the delay from the model seeing it), repeated, refused or deleted; a camera added, changed or deleted, its video starting or stopping; mediamtx paths added, updated or removed; exports. The app writes `frontend.log` from Electron's main process (`frontend/electron/logs.ts`), which alone may touch files: the pages log through `frontend/src/utils/logger.ts`, which hands each line over IPC (`electron/preload.ts`), so the app's log does not depend on the backend. The pages log pages opened, requests the backend refused (the same refusal again within a minute is counted, not logged), the backend lost and back, a camera's video failing and playing again, live updates dropped, uncaught errors and a crashed screen (`components/UI/ErrorBoundary.tsx`); the main process logs its start with its settings, a window that crashed or froze, and its own errors, still shown in a dialog. A line from a page is checked and cut to size before it is written. Unset, `logDir` is `WebApp/logs` while developing and the OS's log folder for the app once packaged; a `logDir` it cannot write falls back to that folder, which the Logs tab then shows. The Detection Service writes `detection.log` in the same shape, through Python's `logging` (`ImageRecognitionService/detection/logs.py`), every line logged while a Run is active carrying its Session's `session_id`, whichever thread logs it: the service logs the detector warmed or its warm-up failed (with the `device` it runs on, `cuda:0` when CUDA is visible, else `cpu`, also on its `GET /status` beside its `model`, the weights' training run folder such as `kanat_yolo26m_v1`), itself started and stopping, each Run starting, watching (with its Baseline Marks), refused (filed under the Session refused, with the active one's `active_session_id`), failed (with the traceback) and ended; the stream opened, dropped, back and frames lost upstream; Board space built, the Board found, a camera view that sits badly on it, re-anchoring after the Board was lost; and each Bullet Hole posted, retried, refused or given up on (`detection.post`). Its folder is `--log-dir`, else `KANAT_LOG_DIR`, else `WebApp/logs` when that exists. The command line (`new_bullet_holes.py`) logs to its console only, and its end-of-run report stays printed. The app's Logs tab reads `backend.log`, `frontend.log` and `detection.log` directly (`frontend/electron/logreader.ts`, reached over IPC through `frontend/src/api/logs.ts`): only the main process touches the files, as it alone may, and it reads each file's tail so a 10 MB log is not loaded whole. It shows the newest lines across the files, newest first, filtered by service and by level (that level and worse) and searched over the message and fields, refreshing every few seconds unless paused; a line's extra fields open on click (`frontend/src/pages/Logs.tsx`). A button opens the log folder in the file manager, for the rotated files the viewer does not read; the app's window only ever shows the app, any other page it is asked to open goes to the browser, and an export link is downloaded in the app. A request that fails is one error line with its traceback (`core/request_log.py`), not uvicorn's report of it too. A log line's own fields are added with `extra=` (never named after a LogRecord attribute such as `name`). There is no log stack (Loki, Grafana) to run.

**SQLite is the only database.** One local single-user app, so a file database is enough: a local file while developing, and a file on a Docker volume on the range PC (`WebApp/docker-compose.yml`). `core/database.py` turns on foreign keys, WAL and a busy timeout; `core/types.py` keeps datetimes timezone-aware (UTC) as Postgres did. No Redis, no queue, no secondary store.

**On the range PC (Windows 10), the backend and the Detection Service run in Docker too** (`docker compose --profile app up -d`), so their Python, WeasyPrint's Pango and PyTorch come in the images rather than installed on Windows, Docker restarts them, and stopping the Detection Service sends the SIGTERM on which it ends its Run. MediaMTX and the Electron app run on the PC itself, since the cameras' multicast does not reach Docker Desktop's containers; the containers reach MediaMTX at `host.docker.internal`, with the PC's time zone (`KANAT_TZ`) so their log timestamps are in local time. While developing, `start-all.sh` runs the backend and the Detection Service on the Mac instead. `WebApp/deploy/windows/build-bundle.sh` builds the offline bundle (installers pinned by SHA-256, the x64 images, the CPU and CUDA Detection Service, the app's installer, no data), and its `install.ps1` installs it on an empty Windows PC: WSL 2, Docker Desktop, MediaMTX started at login by Task Scheduler, the firewall rule and multicast route for the cameras, and the Detection Service on the GPU only where Docker can use an NVIDIA one (`docker-compose.gpu.yml`), else the CPU.

---

## What is deliberately out of scope

- Multi-user or multi-site deployments.
- Millimetre-accuracy positioning (blocked upstream — see `ImageRecognitionService/HANDOVER.md`, "Blocked" section).
- Any interaction with `PacketProcessingService/`, `Composer_cli/`, or `MotionSimulator/`.
