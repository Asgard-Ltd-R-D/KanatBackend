# WebApp backend

FastAPI + SQLAlchemy 2 + Alembic on SQLite, Python 3.12 (`.python-version`), managed with uv. Read `WebApp/CONTEXT.md` for the domain words (Session, Bullet Hole, Run, Group, Camera) before changing behaviour.

## Layout

| Folder | Holds | Rule |
|---|---|---|
| `app/routers/` | one file per resource, HTTP only | Parses the request, calls a service, shapes the response. No queries. Registered in `app/core/router.py`. |
| `app/services/` | the rules | Calls repositories and other services. Background loops live here (`camera_sync.py`, `detection_sync.py`). |
| `app/repositories/` | the queries, one module per table | The only code that touches the SQLAlchemy session's query API. |
| `app/models/` | ORM tables | Every change needs a migration. |
| `app/schemas/` | Pydantic request/response models | Validation (e.g. camera alias rules) lives here. |
| `app/core/` | database, deps, logging, request log, router wiring | |
| `app/config/settings.py` | every environment variable | Add a setting here, then to `WebApp/docker-compose.yml` and `WebApp/.env.example` if the containers need it. |
| `alembic/versions/` | numbered migrations `NNN_<what>.py` | |
| `tests/` | pytest, one file per area; `fakes.py` for MediaMTX and the Detection Service | |

## Commands

```bash
uv run uvicorn app.main:app --reload --timeout-graceful-shutdown 2   # http://127.0.0.1:8000
uv run pytest -q                                                     # runs on a throwaway SQLite file, no server needed
uv run alembic upgrade head
uv add <package> / uv remove <package>                               # never edit uv.lock by hand
```

## Rules

- **Migrations:** every model change gets a numbered migration, and a test in `tests/test_schema.py`. A migration that would lose or merge data refuses, naming the rows and the command that fixes them; it never deletes data itself. Never change the database by hand.
- **127.0.0.1, not localhost**, in every default URL: on Windows localhost tries IPv6 first.
- **Paths and processes must work on Windows too:** files can be locked while open (see `recordings.py`'s retried deletes), and names like `CON`/`NUL` are reserved.
- **Cameras:** MediaMTX reads each camera's RTP multicast directly (`camera_sync.py` sets a `udp+rtp://group:port?interface=card` source, the card being the UI's picker value); GStreamer (`run_record.sh/.ps1`) is no longer in this pipeline, and `RECORD_LAUNCHER` is legacy, unused.
- **Logging:** `logging.getLogger(__name__)`, structured `extra={...}`; never log secrets or full stream URLs with credentials.
- **The Detection Service contract is versioned (`v2`:** a posted hole names its board by the camera alias): unknown versions, `v1` included, are a 422.
- **Optional heavy imports** (e.g. WeasyPrint) are imported where used, so the rest of the app runs without them.
- **Don't run ruff's formatter over files:** the code is hand-wrapped, and a formatter pass rewrites unrelated lines.
- **Docker image:** `Dockerfile` runs `alembic upgrade head` then uvicorn. A new runtime file or system library must be added there, or the Windows bundle breaks.
