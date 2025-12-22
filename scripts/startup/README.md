# Startup Script for PacketProcessingService (Linux)

This script automatically starts the PacketProcessingService dotnet program on system boot, provided that the docker compose stack `kanatbackend` is running.

## Overview

The Linux startup script will:
1. Wait for Docker to be available
2. Check if the docker compose stack (`kanatbackend-prod` or `kanatbackend-dev`) is running
3. Wait for the stack to start if it's not yet running (up to 5 minutes)
4. Start the PacketProcessingService dotnet application
5. Log all activities to `~/.kanat-backend/logs/`

## Linux Installation

### One-time automatic setup (systemd + GNOME indicator)

To automatically configure Docker on boot, the systemd service, and the GNOME top-bar status icon:

1. From the project root, run:
   ```bash
   sudo bash scripts/startup/setup-linux-startup.sh
   ```

2. Then, as your normal user (not root):
   - Restart GNOME Shell  
     - On X11: press `Alt+F2`, type `r`, press Enter  
     - On Wayland: log out and log back in
   - Enable the extension:
     ```bash
     gnome-extensions enable dotnet-port-status@kanatbackend
     ```

The top bar will then show a green/red icon based on `localhost:10900` (dotnet prod) status.

### Ensure Docker engine starts on boot

1. Enable and start the Docker daemon:
   ```bash
   sudo systemctl enable docker
   sudo systemctl start docker
   systemctl is-enabled docker
   ```

### Option 1: Systemd Service (Recommended)

1. Edit `start-dotnet-on-boot-linux.service` and update the path in `ExecStart`:
   ```ini
   ExecStart=/bin/bash -c '/absolute/path/to/KanatBackend/scripts/startup/start-dotnet-on-boot-linux.sh'
   ```

2. Make the script executable:
   ```bash
   chmod +x start-dotnet-on-boot-linux.sh
   ```

3. Copy and enable the service (runs at boot, headless):
   ```bash
   sudo cp start-dotnet-on-boot-linux.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable start-dotnet-on-boot-linux.service
   sudo systemctl restart start-dotnet-on-boot-linux.service
   ```

4. Check status:
   ```bash
   sudo systemctl status start-dotnet-on-boot-linux.service
   ```

5. View logs:
   ```bash
   journalctl -u start-dotnet-on-boot-linux.service -n 200 -f
   ```

### Option 2: Crontab (simple fallback)

1. Make the script executable:
   ```bash
   chmod +x start-dotnet-on-boot-linux.sh
   ```

2. Edit crontab:
   ```bash
   crontab -e
   ```

3. Add this line (update the path):
   ```
   @reboot /absolute/path/to/KanatBackend/scripts/startup/start-dotnet-on-boot-linux.sh
   ```

### GNOME top-bar status icon (native Shell extension)

A GNOME Shell extension is included to show a native status icon in the top bar (right side) that reflects the health of the dotnet prod port (`localhost:10900`):

- Green icon: port 10900 reachable (online)
- Red icon: port 10900 unreachable (offline)

The extension source is in:

- `scripts/gnome-extension/dotnet-port-status@kanatbackend`

If you do not use the automatic setup script, you can install it manually on your Ubuntu GNOME system:

1. Copy the extension to your user extensions directory:
   ```bash
   mkdir -p ~/.local/share/gnome-shell/extensions
   cp -r scripts/gnome-extension/dotnet-port-status@kanatbackend \
         ~/.local/share/gnome-shell/extensions/
   ```

2. Restart GNOME Shell:
   - On X11: press `Alt+F2`, type `r`, press Enter  
   - On Wayland: log out and log back in

3. Enable the extension:
   ```bash
   gnome-extensions enable dotnet-port-status@kanatbackend
   ```

Once enabled, the icon will poll `127.0.0.1:10900` every few seconds and show the status natively in the GNOME top bar.

### Optional: Open a terminal with live dotnet logs on login

Systemd runs at boot without a GUI, so it can't reliably pop up a terminal window.  
If you want to **see logs live in a terminal after you log in**, use a desktop autostart entry:

1. Create the autostart directory (if it doesn't exist):
   ```bash
   mkdir -p ~/.config/autostart
   ```

2. Create an autostart file:
   ```bash
   nano ~/.config/autostart/packetprocessing-console.desktop
   ```

3. Put this content inside (adjust the path if your project is not on `Desktop`):
   ```ini
   [Desktop Entry]
   Type=Application
   Name=PacketProcessingService Console
   Exec=gnome-terminal -- bash -lc 'tail -n 200 -F ~/.kanat-backend/logs/dotnet-*.log; exec bash'
   X-GNOME-Autostart-enabled=true
   ```

This will:
- Start normally via systemd on boot (headless, reliable)
- Open a terminal on login that tails the dotnet logs so you can see live output

## Cleanup / Uninstall

To completely remove all startup components (systemd service, Docker containers, GNOME extension, etc.):

```bash
sudo bash scripts/startup/cleanup-linux-startup.sh
```

This script will:
- Stop and remove the systemd service
- Kill all PacketProcessingService dotnet processes
- Stop and remove all kanatbackend Docker containers (prod and dev)
- Remove the GNOME Shell extension
- Remove autostart entries

**To also remove Docker volumes** (⚠️ **this deletes all database data**):

```bash
sudo bash scripts/startup/cleanup-linux-startup.sh --remove-volumes
```

**Note**: Log files in `~/.kanat-backend/logs/` are preserved. Remove them manually if needed:
```bash
rm -rf ~/.kanat-backend/logs
```

## Configuration

The script supports the `KANAT_ENV` environment variable to specify which environment to use:
- `prod` (default)
- `dev`

The script automatically detects which docker compose stack is running and use that environment.

## Troubleshooting

### Script doesn't start on boot

- Check systemd service status: `sudo systemctl status start-dotnet-on-boot-linux.service`
- Check service logs: `journalctl -u start-dotnet-on-boot-linux.service -f`
- Verify the service is enabled: `sudo systemctl is-enabled start-dotnet-on-boot-linux.service`

### Docker not found

- Ensure Docker is installed and in the system PATH
- Ensure Docker daemon is running: `sudo systemctl status docker`
- The script will wait up to 5 minutes for Docker to become available

### Docker compose stack not running

- Ensure the docker compose stack is configured to start on boot (separate configuration)
- The script will wait up to 5 minutes for the stack to start
- Check docker compose status: `docker compose -p kanatbackend-prod ps`

### PacketProcessingService already running

- The script checks if the service is already running and skips startup if it is
- To manually stop: `pkill -f "PacketProcessingService.dll"`

### Permission issues

- Ensure scripts are executable: `chmod +x start-dotnet-on-boot-linux.sh`
- Systemd service may need specific user permissions - check the service file user/group settings

## Log Files

The script logs to:
- `~/.kanat-backend/logs/startup-YYYYMMDD-HHMMSS.log`

Each run creates a new log file with a timestamp.

You can also view systemd service logs:
- `journalctl -u start-dotnet-on-boot-linux.service -f`
