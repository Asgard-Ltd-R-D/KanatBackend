#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Portable GStreamer MP4->H264 publisher:
# - Reads MP4 (any codec) -> decodebin -> HW encoder when available -> H.264
# - Mirrors to RTSP (MediaMTX publisher) AND multicast RTP (H264)
# - Picks best encoder per-OS (Apple VT / NVIDIA / Intel QSV/VAAPI / AMD AMF)
###############################################################################

# --- Inputs ---------------------------------------------------------------
ROOT="${ROOT:-$PWD}"
SRC_FILE="${SRC_FILE:-${ROOT}/H264.mp4}"

# MediaMTX envs are passed to runOnInit
RTSP_PORT="${RTSP_PORT:-8554}"
MTX_PATH="${MTX_PATH:-recorddemo}"
URL="${URL:-rtsp://127.0.0.1:${RTSP_PORT}/${MTX_PATH}}"

# Multicast
MCAST_ADDR="${MCAST_ADDR:-226.226.226.112}"
MCAST_PORT="${MCAST_PORT:-112}"
TTL="${TTL:-1}"  # IMPORTANT: use ttl-mc for multicast (not ttl)

# Encoding controls (tweak to taste)
TARGET_BITRATE_KBPS="${TARGET_BITRATE_KBPS:-5000}"   # kbps
KEYINT_SEC="${KEYINT_SEC:-2}"                        # IDR every N seconds
FPS="${FPS:-30}"                                     # optional hint to some encoders

# gst binaries
GSTBIN="${GSTBIN:-$(command -v gst-launch-1.0 || true)}"
GSTINSPECT="${GSTINSPECT:-$(command -v gst-inspect-1.0 || true)}"
if [[ -z "${GSTBIN}" || -z "${GSTINSPECT}" ]]; then
  echo "ERROR: Could not find gst-launch-1.0 or gst-inspect-1.0 in PATH." >&2
  exit 1
fi

# --- Helpers --------------------------------------------------------------
has_element() {
  "${GSTINSPECT}" "$1" >/dev/null 2>&1
}

os_family() {
  case "$(uname -s)" in
    Darwin)  echo "mac";;
    Linux)   echo "linux";;
    MINGW*|MSYS*|CYGWIN*|Windows_NT) echo "windows";;
    *) echo "other";;
  esac
}

pick_encoder() {
  local os; os="$(os_family)"

  # Prefer HW encoders; each block tries a list in order.
  if [[ "$os" == "mac" ]]; then
    # Apple VideoToolbox (macOS)
    if has_element vtenc_h264_hw; then echo "vtenc_h264_hw"; return; fi  # HW-only
    if has_element vtenc_h264;    then echo "vtenc_h264";    return; fi  # HW/SW
  elif [[ "$os" == "linux" ]]; then
    # NVIDIA NVENC
    if has_element nvh264enc;     then echo "nvh264enc";     return; fi
    # Intel Quick Sync (modern plugin)
    if has_element qsvh264enc;    then echo "qsvh264enc";    return; fi
    # Intel VA-API
    if has_element vaapih264enc;  then echo "vaapih264enc";  return; fi
    if has_element vah264enc;     then echo "vah264enc";     return; fi
    # AMD AMF on Linux (rare, but supported in some builds)
    if has_element amfh264enc;    then echo "amfh264enc";    return; fi
  elif [[ "$os" == "windows" ]]; then
    # NVIDIA on Windows (Direct3D11 path), also try CUDA path as a fallback
    if has_element nvd3d11h264enc; then echo "nvd3d11h264enc"; return; fi
    if has_element nvh264enc;      then echo "nvh264enc";      return; fi
    # Intel Quick Sync (MSDK legacy or QSV modern)
    if has_element qsvh264enc;     then echo "qsvh264enc";     return; fi
    if has_element msdkh264enc;    then echo "msdkh264enc";    return; fi
    # AMD AMF for Windows
    if has_element amfh264enc;     then echo "amfh264enc";     return; fi
    # Apple VT not applicable on Windows
  fi

  # Final fallback: software x264enc (portable, high quality, CPU heavy)
  echo "x264enc"
}

