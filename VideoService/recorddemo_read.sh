#!/usr/bin/env bash
set -Eeuo pipefail

# MTX_QUERY is provided by MediaMTX to runOnRead (raw query string, no leading '?')
# We store the latest prefix per path (very small text file), so the segment hook can use it.
STATE_DIR="/tmp/mtx-record-state"
mkdir -p "$STATE_DIR"
OUT="$STATE_DIR/${MTX_PATH}.prefix"

# Parse MTX_QUERY robustly, handle URL-encoding
# example MTX_QUERY: "prefix=mytag&foo=bar"
prefix="$(python3 - <<'PY'
import os, urllib.parse as up
q = os.environ.get("MTX_QUERY","")
vals = up.parse_qs(q)
p = vals.get("prefix", [""])[0]
print(up.unquote_plus(p))
PY
)"

if [ -n "$prefix" ]; then
  printf '%s' "$prefix" > "$OUT"
fi
