#!/usr/bin/env bash
set -Eeuo pipefail

# Defaults
MCAST_IP_DEFAULT="226.226.226.112"
MCAST_PORT_DEFAULT="112"

# Args
MCAST_IP=""
MCAST_PORT=""
RTSP_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mcast-ip)   MCAST_IP="${2:-}"; shift 2 ;;
    --mcast-port) MCAST_PORT="${2:-}"; shift 2 ;;
    --rtsp-url)   RTSP_URL="${2:-}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Fallbacks
MCAST_IP="${MCAST_IP:-${MCAST_IP_ENV:-${MCAST_IP_DEFAULT}}}"
MCAST_PORT="${MCAST_PORT:-${MCAST_PORT_ENV:-${MCAST_PORT_DEFAULT}}}"

if [[ -z "$RTSP_URL" ]]; then
  : "${MTX_PATH:=hello}"
  : "${RTSP_PORT:=8554}"
  RTSP_URL="rtsp://127.0.0.1:${RTSP_PORT}/${MTX_PATH}"
fi

# ----- GStreamer auto detection -----
GST_BIN=$(command -v gst-launch-1.0 || true)
if [[ -z "$GST_BIN" ]]; then
  # fallback for homebrew mac
  if [[ -x "/opt/homebrew/bin/gst-launch-1.0" ]]; then
    GST_BIN="/opt/homebrew/bin/gst-launch-1.0"
  else
    echo "❌ gst-launch-1.0 not found. Please install GStreamer." >&2
    exit 1
  fi
fi

echo "Using GStreamer: $GST_BIN"
echo "Publishing to ${RTSP_URL} from udp://${MCAST_IP}:${MCAST_PORT}"

trap 'echo "Stopping..."; exit 0' INT TERM

# Loop forever
while :; do
  "$GST_BIN" -e \
    udpsrc multicast-group="${MCAST_IP}" auto-multicast=true port="${MCAST_PORT}" \
         caps="application/x-rtp,media=video,encoding-name=H264,clock-rate=90000,pt=96" ! \
    rtpjitterbuffer ! rtph264depay ! h264parse config-interval=-1 ! \
    rtspclientsink location="${RTSP_URL}" protocols=tcp do-rtsp-keep-alive=false

  sleep 0.2
done
