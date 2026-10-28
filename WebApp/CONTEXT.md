# WebApp — Domain Context

Read this before working on anything in `WebApp/`. For the detection pipeline's domain (Bullet Hole detection, Board geometry, registration, persistence), see `ImageRecognitionService/HANDOVER.md` and `docs/adr/`.

---

## What this is

The WebApp is the operator-facing layer for a live shooting range. It consists of:

- **`backend/`** — Python + FastAPI service. Tells the Detection Service when to watch a Session, receives the confirmed Bullet Hole detections, stores them per Session in PostgreSQL, and serves a REST API to the frontend.
- **`frontend/`** — Electron desktop app (React + TypeScript + Vite + Tailwind). The operator uses it to start and close Sessions, review results, and export reports.

The two components in this repo that matter for day-to-day range operation are `ImageRecognitionService/` (the Detection Service) and `WebApp/` (everything the operator touches). The others (`PacketProcessingService/`, `Composer_cli/`, `MotionSimulator/`) are out of scope here.

---

## Glossary

**Session**
The WebApp's name for a Range (see the root `CONTEXT.md`): one shooting session at the range site, from start to stop. An operator starts a Session before firing begins and closes it when done. A Session has a `status` of `active` or `completed`. At most one Session is active at a time: starting a Session, or reopening a completed one, while another is active is refused (409, naming the active one), the session list's New Session button is disabled meanwhile, and the database holds it too, for two requests at once (`uq_sessions_one_active`, a unique index on the active rows). All Bullet Holes reported during a Session belong to it. A Session is the unit of export (PDF report) and the unit displayed in the session list. A Session names the camera that watches its Board (`sessions.camera_id`), chosen when it starts and fixed for its life, so every Bullet Hole in it is placed on that camera's picture, from the baseline of the Run that reported it; a Session without one is recorded and marked by hand. Deleting the camera leaves its Sessions without one.

**Detection** (of a Session)
Whether a Run of the Detection Service watches the Session: `none` (no camera), `starting`, `watching` (the Session page says "Detection ready": shots count from here), `not_watching` with its reason (the Detection Service did not answer, the Run failed on the Stream, another Session's Run still holds the service, until the next reconcile ends it, or the Session's camera was disabled or deleted; none for a Run lost while the service answers, until it is started again), `ending` (the page says "Closing…"), or `end_unconfirmed`. When a Session with a camera starts, the backend answers at once with `starting` and asks the Detection Service for its Run on `rtsp://127.0.0.1:8554/<alias>` in the background; the Detection Service answers once the Run's baseline is built, a few seconds later. Completing the Session ends its Run first, while the Session is still active: the Run looks on until every Candidate it has open is judged, opening none, up to about 3 s, so a Bullet Hole fired just before the end is still posted and stored. If the Detection Service does not answer the end within 15 s, or no longer has the Run, the Session completes anyway. If a Run watched it and no end of its Run has been confirmed since, even if it reads not watching by then, it reads `end_unconfirmed` (its last shots may be missing) until it is reopened. Every 5 s, beside the camera sync, the backend reconciles the Detection Service's one Run with the Session to watch: the active Session, there being one at a time, while its camera is enabled. It ends a Run of any other Session (one completed while the Detection Service could not be told) and starts the active one's when it has none, so a Run lost to a restart or a failed Stream comes back by itself, and a reopened Session is watched again. Each new Run takes a fresh baseline: anything fired while none watched is a Baseline Mark, which the operator adds by hand. The state is held in the backend's memory (`backend/app/services/detection_sync.py`, the client is `detection_client.py`), returned with the Session and pushed on its live stream.

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
The WebApp configures the cameras, and starts and ends the Detection Service's Runs, but not the Detection Service itself. The operator enters each camera (alias, multicast group and port, network interface) in Settings; the alias is fixed once the camera exists, since it names the camera's stream (`rtsp://<host>:8554/<alias>`, which the Detection Service reads) and its recordings; the backend stores them in the `cameras` table and keeps mediamtx in step through its Control API (`backend/app/services/camera_sync.py`): each enabled camera becomes a mediamtx path whose `run_record.sh` (GStreamer) joins the camera's H.264 RTP multicast and publishes it as RTSP, as KanatFrontend set it up. A disabled camera keeps a path with nothing running or recording on it, because mediamtx's playback server only plays recordings of a configured path. The paths `mediamtx.yml` defines (e.g. `loopdemo`) belong to mediamtx: the backend reads their names from the file and never patches or deletes them, and refuses a camera of the same name. Paths added through the API live only in mediamtx's memory, so the backend re-applies them on startup and every 5 s. The live camera view in the frontend is a WebRTC stream from mediamtx per enabled camera (WHEP, `frontend/src/components/Camera/WhepPlayer.tsx`), retried every 5 s while a camera has no signal.

