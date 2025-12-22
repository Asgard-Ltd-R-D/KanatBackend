#!/usr/bin/env bash
# scripts/startup/setup-linux-startup.sh
#
# One-time automatic setup (systemd + GNOME indicator) for PacketProcessingService.
# Run from project root:
#   sudo bash scripts/startup/setup-linux-startup.sh
#
# What it does:
# - Ensures Docker Engine is enabled on boot and started now
# - Installs & enables the systemd service that runs start-dotnet-on-boot-linux.sh at boot
# - Installs the GNOME Shell extension (per-user) for the invoking user (SUDO_USER)
# - Creates an optional GNOME autostart entry to open a terminal that tails systemd logs on login
#
# Notes:
# - GNOME extension will appear only after user logs in and restarts GNOME Shell (X11 Alt+F2 r / Wayland logout/login).
# - This script is safe to re-run; it overwrites/refreshes the installed unit/extension/autostart entry.

set -euo pipefail

# -------------------------------
# Helpers
# -------------------------------
log()  { echo -e "\033[1;34m[setup]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m  $*"; }
err()  { echo -e "\033[1;31m[err]\033[0m   $*"; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    err "This script must be run with sudo/root."
    exit 1
  fi
}

detect_user() {
  # Prefer the user who invoked sudo; fallback to logname
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    TARGET_USER="${SUDO_USER}"
  else
    TARGET_USER="$(logname 2>/dev/null || true)"
    if [[ -z "${TARGET_USER}" || "${TARGET_USER}" == "root" ]]; then
      err "Could not determine the non-root user (SUDO_USER/logname). Run via: sudo bash ..."
      exit 1
    fi
  fi

  TARGET_HOME="$(eval echo "~${TARGET_USER}")"
  if [[ ! -d "${TARGET_HOME}" ]]; then
    err "Home directory not found for user: ${TARGET_USER} (${TARGET_HOME})"
    exit 1
  fi
}

project_root() {
  # This script is expected at: <root>/scripts/startup/setup-linux-startup.sh
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
}

install_deps() {
  # We only require gnome extension tooling if GNOME is used.
  # But installing these deps is harmless and makes first-time setup smoother.
  log "Installing required packages (if missing)..."
  apt-get update -y >/dev/null
  apt-get install -y \
    gnome-shell-extensions \
    gnome-shell-extension-manager \
    gnome-extensions-app \
    >/dev/null || true
}

ensure_docker_engine() {
  log "Ensuring Docker Engine is enabled on boot and running..."
  systemctl enable docker >/dev/null
  systemctl start docker >/dev/null

  # Basic sanity check
  if ! docker info >/dev/null 2>&1; then
    warn "docker info failed. If you use Docker Desktop, switch to Docker Engine context 'default' later."
  fi

  # Enforce Docker Engine context for the target user (avoid desktop-linux socket in CLI)
  log "Forcing Docker context to 'default' for user '${TARGET_USER}'..."
  runuser -u "${TARGET_USER}" -- bash -lc 'docker context use default >/dev/null 2>&1 || true; unset DOCKER_HOST'
}

install_systemd_service() {
  local unit_src="${PROJECT_ROOT}/scripts/startup/start-dotnet-on-boot-linux.service"
  local unit_dst="/etc/systemd/system/start-dotnet-on-boot-linux.service"
  local script_path="${PROJECT_ROOT}/scripts/startup/start-dotnet-on-boot-linux.sh"

  if [[ ! -f "${script_path}" ]]; then
    err "Startup script not found: ${script_path}"
    exit 1
  fi

  # Make script executable
  chmod +x "${script_path}"

  # If a service template is not present, generate a robust unit file.
  if [[ ! -f "${unit_src}" ]]; then
    warn "Service file not found at ${unit_src}. Generating one..."
    cat > "${unit_src}" <<EOF
[Unit]
Description=Start PacketProcessingService after Docker is ready
After=docker.service network-online.target NetworkManager-wait-online.service
Wants=network-online.target NetworkManager-wait-online.service
Requires=docker.service

[Service]
Type=simple
User=${TARGET_USER}
Environment=HOME=${TARGET_HOME}
WorkingDirectory=${PROJECT_ROOT}

# Ensure Docker Engine context (avoid Docker Desktop socket/context)
ExecStart=/bin/bash -lc 'docker context use default >/dev/null 2>&1 || true; unset DOCKER_HOST; ${script_path}'

Restart=on-failure
RestartSec=5

StartLimitIntervalSec=300
StartLimitBurst=60

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
  else
    log "Service template exists. Installing it to systemd..."
    # Best-effort: if template has placeholders, user should keep it correct.
    # We'll still install it as-is.
  fi

  log "Installing systemd service: start-dotnet-on-boot-linux.service"
  cp -f "${unit_src}" "${unit_dst}"
  systemctl daemon-reload >/dev/null
  systemctl enable start-dotnet-on-boot-linux.service >/dev/null
  systemctl restart start-dotnet-on-boot-linux.service >/dev/null
}

