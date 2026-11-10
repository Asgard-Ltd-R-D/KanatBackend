# VideoService

MediaMTX (binary not committed) plus the GStreamer recorders that join each camera's multicast and publish it to MediaMTX over RTSP. MediaMTX runs on the host, from this folder as its working directory, on macOS, Linux and Windows. Start at `README.md`.

## Files

| File | What |
|---|---|
| `mediamtx.yml` | Config: RTSP `:8554`, WebRTC `127.0.0.1:8889`, Control API `127.0.0.1:9997`, Playback `127.0.0.1:9996`, recordings in `recordings/`. The backend reads it too (mounted read-only into its container). |
| `run_record.sh` | The recorder on macOS/Linux. Watches its parent and stops when MediaMTX stops. |
| `run_record.ps1` | The recorder on Windows. MediaMTX's job object stops it with MediaMTX. |
| `recordings/`, `replay-cache/` | Data, not code. |
| `run_loopdemo.sh`, `recorddemo_*.sh`, `H264.mp4`, `bash.sh`, `setup.sh`, `install.sh` | From the earlier project. |

## Rules

- **Never delete or rewrite the earlier project's files** (loopdemo, recorddemo, `H264.mp4`, the setup scripts) even if unused: leave them alone.
- **The backend adds each camera's path** through the Control API, with `runOnInit` running `./run_record.sh` or `./run_record.ps1` (`WebApp/backend/app/services/camera_sync.py`, `RECORD_LAUNCHER`). The relative path relies on MediaMTX's working directory being this folder.
- **The two recorders must stay equivalent:** same pipeline and arguments (`udpsrc` → `rtpjitterbuffer` → `rtph264depay` → `h264parse` → `rtspclientsink protocols=tcp`), same parameters and defaults, restart after 2 s. Change one, change the other.
- **`run_record.ps1` targets Windows PowerShell 5.1** (see `WebApp/deploy/windows/CLAUDE.md` for its traps) and has CRLF line endings; `run_record.sh` has LF (`.gitattributes`).
- **Ports bound to 127.0.0.1 stay local.** On Windows, the installer also blocks `mediamtx.exe` from the network; the containers reach it through `host.docker.internal`.
- **MediaMTX forgets the cameras when it restarts**; the backend re-adds them on its next sync.
- **The MediaMTX version** is pinned in `WebApp/deploy/windows/build-bundle.sh`; check its release notes before changing config keys.