**Recording**
A Session records the cameras only if the operator turns recording on, when starting it or during it (`sessions.record`); each stretch with it on is a recording interval (`recording_intervals`). The backend switches mediamtx's `record` on every camera path while an active Session has an open interval, but a Session's replay, and the video its deletion removes, are only the recordings within its own intervals, so a Session running alongside one that records never shows or deletes that one's video; mediamtx writes 10-minute fMP4 files to `VideoService/recordings/` and deletes them after a day. A completed Session's replay lists each camera's recorded spans within the Session from mediamtx's playback server, in parts of at most 10 minutes that play one into the next, and plays them through the backend (`backend/app/routers/recordings.py`), since the playback server listens on this PC only. The playback server streams a part with no length and no byte ranges, which a `<video>` cannot seek in, so the backend fetches each part once into a cache folder (`VideoService/replay-cache`; the camera sync loop deletes a copy every 10 minutes once its recording is a day old, i.e. with the original, and the least recently played beyond 20 GB) and serves it in byte ranges (`backend/app/core/ranges.py`). On a completed Session the recordings are listed one row per camera and open in a player window; a Bullet Hole's time in the Bullet Log opens it 3 s before that moment, when a camera was recording then. Deleting a Session deletes its video too: the recordings that started within its intervals (mediamtx names each file after its start, in local time), in every camera's folder including those of cameras since deleted, unless they run on into another Session's intervals, and their replay copies. mediamtx only expires the recordings of paths it still has, so the backend deletes day-old recordings left by a deleted camera.

**The backend runs on the same PC as mediamtx, not in a container.** It reaches mediamtx's Control API and playback server on 127.0.0.1, reads `VideoService/recordings` to delete a Session's video, and reads mediamtx's local-time file names in the PC's own time zone. So the compose files run only its database; the backend is started on the PC (`uv run uvicorn ...`, see CLAUDE.md), as the installer will.

