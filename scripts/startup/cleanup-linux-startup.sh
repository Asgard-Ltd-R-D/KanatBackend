#!/usr/bin/env bash
#
# Cleanup script for Linux startup components
# - Stops and removes all kanatbackend Docker containers
# - Kills all PacketProcessingService dotnet processes
# - Stops, disables, and removes the systemd service
# - Removes the GNOME Shell extension
# - Removes autostart entries
#
# Usage:
#   sudo bash scripts/startup/cleanup-linux-startup.sh [--remove-volumes]
#
# Options:
#   --remove-volumes    Also remove Docker volumes (data will be lost!)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

REMOVE_VOLUMES=false
if [[ "${1:-}" == "--remove-volumes" ]]; then
    REMOVE_VOLUMES=true
fi

echo "=== KanatBackend Linux startup cleanup ==="
echo "Project root: $PROJECT_ROOT"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "ERROR: This script must be run with sudo (as root)."
  exit 1
fi

if [[ -z "${SUDO_USER:-}" ]]; then
  echo "ERROR: SUDO_USER is not set. Run this script with: sudo bash $0"
  exit 1
fi

TARGET_USER="$SUDO_USER"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"

if [[ -z "$TARGET_HOME" ]]; then
  echo "ERROR: Could not determine home directory for user $TARGET_USER"
  exit 1
fi

echo "Cleaning up for user: $TARGET_USER (home: $TARGET_HOME)"
echo

# Step 1: Stop and remove systemd service
echo "=== Step 1: Stop and remove systemd service ==="
SERVICE_NAME="start-dotnet-on-boot-linux.service"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "Stopping service: $SERVICE_NAME"
    systemctl stop "$SERVICE_NAME" || true
fi

if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "Disabling service: $SERVICE_NAME"
    systemctl disable "$SERVICE_NAME" || true
fi

if [[ -f "$SERVICE_FILE" ]]; then
    echo "Removing service file: $SERVICE_FILE"
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    echo "✓ Systemd service removed"
else
    echo "Service file not found (already removed?)"
fi

# Step 2: Kill all PacketProcessingService dotnet processes
echo
echo "=== Step 2: Kill PacketProcessingService dotnet processes ==="
DOTNET_PIDS=$(pgrep -f "PacketProcessingService.dll" 2>/dev/null || true)
if [[ -n "$DOTNET_PIDS" ]]; then
    echo "Found PacketProcessingService processes: $DOTNET_PIDS"
    for pid in $DOTNET_PIDS; do
        echo "Killing process $pid"
        kill -TERM "$pid" 2>/dev/null || true
    done
    sleep 2
    # Force kill if still running
    DOTNET_PIDS=$(pgrep -f "PacketProcessingService.dll" 2>/dev/null || true)
    if [[ -n "$DOTNET_PIDS" ]]; then
        for pid in $DOTNET_PIDS; do
            echo "Force killing process $pid"
            kill -KILL "$pid" 2>/dev/null || true
        done
    fi
    echo "✓ All PacketProcessingService processes killed"
else
    echo "No PacketProcessingService processes found"
fi

# Step 3: Stop and remove Docker containers
echo
echo "=== Step 3: Stop and remove Docker containers ==="

# Stop and remove prod containers
if docker compose -p kanatbackend-prod -f "$PROJECT_ROOT/docker-compose.prod.yml" ps -q 2>/dev/null | grep -q .; then
    echo "Stopping kanatbackend-prod containers..."
    docker compose -p kanatbackend-prod -f "$PROJECT_ROOT/docker-compose.prod.yml" down || true
    echo "✓ kanatbackend-prod containers stopped and removed"
else
    echo "No kanatbackend-prod containers running"
fi

# Stop and remove dev containers
if docker compose -p kanatbackend-dev -f "$PROJECT_ROOT/docker-compose.dev.yml" ps -q 2>/dev/null | grep -q .; then
    echo "Stopping kanatbackend-dev containers..."
    docker compose -p kanatbackend-dev -f "$PROJECT_ROOT/docker-compose.dev.yml" down || true
    echo "✓ kanatbackend-dev containers stopped and removed"
else
    echo "No kanatbackend-dev containers running"
fi

