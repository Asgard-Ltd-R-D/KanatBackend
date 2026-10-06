# Commit conventions

One commit per **concern**. A concern is a group of files that can be described in one sentence without using "and". One issue will typically produce several commits — each one a self-contained step that leaves the repo in a working state.

## Subject line

```
<scope>: <imperative short description>
```

- **scope** — the area of the codebase this touches, e.g. `webapp/backend`, `webapp/frontend`, `webapp/schema`, `webapp/api`. Use a slash-delimited path for precision; keep it under 20 chars.
- **description** — imperative mood, lowercase, no trailing period. Describes *what the commit does*, not why. Max ~55 chars so the full subject stays under 72.

Examples:
```
webapp/docs: add WebApp context and agent conventions
webapp/container: add Dockerfile and dev compose service
webapp/deps: add Python dependencies via uv
webapp/alembic: add migration infrastructure
webapp/core: add FastAPI app with settings, DB, and router wiring
```

## Body (mandatory for WebApp commits)

One or two sentences explaining what the files in this commit implement together — name the key pieces and how they connect (e.g. "router calls service, service calls ORM model"). Keep it factual and precise. No filler ("this commit adds…"), no lists.

## Footer

Always reference the issue this commit belongs to:

```
Refs #<number>
```

Use `Refs`, not `Closes` — closing happens through the PR, not individual commits. This keeps the issue open until the PR is merged. Multiple commits can share the same `Refs #<number>`.

## Full example

```
webapp/core: add FastAPI app with settings, DB, and router wiring

Pydantic Settings reads DATABASE_URL from the environment; SQLAlchemy
Base and get_db live in core/ so every router imports from one place;
core/router.py is the single registration point for all routers.

Refs #95
```

## Grouping rule

If you need "and" to describe a commit, split it. Good splits for a backend scaffold:

| Commit | Files |
|--------|-------|
| docs | CLAUDE.md, CONTEXT.md, agent convention files |
| container | Dockerfile, docker-compose entries |
| deps | pyproject.toml, uv.lock |
| alembic | alembic.ini, env.py, script.py.mako |
| app core | main.py, config/, core/, package __init__.py stubs |
