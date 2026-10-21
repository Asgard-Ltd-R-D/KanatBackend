#!/usr/bin/env bash
set -Eeuo pipefail

# Defaults
MCAST_IP_DEFAULT="226.226.226.112"
MCAST_PORT_DEFAULT="112"

# Arguments
MCAST_IP=""
MCAST_PORT=""
RTSP_URL=""
IFACE=""

usage() {
  echo "Usage: $0 [options]"
  echo
  echo "Options:"
  echo "  --iface NAME        Multicast network interface, e.g. enP4p65s0"
  echo "  --mcast-ip IP       Multicast address (default: ${MCAST_IP_DEFAULT})"
  echo "  --mcast-port PORT   Multicast port (default: ${MCAST_PORT_DEFAULT})"
  echo "  --rtsp-url URL      RTSP destination URL"
  echo "  -h, --help          Show this help"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --iface)
      IFACE="${2:?Missing value for --iface}"
      shift 2
      ;;
    --mcast-ip)
      MCAST_IP="${2:?Missing value for --mcast-ip}"
      shift 2
      ;;
    --mcast-port)
      MCAST_PORT="${2:?Missing value for --mcast-port}"
      shift 2
      ;;
    --rtsp-url)
      RTSP_URL="${2:?Missing value for --rtsp-url}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# Environment-variable fallbacks
MCAST_IP="${MCAST_IP:-${MCAST_IP_ENV:-${MCAST_IP_DEFAULT}}}"
MCAST_PORT="${MCAST_PORT:-${MCAST_PORT_ENV:-${MCAST_PORT_DEFAULT}}}"
IFACE="${IFACE:-${IFACE_ENV:-}}"

# Build the default RTSP URL
if [[ -z "$RTSP_URL" ]]; then
  : "${MTX_PATH:=hello}"
  : "${RTSP_PORT:=8554}"
  RTSP_URL="rtsp://127.0.0.1:${RTSP_PORT}/${MTX_PATH}"
fi

# Validate the interface: sysfs on Linux, ifconfig on macOS, skipped elsewhere
iface_exists() {
  if [[ -d /sys/class/net ]]; then
    [[ -d "/sys/class/net/$1" ]]
  elif command -v ifconfig >/dev/null; then
    ifconfig "$1" >/dev/null 2>&1
  fi
}

list_ifaces() {
  if [[ -d /sys/class/net ]]; then
    ls /sys/class/net
  else
    ifconfig -l | tr ' ' '\n'
  fi
}

if [[ -n "$IFACE" ]] && ! iface_exists "$IFACE"; then
  echo "❌ Network interface '${IFACE}' does not exist." >&2
  echo "Available interfaces:" >&2

  list_ifaces | sed 's/^/  - /' >&2

  exit 1
fi

# Locate GStreamer
GST_BIN="$(command -v gst-launch-1.0 || true)"

if [[ -z "$GST_BIN" ]]; then
  # Homebrew fallback for macOS
  if [[ -x "/opt/homebrew/bin/gst-launch-1.0" ]]; then
    GST_BIN="/opt/homebrew/bin/gst-launch-1.0"
  else
    echo "❌ gst-launch-1.0 was not found." >&2
    echo "Install it on Ubuntu with:" >&2
    echo "sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good gstreamer1.0-plugins-bad" >&2
    exit 1
  fi
fi

# Construct udpsrc properties
UDP_SRC_ARGS=(
  "address=${MCAST_IP}"
  "port=${MCAST_PORT}"
  "auto-multicast=true"
)

if [[ -n "$IFACE" ]]; then
  UDP_SRC_ARGS+=("multicast-iface=${IFACE}")
fi

echo "Using GStreamer: ${GST_BIN}"
echo "Multicast source: udp://${MCAST_IP}:${MCAST_PORT}"
echo "RTSP destination: ${RTSP_URL}"

if [[ -n "$IFACE" ]]; then
  echo "Multicast interface: ${IFACE}"
else
  echo "Multicast interface: automatic"
fi

# GStreamer runs in the background and the script waits on it: bash runs a trap
# only once a foreground child exits, and a GStreamer with no multicast arriving
# never does, so MediaMTX stopping this script would leave it running.
# The script also watches MediaMTX, which starts it: if MediaMTX dies without
# stopping it (killed, crashed), it stops instead of streaming as an orphan
# that a restarted MediaMTX's own copy of this script would fight.
PARENT_PID=$PPID
GST_PID=""
# Between GStreamer restarts, so a camera that keeps failing does not flood the log
RESTART_PAUSE_S=2

stop_gst() {
  [[ -n "$GST_PID" ]] && kill "$GST_PID" 2>/dev/null
  GST_PID=""
}
trap 'echo; echo "Stopping..."; stop_gst; exit 0' INT TERM HUP
trap 'stop_gst' EXIT

while true; do
  "$GST_BIN" -e \
    udpsrc "${UDP_SRC_ARGS[@]}" ! \
    "application/x-rtp,media=video,encoding-name=H264" ! \
    rtpjitterbuffer latency=0 drop-on-latency=true ! \
    rtph264depay ! \
    h264parse ! \
    rtspclientsink location="${RTSP_URL}" protocols=tcp &
  GST_PID=$!

  while kill -0 "$GST_PID" 2>/dev/null; do
    if ! kill -0 "$PARENT_PID" 2>/dev/null; then
      echo "The process that started this script is gone. Stopping..." >&2
      exit 0
    fi
    # In the background and waited on, so a trap still runs at once
    sleep 1 &
    wait $! || true
  done

  if ! wait "$GST_PID"; then
    echo "⚠️ GStreamer stopped with an error. Restarting..." >&2
  fi
  GST_PID=""

  sleep "$RESTART_PAUSE_S"
done