# Also try to stop containers by name (in case compose files are missing)
CONTAINER_NAMES=(
    "questdb-packets-prod"
    "questdb-packets-dev"
    "postgres-range-prod"
    "postgres-range-dev"
    "seq-prod"
    "seq-dev"
)

for container in "${CONTAINER_NAMES[@]}"; do
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${container}$"; then
        echo "Stopping and removing container: $container"
        docker stop "$container" 2>/dev/null || true
        docker rm "$container" 2>/dev/null || true
    fi
done

# Step 4: Remove Docker volumes (optional)
if [[ "$REMOVE_VOLUMES" == "true" ]]; then
    echo
    echo "=== Step 4: Remove Docker volumes ==="
    VOLUME_NAMES=(
        "kanatbackend_questdb_data_prod"
        "kanatbackend_questdb_logs_prod"
        "kanatbackend_postgres_data_prod"
        "kanatbackend_questdb_data"
        "kanatbackend_questdb_logs"
        "kanatbackend_postgres_data"
        "kanatbackend_seq-data"
    )
    
    for volume in "${VOLUME_NAMES[@]}"; do
        if docker volume ls --format '{{.Name}}' 2>/dev/null | grep -q "^${volume}$"; then
            echo "Removing volume: $volume"
            docker volume rm "$volume" 2>/dev/null || true
        fi
    done
    echo "✓ Docker volumes removed"
else
    echo
    echo "=== Step 4: Docker volumes (skipped) ==="
    echo "Volumes are preserved. Use --remove-volumes to remove them (data will be lost!)"
fi

# Step 5: Remove GNOME Shell extension
echo
echo "=== Step 5: Remove GNOME Shell extension ==="
EXT_DEST="$TARGET_HOME/.local/share/gnome-shell/extensions/dotnet-port-status@kanatbackend"

if [[ -d "$EXT_DEST" ]]; then
    echo "Removing GNOME extension: $EXT_DEST"
    rm -rf "$EXT_DEST"
    echo "✓ GNOME extension removed"
    echo "Note: You may need to restart GNOME Shell for changes to take effect"
else
    echo "GNOME extension not found (already removed?)"
fi

# Step 6: Remove autostart entries
echo
echo "=== Step 6: Remove autostart entries ==="
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
AUTOSTART_FILES=(
    "packetprocessing-console.desktop"
)

for file in "${AUTOSTART_FILES[@]}"; do
    AUTOSTART_FILE="$AUTOSTART_DIR/$file"
    if [[ -f "$AUTOSTART_FILE" ]]; then
        echo "Removing autostart file: $AUTOSTART_FILE"
        rm -f "$AUTOSTART_FILE"
    fi
done

if [[ -d "$AUTOSTART_DIR" ]] && [[ -z "$(ls -A "$AUTOSTART_DIR" 2>/dev/null)" ]]; then
    echo "Removing empty autostart directory: $AUTOSTART_DIR"
    rmdir "$AUTOSTART_DIR" 2>/dev/null || true
fi

echo "✓ Autostart entries removed"

# Step 7: Clean up log files (optional)
echo
echo "=== Step 7: Log files ==="
LOG_DIR="$TARGET_HOME/.kanat-backend/logs"
if [[ -d "$LOG_DIR" ]]; then
    echo "Log directory exists: $LOG_DIR"
    echo "Log files are preserved. To remove them manually:"
    echo "  rm -rf $LOG_DIR"
else
    echo "No log directory found"
fi

echo
echo "=== Cleanup complete ==="
echo
echo "Summary:"
echo "  ✓ Systemd service stopped and removed"
echo "  ✓ PacketProcessingService processes killed"
echo "  ✓ Docker containers stopped and removed"
if [[ "$REMOVE_VOLUMES" == "true" ]]; then
    echo "  ✓ Docker volumes removed"
else
    echo "  ⚠ Docker volumes preserved (use --remove-volumes to remove)"
fi
echo "  ✓ GNOME extension removed"
echo "  ✓ Autostart entries removed"
echo
echo "Note: If GNOME extension was enabled, restart GNOME Shell to see it removed:"
echo "  - On X11: press Alt+F2, type 'r', press Enter"
echo "  - On Wayland: log out and log back in"

