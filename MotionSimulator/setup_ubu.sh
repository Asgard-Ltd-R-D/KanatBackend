#!/usr/bin/env bash
set -euo pipefail

# --- 1) Find a Python 3 launcher ---
find_py3() {
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" - <<'PY'
import sys
sys.exit(0 if sys.version_info[0] == 3 else 1)
PY
      then
        echo "$c"; return 0
      fi
    fi
  done
  echo "No Python 3 interpreter found" >&2
  exit 1
}

PY="$(find_py3)"
PROJECT_DIR="$PWD"

# --- 2) Sanity check ---
[[ -f "$PROJECT_DIR/motion_simulator.py" ]] || { echo "Error: motion_simulator.py not found in $PROJECT_DIR"; exit 1; }
[[ -f "$PROJECT_DIR/ui_client.py"       ]] || { echo "Error: ui_client.py not found in $PROJECT_DIR"; exit 1; }

# --- 3) Prepare Commands ---
# We use 'cd' and then run the python script. 'exec bash' keeps the window open if the script crashes.
CMD1="cd '$PROJECT_DIR' && '$PY' motion_simulator.py; exec bash"
CMD2="cd '$PROJECT_DIR' && '$PY' ui_client.py; exec bash"

echo "[info] Launching Motion Simulator and UI Client..."

# --- 4) Launch using the Native Binary Path ---
# We use /usr/bin/gnome-terminal to try and bypass the Snap version.
# We launch them as separate windows to prevent the "one tab crash" issue.
# 'env -u' strips the Snap-related library paths that cause the GLIBC error.

LAUNCHER="env -u LD_LIBRARY_PATH -u LIBPATH -u PYTHONPATH /usr/bin/gnome-terminal"

$LAUNCHER --window --title="Simulator" -- bash -c "$CMD1" &
sleep 0.5
$LAUNCHER --window --title="UI Client" -- bash -c "$CMD2" &

echo "[ok] Processes started in separate windows."