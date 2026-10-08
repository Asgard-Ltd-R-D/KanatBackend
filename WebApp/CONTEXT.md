# WebApp — Domain Context

Read this before working on anything in `WebApp/`. For the detection pipeline's domain (Bullet Hole detection, Board geometry, registration, persistence), see `ImageRecognitionService/HANDOVER.md` and `docs/adr/`.

---

## What this is

The WebApp is the operator-facing layer for a live shooting range. It consists of:

- **`backend/`** — Python + FastAPI service. Receives confirmed Bullet Hole detections from the detection model, stores them per Session in PostgreSQL, and serves a REST API to the frontend.
- **`frontend/`** — Electron desktop app (React + TypeScript + Vite + Tailwind). The operator uses it to start and close Sessions, review results, and export reports.

The two components in this repo that matter for day-to-day range operation are `ImageRecognitionService/` (the model) and `WebApp/` (everything the operator touches). The others (`PacketProcessingService/`, `Composer_cli/`, `MotionSimulator/`) are out of scope here.

---

## Glossary

**Session**
One shooting run on a Range. An operator starts a Session before firing begins and closes it when done. A Session has a `status` of `active` or `completed`. All Bullet Holes reported during a Session belong to it. A Session is the unit of export (PDF report) and the unit displayed in the session list.

**Bullet Hole** (web app sense)
A confirmed detection reported by the detection model to the backend. One row in the `bullet_holes` table. Carries a position (template coordinates x/y), the absolute timestamp when it was first detected (`first_seen_at`), a source (`"model"` or `"manual"`), and an insertion-order rank within the session. Optional fields (`target_index`, `x_mm`, `y_mm`) are populated when the model provides them. Ring scores, target/miss classification, and per-detection confidence/frame metadata are outside the current WebApp scope.

This is distinct from a **Hit**: two bullets through the same point leave one Bullet Hole. The system counts Bullet Holes, not Hits. See `docs/adr/0001-report-bullet-holes-not-hits.md`.

**Template coordinates**
The coordinate system of the printed Target artwork (`ImageRecognitionService/data/targets/kanat_silhouette_a4.png`, 1405×1120 px). All Bullet Hole positions are reported and stored in these coordinates. The frontend's target overlay maps them back to screen pixels at render time.

**Target / Miss**
A Bullet Hole is a **Target** hit if it landed on a scoring silhouette. It is a **Miss** if it hit the Board outside any Target. Ring scores 6–10 are Target hits; score 0 is a Miss.

**Capture Setup / mediamtx**
The video pipeline is outside the WebApp's scope. The WebApp does not start, stop, or control the camera or the detection model. It only receives results the model pushes to it. The live camera view in the frontend is an HLS stream from mediamtx, displayed as-is with no interaction.

**API contract**
The JSON schema the detection model uses when calling `POST /sessions/{id}/bullets`. Defined in `backend/docs/api_contract.md` and versioned (`v1`). The backend rejects any payload whose `version` field does not match.

---

## Architecture

```
Camera
  └─► mediamtx (VideoService) ──HLS──► Frontend (Electron) — operator watches live
            │
            ▼ RTSP stream
  ImageRecognitionService (detection model)
            │
            │  POST /sessions/{id}/bullets  (one call per confirmed Bullet Hole)
            ▼
       WebApp/backend  (FastAPI)
            │
            ├─► PostgreSQL — sessions + bullet_holes tables
            │
            └─► GET /sessions, GET /sessions/{id}, GET /sessions/{id}/export/pdf
                        ▲
               WebApp/frontend (Electron)
```

---

## Key design decisions

**The system is not real-time.** The UI does not update while a Session is active. The operator starts a Session, the model runs, and when the operator closes the Session the results are fetched and displayed. There is no polling, no WebSocket, and no live bullet feed to the frontend. The only real-time element is the HLS camera stream, which is handled entirely by the browser's video player.

**Bullet Holes arrive slowly.** The detection model requires a 50-frame persistence window (~2 seconds at 25 fps) before confirming a Bullet Hole. Confirmed detections arrive seconds apart, not milliseconds. The backend endpoint for receiving them does not need a queue or any special throughput design.

**The frontend is an Electron desktop app**, not a web app. It is installed on the operator's machine at the Range. It talks to the backend over localhost or a local network. There is no public internet exposure.

**PDF export is backend-generated.** The frontend calls `GET /sessions/{id}/export/pdf` and receives a file download. The backend renders the PDF using WeasyPrint from an HTML template. The frontend has no PDF logic.

**PostgreSQL is the only database.** It runs in the existing Docker stack (`docker-compose.dev.yml`, port 5432). No Redis, no queue, no secondary store.

---

## What is deliberately out of scope

- Starting, stopping, or configuring the detection model or mediamtx from the WebApp.
- Real-time bullet feed to the UI during an active Session.
- Multi-user or multi-range deployments.
- Millimetre-accuracy positioning (blocked upstream — see `ImageRecognitionService/HANDOVER.md`, "Blocked" section).
- Any interaction with `PacketProcessingService/`, `Composer_cli/`, or `MotionSimulator/`.