install_gnome_extension() {
  local ext_src="${PROJECT_ROOT}/scripts/gnome-extension/dotnet-port-status@kanatbackend"
  local ext_dst="${TARGET_HOME}/.local/share/gnome-shell/extensions/dotnet-port-status@kanatbackend"

  if [[ ! -d "${ext_src}" ]]; then
    warn "GNOME extension source not found: ${ext_src}"
    warn "Skipping GNOME extension install."
    return 0
  fi

  log "Installing GNOME Shell extension for user '${TARGET_USER}'..."
  mkdir -p "${TARGET_HOME}/.local/share/gnome-shell/extensions"

  # Refresh install (remove old copy)
  rm -rf "${ext_dst}"
  cp -r "${ext_src}" "${ext_dst}"
  chown -R "${TARGET_USER}:${TARGET_USER}" "${ext_dst}"

  log "GNOME extension installed at: ${ext_dst}"
  warn "You still need to restart GNOME Shell and enable it as the user:"
  warn "  gnome-extensions enable dotnet-port-status@kanatbackend"
}

create_autostart_terminal() {
  local autostart_dir="${TARGET_HOME}/.config/autostart"
  local desktop_file="${autostart_dir}/packetprocessing-console.desktop"

  log "Creating GNOME autostart entry (tails systemd logs in a terminal on login)..."
  mkdir -p "${autostart_dir}"

  cat > "${desktop_file}" <<'EOF'
[Desktop Entry]
Type=Application
Name=PacketProcessingService Console
Comment=Tail PacketProcessingService systemd logs after login
Exec=gnome-terminal -- bash -lc 'journalctl -u start-dotnet-on-boot-linux.service -n 200 -f; exec bash'
X-GNOME-Autostart-enabled=true
Terminal=false
Categories=Utility;
EOF

  chown "${TARGET_USER}:${TARGET_USER}" "${desktop_file}"
  chmod 0644 "${desktop_file}"
}

print_next_steps() {
  echo
  log "Setup complete."
  echo
  echo "Next steps (run as ${TARGET_USER}, NOT root):"
  echo "1) Restart GNOME Shell:"
  echo "   - X11: Alt+F2, type r, Enter"
  echo "   - Wayland: log out and log back in"
  echo "2) Enable the GNOME extension (if installed):"
  echo "   gnome-extensions enable dotnet-port-status@kanatbackend"
  echo
  echo "Verify systemd service:"
  echo "  sudo systemctl status start-dotnet-on-boot-linux.service --no-pager"
  echo "  journalctl -u start-dotnet-on-boot-linux.service -n 200 --no-pager"
  echo
  echo "Tip: Ensure Docker CLI uses Docker Engine:"
  echo "  docker context use default"
  echo "  unset DOCKER_HOST"
  echo
}

# -------------------------------
# Main
# -------------------------------
require_root
detect_user
project_root

log "Project root: ${PROJECT_ROOT}"
log "Target user:  ${TARGET_USER}"
log "Target home:  ${TARGET_HOME}"

install_deps
ensure_docker_engine
install_systemd_service
install_gnome_extension
create_autostart_terminal
print_next_steps