**Overlay**
The Session's Bullet Holes, numbered by rank as in the log and coloured Target, Miss or manual, and its Run's Baseline View (the Target outlines, and the Baseline Marks in grey), drawn by the frontend over the picture of the Session's camera, live and in replay, where the Run's latest Registration places the Board in the picture, read every 5 s; never burned into the video (`docs/adr/0009-overlays-are-drawn-by-the-frontend-from-each-runs-baseline-view.md`). In replay each Bullet Hole shows from its `first_seen_at` on, over the Baseline View of the Run watching at that moment, at the place registered last before it. A Bullet Hole from an earlier Run of the Session is carried into the watching Run's coordinates through the picture, onto where that Run's baseline saw it, and a Baseline Mark that a drawn Bullet Hole stands for is not drawn. The operator can turn it off to see the bare picture. While no Run watches (a Session without a camera, before its first Run, between a lost Run and the next, or live unless its detection reads `watching` or `ending`) there is none.
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
            ├─► PostgreSQL — sessions, bullet_holes, cameras, recording_intervals, runs tables
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
            ├─► mediamtx Control API (127.0.0.1:9997) — camera paths, recording on/off
            │   mediamtx playback (127.0.0.1:9996) — recorded video for replay
            │
            ├─► GET /sessions, GET /sessions/{id} (with its Runs, for the Overlay), GET /sessions/{id}/export/pdf
            │
            ├─► GET /sessions/{id}/live (Server-Sent Events) — pushes each change to the frontend
            │
            ├─► GET /status — whether mediamtx and the Detection Service are up, for the frontend's
            │   status indicator: from each one's last answer (under 12 s old), asking it only without one
            │
            └─► logs/backend.log ─┐
            logs/frontend.log ────┤
            logs/detection.log ───┼─► Grafana Alloy ──► Loki ──► Grafana (127.0.0.1:3300)
            logs/postgres/*.json ─┘                                       │
                        ▲                                                 │ embedded
               WebApp/frontend (Electron) ◄────────── Logs tab ───────────┘
```

---

## Key design decisions

**Live detections are pushed, not polled.** While a Session is active, the frontend holds a Server-Sent Events stream from `/sessions/{id}/live` (`backend/app/routers/live.py`). Live traffic only ever goes backend → frontend: corrections to a Session's Bullet Holes happen after it ends. The backend pushes an event when a Bullet Hole is created or deleted, the Session's status changes, or its detection does (`backend/app/schemas/live.py`); the frontend applies it to the session it already holds (`frontend/src/hooks/useSessionLive.ts`). The browser reconnects a dropped stream by itself, and on every (re)connect the frontend refetches the Session once, so nothing published while it was not listening is lost. The backend pings an idle stream every 15 s; after 40 s without a ping or an event the frontend assumes a frozen backend and reconnects. uvicorn must run with `--timeout-graceful-shutdown`: an open stream never finishes, and without it a restarting backend never exits and keeps the frontend attached to it. It must also run a single worker: the open streams live in that process's memory, so with several workers a bullet reported to one never reaches a frontend listening on another. A detection reaches the screen as soon as the backend stores it; the delay that remains is the Detection Service's own persistence window. The camera stream is separate: WebRTC, handled by the browser's video player.

**Bullet Holes arrive slowly.** The Detection Service requires a 50-frame persistence window (~2 seconds at 25 fps) before confirming a Bullet Hole. Confirmed detections arrive seconds apart, not milliseconds. The backend endpoint for receiving them does not need a queue or any special throughput design.

**The frontend is an Electron desktop app**, not a web app. It is installed on the operator's machine at the range site. It talks to the backend over localhost or a local network. There is no public internet exposure.

**PDF export is backend-generated.** The frontend calls `GET /sessions/{id}/export/pdf` and receives a file download. The backend renders the PDF using WeasyPrint from an HTML template. The frontend has no PDF logic.

**Logs go to Grafana, through Loki.** The backend and the app each write their own log, one JSON object a line, in one folder: `WebApp/logs` while developing, `/var/log/kanat` on the range PC, where the installer sets it for each (the backend's `LOG_DIR`, the app's `logDir` in `kanat-config.json`, and `KANAT_LOG_DIR` for `docker-compose.yml`). Each rotates at 10 MB, keeping 10 old files. The backend writes `backend.log` (`backend/app/core/logs.py`), and a readable line to its console. Every request is logged as its answer is sent, with its method, path, status and duration (work it leaves to run after the answer, such as asking for a Session's Run, is not counted, and logs its own error if it fails; a client gone before an answer is a warning, not a 500), and every line logged while it ran carries its `request_id`, also sent back as `X-Request-ID` (`core/request_log.py`); the status poll, the health check and replay byte ranges only at DEBUG unless they fail. A request refused as invalid (422) is logged with what was wrong. The services log what happens in an operator's words, with the ids as fields: a Session created, completed, reopened, renamed or deleted, its recording switched; a Bullet Hole received (with its position and the delay from the model seeing it), repeated, refused or deleted; a camera added, changed or deleted, its video starting or stopping; mediamtx paths added, updated or removed, the cameras starting or stopping recording; replay parts fetched, the replay cache cleaned, recordings deleted; exports. The app writes `frontend.log` from Electron's main process (`frontend/electron/logs.ts`), which alone may touch files: the pages log through `frontend/src/utils/logger.ts`, which hands each line over IPC (`electron/preload.ts`), so the app's log does not depend on the backend. The pages log pages opened, requests the backend refused (the same refusal again within a minute is counted, not logged), the backend lost and back, a camera's video failing and playing again, live updates dropped, uncaught errors and a crashed screen (`components/UI/ErrorBoundary.tsx`); the main process logs its start with its settings, a window that crashed or froze, and its own errors, still shown in a dialog. A line from a page is checked and cut to size before it is written. Unset, `logDir` is `WebApp/logs` while developing and the OS's log folder for the app once packaged; a `logDir` it cannot write falls back to that folder, which the Logs tab then shows. The Detection Service writes `detection.log` in the same shape, through Python's `logging` (`ImageRecognitionService/detection/logs.py`), every line logged while a Run is active carrying its Session's `session_id`, whichever thread logs it: the service logs itself started and stopping, each Run starting, watching (with its Baseline Marks), refused (filed under the Session refused, with the active one's `active_session_id`), failed (with the traceback) and ended; the stream opened, dropped, back and frames lost upstream; Board space built, the Board found, a camera view that sits badly on it, re-anchoring after the Board was lost; and each Bullet Hole posted, retried, refused or given up on (`detection.post`). Its folder is `--log-dir`, else `KANAT_LOG_DIR`, else `WebApp/logs` when that exists. The command line (`new_bullet_holes.py`) logs to its console only, and its end-of-run report stays printed. Postgres writes its own JSON log (`jsonlog`) in the folder's `postgres/` subfolder, one file a weekday, emptied a week later: errors, warnings, startup and shutdown, checkpoints, queries slower than 1 s and lock waits past 1 s (`observability/postgres/start.sh`, which makes the subfolder itself, and starts Postgres logging to `docker logs webapp-postgres` instead when the folder cannot be written); Alloy reads its severity as the level, and counts Python's `critical` as `error`. Grafana Alloy reads the folder and ships it to Loki, which keeps 30 days; Grafana shows it, with a ready dashboard (`observability/grafana/dashboards/kanat-webapp.json`): counts of errors, warnings, Bullet Holes and Sessions; the top errors, each distinct message with how often it came; log volume by level; every error and warning line; the activity in an operator's words (Sessions, Bullet Holes, cameras, recording, the Detection Service's Runs); request times; and every line. Log lines run oldest to newest, the newest at the bottom, filtered by service, level, Session id and text. A request that fails is one error line with its traceback (`core/request_log.py`), not uvicorn's report of it too. All three run from `docker-compose.yml` beside the database, on 127.0.0.1 only (`docker compose up -d loki alloy grafana`). The app's Logs tab embeds that dashboard (`frontend/src/pages/Logs.tsx`), shows the log folder with a button that opens it, and opens Grafana in the browser to explore: the app's window only ever shows the app, any other page it is asked to open goes to the browser, and an export link is downloaded in the app. Anyone on the PC may view and query without logging in, and the `admin` account edits, with `GRAFANA_ADMIN_PASSWORD` from `WebApp/.env` (`.env.example`), which `docker compose` requires. A log line's own fields are added with `extra=` (never named after a LogRecord attribute such as `name`); only `app`, `service` and `level` are Loki labels, the rest is read with `| json`.

**PostgreSQL is the only database.** It runs in the existing Docker stack (`docker-compose.dev.yml`, port 5432). No Redis, no queue, no secondary store.

---

## What is deliberately out of scope

- Multi-user or multi-site deployments.
- Millimetre-accuracy positioning (blocked upstream — see `ImageRecognitionService/HANDOVER.md`, "Blocked" section).
- Any interaction with `PacketProcessingService/`, `Composer_cli/`, or `MotionSimulator/`.
