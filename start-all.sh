#!/usr/bin/env bash
# Starts the whole WebApp stack on this Mac in one terminal: Postgres (Docker),
# MediaMTX, the Detection Service, the backend, and the frontend (Vite + Electron).
# Each service's output is prefixed with its name. Ctrl-C, or any one service
# exiting, stops them all (a second Ctrl-C kills what is still shutting down);
# Postgres stays up (docker compose -f WebApp/docker-compose.yml stop).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.docker/bin:$PATH"

# Services started with & ignore Ctrl-C (bash does that in a script, and the
# Detection Service only handles SIGTERM), so stop them with one SIGTERM and wait:
# the Detection Service ends its Run and posts the Bullet Holes it still holds.
# Signal every process under the script, not just its children: npm and uv run
# their services as their own children, and a KILL to npm alone orphans Vite
# and Electron. The KILL also takes the processes listed before the TERM: one
# whose parent exited on the TERM is no longer under the script.
tree() { local c; for c in $(pgrep -P "$1"); do echo "$c"; tree "$c"; done; }
stop_all() {
  under=$(tree $$)
  trap '' TERM; trap 'kill -KILL $under $(tree $$) 2>/dev/null' INT
  kill -TERM $under 2>/dev/null || true
  wait
}
trap stop_all EXIT
trap 'exit 130' INT TERM

if ! docker info >/dev/null 2>&1; then
  echo "[start-all] starting Docker Desktop..."
  open -a Docker
  until docker info >/dev/null 2>&1; do sleep 2; done
fi
if lsof -a -c postgres -iTCP:5432 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[start-all] a local Postgres holds port 5432: brew services stop postgresql@17" >&2
  exit 1
fi
# The log folder is made here, as this user, before Docker would make it as
# root: the services below write their logs into it
(cd "$ROOT/WebApp" && mkdir -p "${KANAT_LOG_DIR:-logs}")
docker compose -f "$ROOT/WebApp/docker-compose.yml" up -d --wait
(cd "$ROOT/WebApp/backend" && uv run alembic upgrade head)

# run <name> <dir> <command...>: in the background, output prefixed with [name].
# sed ignores the SIGTERM and ends with its service's output, so a service
# logging its shutdown never writes into a closed pipe.
names=() pids=()
run() {
  local name=$1 dir=$2; shift 2
  (cd "$dir" && exec "$@") 2>&1 | (trap '' TERM; exec sed -l "s/^/[$name] /") &
  names+=("$name") pids+=($!)
}

run mediamtx  "$ROOT/VideoService"            ./mediamtx mediamtx.yml
run detection "$ROOT/ImageRecognitionService" .venv/bin/python -u -m detection.service
# WeasyPrint's Pango/GLib come from Homebrew, for the PDF export
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \
  run backend "$ROOT/WebApp/backend" uv run uvicorn app.main:app --reload --timeout-graceful-shutdown 2
run frontend  "$ROOT/WebApp/frontend"         npm run dev

# The first service to exit stops the rest. macOS bash 3.2 has no wait -n, and
# kill -0 with several pids succeeds while any one lives, so check each.
while sleep 1; do
  for i in "${!pids[@]}"; do
    if ! kill -0 "${pids[$i]}" 2>/dev/null; then
      echo "[start-all] ${names[$i]} exited, stopping the rest" >&2
      exit 1
    fi
  done
done
