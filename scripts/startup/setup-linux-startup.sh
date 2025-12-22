#!/usr/bin/env bash
#
# One-time setup script for Linux (Ubuntu + GNOME)
# - Enables Docker engine on boot
# - Installs and enables the systemd service to start PacketProcessingService on boot
# - Installs the GNOME Shell extension for dotnet port status (localhost:10900)
#
# Usage:
#   sudo bash scripts/startup/setup-linux-startup.sh
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== KanatBackend Linux startup setup ==="
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

echo "Running setup for user: $TARGET_USER (home: $TARGET_HOME)"

echo
echo "=== Step 1: Ensure Docker engine starts on boot ==="
systemctl enable docker
systemctl start docker
systemctl is-enabled docker || echo "WARNING: docker service is not enabled"

echo
echo "=== Step 2: Install and enable systemd service for PacketProcessingService ==="

SERVICE_DEST="/etc/systemd/system/start-dotnet-on-boot-linux.service"
SCRIPT_DEST="/home/asgard/$PROJECT_ROOT/scripts/startup/start-dotnet-on-boot-linux.sh"

if [[ ! -f "$SCRIPT_DEST" ]]; then
  echo "ERROR: Startup script not found at $SCRIPT_DEST"
  exit 1
fi

chmod +x "$SCRIPT_DEST"

cat > "$SERVICE_DEST" <<EOF
[Unit]
Description=Start PacketProcessingService after Docker is ready
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=$TARGET_USER
WorkingDirectory=$PROJECT_ROOT

ExecStart=$SCRIPT_DEST

Restart=on-failure
RestartSec=5

StartLimitIntervalSec=300
StartLimitBurst=60

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable start-dotnet-on-boot-linux.service
systemctl restart start-dotnet-on-boot-linux.service || echo "WARNING: Service failed to start, check logs with: journalctl -u start-dotnet-on-boot-linux.service -n 200 -f"

echo
echo "=== Step 3: Install GNOME Shell extension (dotnet port status) ==="

EXT_SRC="$PROJECT_ROOT/scripts/gnome-extension/dotnet-port-status@kanatbackend"
EXT_DEST="$TARGET_HOME/.local/share/gnome-shell/extensions/dotnet-port-status@kanatbackend"

if [[ ! -d "$EXT_SRC" ]]; then
  echo "ERROR: Extension source not found at: $EXT_SRC"
  exit 1
fi

mkdir -p "$(dirname "$EXT_DEST")"
cp -r "$EXT_SRC" "$EXT_DEST"
chown -R "$TARGET_USER":"$TARGET_USER" "$TARGET_HOME/.local"

echo
echo "=== Done ==="
echo "Next steps (run as $TARGET_USER, not root):"
echo "  1) Restart GNOME Shell:"
echo "     - On X11: press Alt+F2, type 'r', press Enter"
echo "     - On Wayland: log out and log back in"
echo "  2) Enable the extension:"
echo "     gnome-extensions enable dotnet-port-status@kanatbackend"
echo "The top bar will then show a green/red icon based on localhost:10900 (dotnet prod) status."


