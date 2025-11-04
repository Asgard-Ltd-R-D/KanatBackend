#!/usr/bin/env bash
set -euo pipefail

# --- 1) Find a Python 3 launcher (prefer python3, fallback python if 3.x) ---
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
  echo "No Python 3 interpreter found (tried: python3, python)" >&2
  exit 1
}
PY="$(find_py3)"

# --- 2) Build commands (run from current directory) ---
PROJECT_DIR="$PWD"
CMD1=$(printf 'cd %q; %q motion_simulator.py' "$PROJECT_DIR" "$PY")
CMD2=$(printf 'cd %q; %q ui_client.py'         "$PROJECT_DIR" "$PY")

# Escape for AppleScript string
esc_as() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
CMD1_AS="$(esc_as "$CMD1")"
CMD2_AS="$(esc_as "$CMD2")"

# Sanity: scripts exist
[[ -f "$PROJECT_DIR/motion_simulator.py" ]] || { echo "Missing motion_simulator.py"; exit 1; }
[[ -f "$PROJECT_DIR/ui_client.py"       ]] || { echo "Missing ui_client.py";       exit 1; }

# --- 3) Open each in its own Terminal tab ---
/usr/bin/osascript -e "tell application \"Terminal\" to activate" \
                   -e "tell application \"Terminal\" to do script \"$CMD1_AS\"" \
                   -e "tell application \"Terminal\" to do script \"$CMD2_AS\""

echo "[ok] Launched in Terminal tabs:"
echo " - $CMD1"
echo " - $CMD2"