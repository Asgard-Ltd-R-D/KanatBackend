# Windows installer

The installers that put KANAT on a Windows 10 22H2 (build 19045+) or 11 PC, with no internet and no Docker. `README.md` is the operator's guide.

| File | What |
|---|---|
| `build-installer.ps1` | Runs on a Windows PC. Checks the build's inputs (Inno Setup, MediaMTX against its pinned SHA-256, the GTK3 runtime, the model, the CUDA PyTorch environment), parses the scripts, stages `build\stage\` (app, backend, detection, video, scripts) and compiles `kanat.iss` once per run mode into `build\output\KANAT-Setup-<version>-<threads\|processes>.exe`, with `SHA256SUMS.txt`. |
| `kanat.iss` | The Inno Setup script: copies the files to `C:\Program Files\KANAT`, asks which adapter the cameras are on, runs `install-services.ps1`, makes the shortcuts and the optional start with Windows, and removes the tasks on uninstall. |
| `scripts\install-services.ps1` | Run by the installer as Administrator: `kanat-config.json` (with the Logs-tab password hash), firewall, the cameras' adapter and multicast route, power, the three scheduled tasks, a health check. Safe to run again. |
| `scripts\run.ps1` | What each task runs: one component (mediamtx, backend, detection), started again with a growing wait when it exits. At start it ends only what is left of its own component (`Stop-KanatProcesses -Only`), never what the other two tasks run. |
| `tests\stop-kanat-processes.test.ps1` | Checks that cleanup helper on a fake install folder (also a step in `.github/workflows/windows.yml`). |
| `scripts\uninstall-services.ps1` | Stops KANAT and removes its tasks and firewall rules (`-StopOnly` just stops, before an update copies files). |
| `scripts\kanat-common.ps1` | Shared: the task names, the data and log folders, `Write-Utf8`, `Stop-KanatProcesses`. |
| `mediamtx.yml` | MediaMTX's production config: `VideoService\mediamtx.yml` without its development path. Keep it ASCII: the backend reads it. |

## How it runs on the PC

- **Installed** to `C:\Program Files\KANAT`, which nothing writes to while KANAT runs: `app\` (Electron), `backend\{python,gtk,service}`, `detection\{python,service}`, `video\`, `scripts\`. Each Python is its own copy with its packages, so the PC needs none.
- **Data** in `C:\ProgramData\Kanat`: `kanat.db`, `logs\`, `kanat-config.json`. Kept when KANAT is updated or removed.
- **Three scheduled tasks** (`KANAT MediaMTX`, `KANAT Backend`, `KANAT Detection`), at startup, as SYSTEM, each running `run.ps1`. The backend applies its migrations before it serves. Detection runs `detection.supervisor`, which runs the service and restarts it.
- **One installer per run mode** (`--run-mode thread` or `process`): the same product and `AppId`, so one installed over the other changes the mode.
- **Nothing for development goes in:** no `dev/` bridges, no MediaMTX demo path, no tests or evaluation tools, no database.

## Rules

- **Windows PowerShell 5.1**, not PowerShell 7. Its traps:
  - `"$var:"` is a parse error; write `"${var}:"`.
  - `-Encoding UTF8` writes a byte order mark that JSON readers refuse; use `Write-Utf8`.
  - `ConvertTo-Json` stops at depth 2; pass `-Depth 20`.
  - Native programs don't throw: check `$LASTEXITCODE`.
  - CRLF line endings (`.gitattributes`).
- **Every input is pinned and checked:** MediaMTX by SHA-256 (changing its version means changing both in `build-installer.ps1`), Inno Setup 6, the tested detection environment (the CUDA PyTorch in `ImageRecognitionService\.venv`).
- **Nothing from a developer's database goes in the installer:** the database starts empty on the PC.
- **Every failure prints `FAILED: <what> (<what to do>)`**, so an operator can send that one line.
- **Before building:** the build parses every script; run PSScriptAnalyzer too.
- **The logs password** is a scrypt hash in `scripts\install-services.ps1` (`admin` today); change it by generating a new hash, as the comment there shows.
- **Not verifiable on a development PC:** the firewall, the multicast route, the scheduled tasks as SYSTEM, the real cameras. Say so; don't claim it works until it has been run on a range PC.
