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

### Docker Desktop startup

1. ```bash
   sudo systemctl enable docker
   sudo systemctl start docker
   systemctl is-enabled docker
   mkdir -p ~/.config/autostart
   nano ~/.config/autostart/docker-desktop.desktop
   ```
   
2. ```ini
   [Desktop Entry]
   Type=Application
   Name=Docker Desktop
   Exec=/usr/bin/docker-desktop
   X-GNOME-Autostart-enabled=true
   ```

### PacketProcessing Teminal Openm

1. ```bash
   nano ~/.config/autostart/packetprocessing.desktop
   ```

2. ```ini
   [Desktop Entry]
   Type=Application
   Name=PacketProcessingService Console
   Exec=gnome-terminal -- bash -lc '%h/Desktop/KanatBackend/scripts/startup/start-dotnet-on-boot-linux.sh; exec bash'
   X-GNOME-Autostart-enabled=true
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

3. Copy and enable the service:
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

### Option 2: Crontab

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
