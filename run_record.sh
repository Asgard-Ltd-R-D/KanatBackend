#!/usr/bin/env bash
set -Eeuo pipefail

# Defaults (used only if args not provided)
MCAST_IP_DEFAULT="226.226.226.112"
MCAST_PORT_DEFAULT="112"

# Parse args: --mcast-ip, --mcast-port, --rtsp-url
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

# If not provided by args, fallback to env (if any), else default
MCAST_IP="${MCAST_IP:-${MCAST_IP_ENV:-${MCAST_IP_DEFAULT}}}"
MCAST_PORT="${MCAST_PORT:-${MCAST_PORT_ENV:-${MCAST_PORT_DEFAULT}}}"

# If RTSP_URL not given, build it from hook env (if present)
if [[ -z "${RTSP_URL}" ]]; then
  # MediaMTX usually injects these for hooks:
  # MTX_PATH (path name) and RTSP_PORT (rtsp tcp listener)
  # Ref: default config docs.
  : "${MTX_PATH:=hello}"
  : "${RTSP_PORT:=8554}"
  RTSP_URL="rtsp://127.0.0.1:${RTSP_PORT}/${MTX_PATH}"
fi

GST="/opt/homebrew/bin/gst-launch-1.0"

echo "Publishing to ${RTSP_URL} from udp://${MCAST_IP}:${MCAST_PORT}"

trap 'exit 0' INT TERM

# RTP/H264 → depay → parse → publish (no re-encode)
while :; do
  "$GST" -e \
    udpsrc multicast-group="${MCAST_IP}" auto-multicast=true port="${MCAST_PORT}" \
         caps="application/x-rtp,media=video,encoding-name=H264,clock-rate=90000,pt=96" ! \
    rtpjitterbuffer ! rtph264depay ! h264parse config-interval=-1 ! \
    rtspclientsink location="${RTSP_URL}" protocols=tcp do-rtsp-keep-alive=false
  sleep 0.2
done
