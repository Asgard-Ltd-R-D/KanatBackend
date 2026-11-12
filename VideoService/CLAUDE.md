# VideoService

MediaMTX (binary not committed). MediaMTX reads each camera's RTP multicast directly (the WebApp backend sets a `udp+rtp://` source per camera through the Control API); the GStreamer `run_record` scripts here are the earlier project's, left for other uses and not in this pipeline. MediaMTX runs on the host, from this folder as its working directory, on macOS, Linux and Windows. Start at `README.md`.

## Files

| File | What |
|---|---|
| `mediamtx.yml` | Config: RTSP `:8554`, WebRTC `127.0.0.1:8889`, Control API `127.0.0.1:9997`. The backend reads it too (mounted read-only into its container). |
| `run_record.sh`, `run_record.ps1`, `run_loopdemo.sh`, `recorddemo_*.sh`, `H264.mp4`, `bash.sh`, `setup.sh`, `install.sh` | From the earlier project; not used by the WebApp pipeline, kept for other uses. |

## Rules

- **Never delete or rewrite the earlier project's files** (loopdemo, recorddemo, `H264.mp4`, the setup scripts) even if unused: leave them alone.
- **The backend adds each camera's path** through the Control API, with a `udp+rtp://` source MediaMTX reads directly (`WebApp/backend/app/services/camera_sync.py`). The relative paths in `mediamtx.yml` rely on MediaMTX's working directory being this folder.
- **The `run_record` scripts are the earlier project's**, kept for other uses. If you edit them, keep the two equivalent (same GStreamer pipeline, parameters and defaults); `run_record.ps1` targets Windows PowerShell 5.1 and has CRLF line endings, `run_record.sh` has LF (`.gitattributes`).
- **Ports bound to 127.0.0.1 stay local.** On Windows, the installer also blocks `mediamtx.exe` from the network; the containers reach it through `host.docker.internal`.
- **MediaMTX forgets the cameras when it restarts**; the backend re-adds them on its next sync.
- **The MediaMTX version** is pinned in `WebApp/deploy/windows/build-bundle.sh`; check its release notes before changing config keys.
