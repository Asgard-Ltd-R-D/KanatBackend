# KANAT on an offline Windows PC

This folder installs everything KANAT needs on a Windows PC with no internet. It's built by `WebApp/deploy/windows/build-bundle.sh`.

| Part | Runs |
|---|---|
| The backend (with its SQLite database) and the Detection Service | Docker Desktop (WSL 2), started with Windows |
| MediaMTX, reading each camera's multicast | on Windows, started by Task Scheduler at login |
| The KANAT app | on Windows (Start menu, desktop) |

The app's Logs tab reads the services' log files directly, so there is no log stack (Loki, Grafana) to run.

Nothing else is needed on the PC: no Python and no Node. The database starts empty.

## Before you start

- **Windows:** Windows 10 22H2 (build 19045) Pro, Enterprise or Education, or Windows 11, 64-bit. Check with `winver`.
- **Virtualization:** turned on in the BIOS/UEFI (Intel VT-x or AMD-V). Task Manager › Performance › CPU shows "Virtualization: Enabled".
- **Hardware:** at least 8 GB RAM (16 GB recommended) and 40 GB free on `C:`.
- **User account:** the Windows account that will run the range is an administrator. Docker Desktop and MediaMTX start when that account logs in.
- **USB drive:** NTFS or exFAT. FAT32 can't hold the image files.
- **GPU (optional):** if the PC has an NVIDIA card, install its Windows driver first. The installer uses the GPU only if Docker can reach it; otherwise the Detection Service runs on the CPU.

## Install

1. Copy this folder to the PC, for example to `C:\KANAT-bundle`.
2. Open PowerShell as Administrator in that folder and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install.ps1 -CameraInterface "Ethernet 2"
   ```

   `-CameraInterface` is the name of the network adapter the cameras are on; `Get-NetAdapter` lists the names. Leave it out to choose from a list.
3. **First run only:** it turns WSL on and asks for a restart. Restart, log in as the same user, and run the same command again.
4. Wait for "KANAT … is installed". The run checks that the backend, MediaMTX and the Detection Service answer.
5. Turn on automatic login, so the range comes back by itself after a power cut. Run `netplwiz`, select the user, and clear "Users must enter a user name and password to use this computer".

Other options:
- `-InstallDir D:\Kanat`: installs somewhere other than `C:\Kanat`.
- `-TimeZone Asia/Jerusalem`: the PC's time zone, as an IANA name.
- `-CpuOnly`: never uses the GPU.

## What it changes on the PC

- **Windows features:** WSL and Virtual Machine Platform turned on, WSL 2.7.14, Docker Desktop 4.94.0 (licence accepted, starts at login, no update checks).
- **Files:**
  - `C:\Kanat\WebApp`: the containers' configuration, with `.env`.
  - `C:\Kanat\VideoService`: MediaMTX and its config.
  - `C:\ProgramData\Kanat\logs`: every service's log.
  - `C:\ProgramData\Kanat\kanat-config.json`: the app's settings.
- **Firewall:**
  - MediaMTX is allowed inbound UDP: the cameras' multicast.
  - MediaMTX's TCP service ports are blocked from the network; it serves this PC only.
- **Network:**
  - The camera adapter is set to the Private profile.
  - A persistent route sends `224.0.0.0/4` (multicast) through it.
- **Power:** the PC never sleeps or hibernates (on AC power).
- **Task Scheduler:** a task named "KANAT MediaMTX".
- **Programs:** the KANAT app (Programs and Features).

## Update

Run `install.ps1` from a newer bundle. It replaces the images and the configuration. The database, the logs and `.env` stay.

## When something doesn't work

Run these from `C:\Kanat\WebApp`:

| Symptom | Look at |
|---|---|
| The app says the backend is offline | `docker compose ps`, `docker compose logs backend` |
| A camera shows "No signal" | Task Scheduler: is "KANAT MediaMTX" running? Is the firewall rule "KANAT MediaMTX camera video" there? Are the camera adapter and the route right (`route print 224*`)? |
| Detection never says ready | `docker compose logs detection` |
| Anything | The app's Logs tab, or the files in `C:\ProgramData\Kanat\logs` |
