# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Five independent pieces, one git repo:

- `PacketProcessingService/` — the product: .NET 8 ASP.NET Core service (the only project in `kanat_server.sln`). Directory is `PacketProcessingService`, but the C# root namespace is `PacketProcessing.*` and the README still calls the folder `PacketProcessing/`.
- `Composer_cli/` + `composer.py` + `build_artifacts.sh` — Python packaging/lifecycle CLI (`composer`) that builds the service, starts the Docker stack, and produces installers. Deployment docs: `Composer_cli/DEPLOY_README.md`.
- `MotionSimulator/` — standalone Python TCP/UDP simulator + pcap replay, used to feed the service without real hardware.
- `ImageRecognitionService/` — Python Bullet Hole detection (OpenCV + YOLO), not wired into the .NET service. Pipeline in `detection/`, scoring/truth tooling in `tools/`, both run as modules from the service root (`python -m tools.evaluate ...`). Start at `ImageRecognitionService/HANDOVER.md`.
- `VideoService/` — git submodule (`KanatVideo`); empty until `git submodule update --init`.
- `WebApp/` — Electron desktop app (session management UI) + FastAPI backend. The two active components for day-to-day range operation. Start at `WebApp/CONTEXT.md`.

## Commands

```bash
# Databases + Seq (QuestDB 8812/9000/9009, Postgres 5432, Seq 5341)
docker compose -f docker-compose.dev.yml up -d

# Build / run the service (Dev: http://localhost:10901, Prod: 10900)
dotnet build kanat_server.sln
cd PacketProcessingService && dotnet run --environment Development

# Tests (xUnit; no trait categories exist — filter by namespace/name)
dotnet test PacketProcessingService/tests/PacketProcessingService.Tests.csproj
dotnet test ... --filter "FullyQualifiedName~DbWriterServiceTests"
dotnet test ... --filter "FullyQualifiedName~UnitTests"        # unit only
dotnet test ... --filter "FullyQualifiedName~IntegrationTests"  # integration only

# Composer CLI (dev/prod lifecycle + installers) — each is a separate subcommand
python composer.py up dev -d      # environment defaults to prod if omitted
python composer.py stop dev
python composer.py kill dev
python composer.py status
python composer.py build
python composer.py release osx-arm64
./build_artifacts.sh linux-x64      # or: clean

# WebApp — backend (FastAPI, http://localhost:8000)
cd WebApp/backend && uv run uvicorn app.main:app --reload

# WebApp — frontend (Electron + Vite dev server)
cd WebApp/frontend && npm run dev

# WebApp — database migrations
cd WebApp/backend && uv run alembic upgrade head

# WebApp — backend tests
cd WebApp/backend && uv run pytest

# WebApp — add/remove a backend dependency
cd WebApp/backend && uv add <package>
cd WebApp/backend && uv remove <package>
```

Packet capture needs raw-socket rights: `sudo setcap cap_net_raw,cap_net_admin=eip <binary>` on Linux, sudo on macOS.

## Conventions

### PacketProcessingService (.NET)
- Async methods carry the `Async` suffix; services are interface-first (`IFoo` next to `Foo`) and resolved through DI.
- Serilog structured logging with bracketed component prefixes (`[HANDLER-SERVICE]`, `[DB-WRITER]`, `[DEVICE-SERVICE]`).
- Dev-only endpoints get `[DevelopmentOnly]`, which also groups them under a "Development" Swagger tag.
- `swagger.json` at the service root is served verbatim in non-Production, overriding the generated doc — regenerate/update it when API shapes change.
- CI (`.github/workflows`): `test.yml` runs the test project on any `PacketProcessingService/**` change; `build.yml` runs after it and publishes installers, tagging `main`/`master` as releases and `feature/**`/`fix/**` as pre-releases — branch names matter.

### WebApp (FastAPI + Electron)
- Backend routers live in `WebApp/backend/app/routers/`, one file per resource (`sessions.py`, `bullets.py`).
- All DB access goes through the SQLAlchemy session injected via FastAPI's `Depends` — no raw queries outside of migrations.
- Every schema change requires an Alembic migration; never mutate the DB by hand.
- Frontend API calls are centralised in `WebApp/frontend/src/api/` — components never call `fetch` directly.
- The detection model's API contract is versioned (`v1`). The version is checked on every inbound bullet payload; unknown versions are rejected with `422`.

## Agent skills

### Issue tracker

GitHub Issues on `Asgard-Ltd-R-D/KanatBackend`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

The WebApp has its own domain context at `WebApp/CONTEXT.md`. Read it before working on anything in `WebApp/`.

### Commit conventions

One commit per issue, subject `<scope>: <imperative description>`, mandatory 1–2 sentence body explaining what the files implement together, footer `Refs #<number>`. See `docs/agents/commit-conventions.md`.
