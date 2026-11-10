# Windows offline install

The bundle that installs KANAT on an offline Windows 10 22H2 (build 19045+) or 11 PC. `README.md` is the operator's guide.

| File | What |
|---|---|
| `build-bundle.sh` | Runs on the Mac. Downloads the pinned installers (checked against their SHA-256), builds the backend and detection images for `linux/amd64`, saves the base images, builds the app's installer, copies the app files, writes `SHA256SUMS.txt`, and zips it all into `~/KanatBundle/KANAT-<version>{/,.zip}`. CPU-only by default; `KANAT_GPU=1` adds the CUDA image (+4 GB). |
| `install.ps1` | Runs on the PC as Administrator: WSL 2, Docker Desktop, GStreamer, the files to `C:\Kanat`, `.env`, `kanat-config.json`, firewall, multicast route, power, images, `docker compose up`, the "KANAT MediaMTX" task, the app, and a health check. Safe to run again: it skips what's done and keeps `.env`, data and logs. |
| `README.md` | Requirements, install, what it changes, update, troubleshooting. |

## How it runs on the PC

- **Docker Desktop (WSL 2):** the backend (with its SQLite database on a volume) and detection (`WebApp/docker-compose.yml`, profile `app`). The app's Logs tab reads the log files directly, so there is no Loki/Grafana stack.
- **Windows:** MediaMTX + GStreamer (Task Scheduler at login), the KANAT app.
- **Containers reach MediaMTX** through `host.docker.internal`; the app reaches everything on `127.0.0.1`.

## Rules

- **Windows PowerShell 5.1**, not PowerShell 7. Its traps:
  - `"$var:"` is a parse error; write `"${var}:"`.
  - `-Encoding UTF8` writes a byte order mark that JSON readers refuse; use the script's `Write-Utf8`.
  - `ConvertTo-Json` stops at depth 2; pass `-Depth 20`.
  - `wsl.exe` writes UTF-16 unless `WSL_UTF8=1`.
  - Native programs don't throw: check `$LASTEXITCODE` (the script's `Run` does).
  - CRLF line endings (`.gitattributes`).
- **Never trust a fixed install path:** Docker Desktop 4.94 installed to `Program Files\Docker\` while older versions use `Docker\Docker\`. Look in every known place, and fail with a clear message.
- **Every download is pinned** to a version at least two weeks old and its publisher's SHA-256. Changing a version means changing its hash.
- **Nothing from a developer's database goes in the bundle:** the database starts empty on the PC.
- **Every failure prints `FAILED: <what> (<what to do>)`**, so an operator can send that one line.
- **Before building a bundle:** parse both `.ps1` files (`[System.Management.Automation.Language.Parser]::ParseFile`) and run PSScriptAnalyzer. CI does this on `windows-latest`.
- **Not verifiable on the Mac:** WSL, Docker Desktop, GStreamer, the firewall, the route, the scheduled task. Say so; don't claim it works until it's been run on a Windows PC.
