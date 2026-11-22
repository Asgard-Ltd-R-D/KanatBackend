#!/usr/bin/env bash
#
# DEV ONLY — git-ignored on purpose (holds camera credentials + machine IPs).
# Not part of the product. Stand-in for a real multicast camera so the WebApp can
# be run against an ordinary RTSP (unicast) camera on any dev PC.
#
# What it does:
#   Pulls the camera's RTSP stream and re-emits it as RTP multicast exactly where
#   MediaMTX's camera path expects it (the backend sets a udp+rtp:// source per
#   camera). Loops, so an unplug/replug recovers on its own.
#
# Why it RE-ENCODES (not -c copy):
#   This camera encodes with B-frames. WebRTC/WHEP — what the app uses to show
#   live video — cannot play H.264 with B-frames (the tile stays blank while the
#   status reads "live"). "-bf 0" strips them. A native multicast camera that is
#   already configured without B-frames does NOT need this script at all.
#
# ── Per-PC settings (env, so nothing secret is committed) ───────────────────
#   CAM_PASS  : the camera's password — REQUIRED (not baked in, so it stays out
#               of git). Set it when you run, e.g.:  CAM_PASS=secret ./dev/restream-camera.sh
#   CAM_IP    : the camera's IP            (default: the dev camera)
#   CAM_USER  : the camera's user          (default: admin)
#   NIC_IP    : THIS PC's IP on the camera's network (the card facing the camera)
#   MCAST     : multicast group:port the backend's camera is pointed at
# Example:  CAM_PASS=secret CAM_IP=132.8.7.50 NIC_IP=132.8.7.2 ./dev/restream-camera.sh
set -euo pipefail

CAM_IP="${CAM_IP:-132.8.7.112}"
CAM_USER="${CAM_USER:-admin}"
CAM_PASS="${CAM_PASS:?set CAM_PASS to the camera password (kept out of git)}"
CAM_PATH="${CAM_PATH:-/onvif-media/media.amp?profile=profile_1_h264}"   # Axis path; yours may differ
NIC_IP="${NIC_IP:-132.8.7.1}"
MCAST="${MCAST:-226.0.0.1:5001}"

RTSP="rtsp://${CAM_USER}:${CAM_PASS}@${CAM_IP}:554${CAM_PATH}"
OUT="rtp://${MCAST%:*}:${MCAST#*:}?localaddr=${NIC_IP}&ttl=16&pkt_size=1316"

# ENCODER=h264_nvenc moves the decode and the encode onto an NVIDIA GPU's own
# video chips (NVDEC, NVENC), leaving the CPU free; the default, libx264, runs
# on any PC (the Mac included).
ENCODER="${ENCODER:-libx264}"
# DECODE is empty on the default path; "${DECODE[@]+...}" below keeps `set -u` from
# failing on an empty array in Bash older than 4.4 (macOS ships 3.2)
if [ "$ENCODER" = "h264_nvenc" ]; then
  DECODE=(-hwaccel cuda -hwaccel_output_format cuda)
  ENCODE=(-c:v h264_nvenc -preset p1 -tune ull -profile:v main -rc cbr -zerolatency 1 -delay 0
          -b:v 8M -maxrate 8M -bufsize 1M -bf 0 -g 25 -bsf:v dump_extra=freq=keyframe)
else
  DECODE=()
  ENCODE=(-c:v libx264 -preset veryfast -tune zerolatency -profile:v main -pix_fmt yuv420p
          -bf 0 -g 50 -x264-params repeat-headers=1)
fi

echo "[restream] camera  : ${CAM_IP}"
echo "[restream] multicast: ${MCAST} via NIC ${NIC_IP}"
echo "[restream] In the app, point the camera at multicast ${MCAST%:*}, port ${MCAST#*:},"
echo "[restream] and pick the network card whose IP is ${NIC_IP} (e.g. en8 / Ethernet)."

while true; do
  echo "[restream] $(date '+%H:%M:%S') connecting to camera..."
  # Low delay on the way in (the Detection Service opens its streams the same way,
  # new_bullet_holes.STREAM_CAPTURE_OPTIONS): a short probe, because by default
  # ffmpeg buffers a couple of seconds of stream to learn what it holds and then
  # stays that far behind; and one decoder thread, because each decoder thread
  # holds back about a frame
  ffmpeg -nostdin -loglevel warning \
    -rtsp_transport tcp -timeout 8000000 \
    -probesize 32768 -analyzeduration 100000 -threads 1 \
    ${DECODE[@]+"${DECODE[@]}"} -i "$RTSP" \
    -an "${ENCODE[@]}" \
    -f rtp -payload_type 96 "$OUT" || true
  echo "[restream] $(date '+%H:%M:%S') ffmpeg stopped; reconnecting in 2s"
  sleep 2
done

# ── Camera-status recovery speed (CAMERA_SYNC_INTERVAL_S) ────────────────────
# The backend polls MediaMTX every CAMERA_SYNC_INTERVAL_S seconds (default 5) to
# decide live / no-signal. Lower = faster status flips (we use 2 in dev). Start
# the backend with it set, e.g.:
#   cd WebApp/backend && CAMERA_SYNC_INTERVAL_S=2 uv run uvicorn app.main:app \
#       --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 2
# (On macOS also prefix: DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib)
