# KANAT on a Windows PC

`KANAT-Setup-<version>-threads.exe` and `KANAT-Setup-<version>-processes.exe` install everything KANAT needs on a Windows PC, with no internet. They are built by `build-installer.ps1` into `WebApp\deploy\windows\build\output`.

| Installer | Detection Service |
|---|---|
| **threads** | Every camera's Run is a thread of one process, all sharing one model. Uses the least memory. |
| **processes** | Every camera's Run is a process of its own, with its own model. A stuck camera is killed alone, without restarting the others. About 4 times the memory with 4 cameras (about 17 GB more on the development PC). |

They are the same product: installing one over the other changes the mode and keeps the data.

| Part | Runs |
|---|---|
| The backend (with its SQLite database) | Windows, a background task, started with Windows |
| The Detection Service | Windows, a background task, started with Windows; its supervisor restarts it if it stops or freezes |
| MediaMTX, reading each camera's multicast | Windows, a background task, started with Windows |
| The KANAT app | Windows (Start menu, desktop, optionally when Windows starts) |

Nothing else is needed on the PC: no Python, no Node, no Docker. The database starts empty. The app's Logs tab reads the services' log files directly, so there is no log stack to run.

## Before you start

- **Windows:** Windows 10 22H2 (build 19045) or Windows 11, 64-bit.
- **Hardware:** an NVIDIA GPU with its Windows driver installed (the model runs on it), 16 GB RAM or more, and 15 GB free on `C:`.
- **User account:** an administrator runs the installer. The services run as the system, so they start without anyone logged in.
- **Not code-signed:** Windows SmartScreen may warn about an unknown publisher. "More info", then "Run anyway".

## Install

1. Copy the installer to the PC and run it. Accept the administrator prompt.
2. **Which adapter are the cameras on?** Choose it from the list. KANAT sets it to the Private network profile and routes the cameras' multicast through it. On a PC with one adapter, let Windows choose.
3. Wait for the install to finish (a minute or two after the files are copied: it starts the services and checks them). KANAT opens when you tick "Open KANAT".
4. In the app, add the cameras in Settings.
5. Turn on automatic login, so the range comes back by itself after a power cut. Run `netplwiz`, select the user, and clear "Users must enter a user name and password to use this computer".

Silent install, for a script: `KANAT-Setup-0.1.0-threads.exe /VERYSILENT /SUPPRESSMSGBOXES /CameraAdapter="Ethernet 2"`.

The Logs tab asks for the engineer password.

## What it changes on the PC

- **Files:**
  - `C:\Program Files\KANAT`: the app, the backend, the Detection Service with its model, MediaMTX, and the scripts. Nothing in it is written to while KANAT runs.
  - `C:\ProgramData\Kanat\kanat.db`: the database.
  - `C:\ProgramData\Kanat\logs`: every service's log (`backend.log`, `detection.log`, `frontend.log`), what each prints when it fails to start (`<service>.out.log`, `.err.log`), `launcher.log` and `installer.log`.
  - `C:\ProgramData\Kanat\kanat-config.json`: the app's settings and the Logs-tab password's hash.
- **Task Scheduler:** `KANAT MediaMTX`, `KANAT Backend` and `KANAT Detection`, run as the system at startup. Each is kept running: a service that exits starts again after 1 s, then 2, 4, up to 30 s.
- **Firewall:** MediaMTX is allowed inbound UDP (the cameras' multicast); its TCP ports (RTSP, the control API) are blocked from the network. The backend and the Detection Service listen on this PC only.
- **Network:** the camera adapter is set to the Private profile, and a persistent route sends `224.0.0.0/4` (multicast) through it.
- **Power:** the PC never sleeps or hibernates (on AC power).
- **Programs:** KANAT, in Programs and Features.

What is **not** in the installer: the development camera bridges (`dev/`), the earlier project's GStreamer demo path in MediaMTX's config, tests, evaluation tools, the other models, and any database. In use, the cameras' multicast is the only video source.

## Update

Run a newer installer (or the other mode's). It stops the services, replaces the files, and starts them again. The database, the logs and the settings stay.

## Uninstall

Programs and Features, KANAT. It stops KANAT and removes its tasks, firewall rules and files. The database, the logs and `kanat-config.json` stay in `C:\ProgramData\Kanat`: delete that folder to remove them. The multicast route and the power settings stay, as they belong to the PC.

## When something doesn't work

| Symptom | Look at |
|---|---|
| The app says the backend is offline | Task Scheduler: is `KANAT Backend` running? `C:\ProgramData\Kanat\logs\backend.err.log` and `launcher.log` |
| A camera shows "No signal" | Is `KANAT MediaMTX` running? Is the firewall rule `KANAT MediaMTX camera video` there? Are the adapter and the route right (`route print 224*`)? |
| Detection never says ready | `detection.log`, `detection.err.log`: it loads the model first (a few seconds, longer the first time after boot) |
| The installer said setting the PC up failed | The last line starting with `FAILED` in `C:\ProgramData\Kanat\logs\installer.log`; run the installer again once it is fixed |
| Anything | The app's Logs tab, or the files in `C:\ProgramData\Kanat\logs` |

## Building the installers

On a Windows PC with the repository, from `WebApp\deploy\windows`:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-installer.ps1
```

It needs Node, `uv`, Inno Setup 6 (`winget install JRSoftware.InnoSetup`), the GTK3 runtime (WeasyPrint's Pango), `VideoService\mediamtx.exe` (the pinned release; its SHA-256 is checked), the detection model, and `ImageRecognitionService\.venv` with PyTorch for CUDA: the tested environment is what ships. `-Variant threads` or `processes` builds one; `-Spanning` splits an installer that would pass 2 GB.