encoder_chain() {
  # Echo the encoder pipeline string (from raw video -> H264 elementary stream)
  local enc="$1"
  local keyint="$(( KEYINT_SEC * FPS ))"  # approximate frames per GOP

  case "$enc" in
    vtenc_h264_hw|vtenc_h264)
      # Apple VideoToolbox H.264 (macOS) — prefer low-latency settings
      # Docs: vtenc_h264 + vtenc_h264_hw (Apple VideoToolbox) 
      # https://gstreamer.freedesktop.org/documentation/applemedia/vtenc_h264*.html
      echo "${enc} realtime=true allow-frame-reordering=false max-keyframe-interval=${keyint} bitrate=${TARGET_BITRATE_KBPS} ! h264parse config-interval=-1"
      ;;
    nvd3d11h264enc|nvh264enc)
      # NVIDIA NVENC (Windows/Linux) — low-latency preset when available
      # https://gstreamer.freedesktop.org/documentation/nvcodec/nvh264enc.html
      echo "${enc} preset=llhp bitrate=${TARGET_BITRATE_KBPS} rc=cbr multipass=two-pass-quarter key-int-max=${keyint} ! h264parse config-interval=-1"
      ;;
    qsvh264enc)
      # Intel Quick Sync (modern QSV plugin)
      # https://gstreamer.freedesktop.org/documentation/qsv/qsvh264enc.html
      echo "qsvh264enc rate-control=cbr bitrate=${TARGET_BITRATE_KBPS} gop-size=${keyint} ! h264parse config-interval=-1"
      ;;
    msdkh264enc)
      # Intel MSDK (legacy Quick Sync plugin)
      # https://gstreamer.freedesktop.org/documentation/msdk/msdkh264enc.html
      echo "msdkh264enc rate-control=cbr bitrate=${TARGET_BITRATE_KBPS} gop-size=${keyint} ! h264parse config-interval=-1"
      ;;
    vaapih264enc|vah264enc)
      # Intel VA-API (depends on driver; properties vary slightly)
      # https://people.freedesktop.org/~tsaunier/documentation/vaapi/vaapih264enc.html
      echo "${enc} rate-control=cbr bitrate=${TARGET_BITRATE_KBPS} keyframe-period=${keyint} tune=low-power ! h264parse config-interval=-1"
      ;;
    amfh264enc)
      # AMD AMF (Windows/Linux)
      # https://gstreamer.freedesktop.org/documentation/amfcodec/amfh264enc.html
      echo "amfh264enc usage=transcoding bitrate=${TARGET_BITRATE_KBPS} gop-size=${keyint} ! h264parse config-interval=-1"
      ;;
    x264enc|*)
      # Software fallback
      echo "x264enc tune=zerolatency speed-preset=superfast bframes=0 key-int-max=${keyint} byte-stream=true aud=true pass=cbr bitrate=${TARGET_BITRATE_KBPS} ! video/x-h264,profile=constrained-baseline,stream-format=byte-stream,alignment=au ! h264parse config-interval=-1"
      ;;
  esac
}

DECODER_CHAIN() {
  # Use decodebin to let GStreamer pick HW decoders when present (NVDEC/QSV/VAAPI/VT)
  # For H.264 input files this will decode to raw video; we re-encode to control bitrate.
  echo "decodebin ! videoconvert"
}

###############################################################################
# Build pipeline
###############################################################################
ENC="$(pick_encoder)"
ENC_CHAIN="$(encoder_chain "${ENC}")"
DEC_CHAIN="$(DECODER_CHAIN)"

echo "[INFO] Using encoder: ${ENC}"
echo "[INFO] Source file : ${SRC_FILE}"
echo "[INFO] RTSP URL    : ${URL}"
echo "[INFO] Multicast   : ${MCAST_ADDR}:${MCAST_PORT} (ttl-mc=${TTL})"

trap 'exit 0' INT TERM

while :; do
  "${GSTBIN}" -e \
    filesrc location="${SRC_FILE}" ! \
    qtdemux name=d \
    d.video_0 ! ${DEC_CHAIN} ! ${ENC_CHAIN} ! tee name=t \
      t. ! queue max-size-buffers=0 max-size-time=0 max-size-bytes=0 ! \
            rtspclientsink location="${URL}" protocols=tcp \
      t. ! queue max-size-buffers=0 max-size-time=0 max-size-bytes=0 ! \
            rtph264pay pt=96 config-interval=1 ! \
            multiudpsink clients="${MCAST_ADDR}:${MCAST_PORT}" ttl-mc="${TTL}" sync=false async=false

  # brief pause so MTX doesn't mark path undemanded while we restart
  sleep 0.3
done
