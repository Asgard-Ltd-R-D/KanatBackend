#!/usr/bin/env bash
set -Eeuo pipefail

# Provided by MediaMTX:
# MTX_SEGMENT_PATH  → absolute path of the newly completed segment file
# MTX_PATH          → path name (e.g., "recorddemo")

STATE_DIR="/tmp/mtx-record-state"
PREFIX_FILE="$STATE_DIR/${MTX_PATH}.prefix"

seg="$MTX_SEGMENT_PATH"
dir="$(dirname "$seg")"
base="$(basename "$seg")"

# Read last requested prefix (if any)
if [[ -f "$PREFIX_FILE" ]]; then
  prefix="$(cat "$PREFIX_FILE")"
else
  prefix=""
fi

# If prefix exists, rename: <prefix>__<timestamp>.ext
if [[ -n "$prefix" ]]; then
  ext="${base##*.}"
  name="${base%.*}"
  mv "$seg" "${dir}/${prefix}__${name}.${ext}"
fi
