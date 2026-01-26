#!/bin/bash
# Linux startup script to start PacketProcessingService after boot
# This script checks if the docker compose stack is running and starts the dotnet program
#
# Installation:
# 1. Make this script executable: chmod +x start-dotnet-on-boot-linux.sh
# 2. Option A - Systemd (recommended):
#    sudo cp start-dotnet-on-boot-linux.service /etc/systemd/system/
#    sudo systemctl daemon-reload
#    sudo systemctl enable start-dotnet-on-boot-linux.service
#    sudo systemctl start start-dotnet-on-boot-linux.service
# 3. Option B - Crontab:
#    crontab -e
#    Add: @reboot /path/to/start-dotnet-on-boot-linux.sh

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration
ENVIRONMENT="${KANAT_ENV:-prod}"  # Default to prod, can be overridden with KANAT_ENV env var
COMPOSER_PATH="$PROJECT_ROOT/composer.py"
MAX_WAIT_TIME=300  # Maximum wait time for docker in seconds
CHECK_INTERVAL=5   # Check interval in seconds

# Logging
LOG_DIR="$HOME/.kanat-backend/logs"
LOG_FILE="$LOG_DIR/startup-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Log relevant configuration/environment information for debugging
log_config_snapshot() {
    log "----- Configuration snapshot start -----"
    log "KANAT_ENV (input): ${KANAT_ENV:-<not set>}"
    log "Resolved ENVIRONMENT: $ENVIRONMENT"
    log "PROJECT_ROOT: $PROJECT_ROOT"

    # Log docker-compose file used for this environment (if present)
    local compose_file="$PROJECT_ROOT/docker-compose.${ENVIRONMENT}.yml"
    if [ -f "$compose_file" ]; then
        log "docker-compose file for environment '$ENVIRONMENT': $compose_file"
        log "docker-compose.${ENVIRONMENT}.yml contents:"
        while IFS= read -r line; do
            log "  $line"
        done < "$compose_file"
    else
        log "docker-compose file not found for environment '$ENVIRONMENT': $compose_file"
    fi

    # Log PacketProcessingService appsettings.Production.json if available
    local appsettings_path="$PROJECT_ROOT/PacketProcessingService/appsettings.Production.json"
    if [ -f "$appsettings_path" ]; then
        log "PacketProcessingService appsettings.Production.json found at: $appsettings_path"
        log "appsettings.Production.json contents:"
        while IFS= read -r line; do
            log "  $line"
        done < "$appsettings_path"
    else
        log "PacketProcessingService appsettings.Production.json not found at: $appsettings_path"
    fi

    log "----- Configuration snapshot end -----"
}

# Check if docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        log "ERROR: Docker is not installed or not in PATH"
        return 1
    fi
    if ! docker info &> /dev/null; then
        log "ERROR: Docker daemon is not running"
        return 1
    fi
    return 0
}

# Check if docker compose stack is running
check_compose_running() {
    local env=$1
    local project_name="kanatbackend-$env"
    local compose_file="$PROJECT_ROOT/docker-compose.${env}.yml"
    
    if [ ! -f "$compose_file" ]; then
        return 1
    fi
    
    # Check if any containers from the project are running
    local containers=$(docker compose -p "$project_name" -f "$compose_file" ps -q 2>/dev/null)
    if [ -z "$containers" ]; then
        return 1
    fi
    
    # Check if at least one container is actually running
    for cid in $containers; do
        local status=$(docker inspect --format '{{.State.Status}}' "$cid" 2>/dev/null)
        if [ "$status" = "running" ]; then
            log "Found running container $cid in $project_name"
            return 0
        fi
    done
    
    return 1
}

# Wait for docker compose stack to be ready
wait_for_compose() {
    local env=$1
    local elapsed=0
    
    log "Waiting for docker compose stack kanatbackend-$env to be running..."
    while [ $elapsed -lt $MAX_WAIT_TIME ]; do
        if check_compose_running "$env"; then
            log "Docker compose stack kanatbackend-$env is running"
            # Give containers a moment to fully initialize
            sleep 3
            return 0
        fi
        sleep $CHECK_INTERVAL
        elapsed=$((elapsed + CHECK_INTERVAL))
        log "Still waiting... (${elapsed}s/${MAX_WAIT_TIME}s)"
    done
    
    log "ERROR: Timeout waiting for docker compose stack kanatbackend-$env"
    return 1
}

# Check if dotnet process is already running
is_dotnet_running() {
    local dll_path="$PROJECT_ROOT/artifacts/releases/$ENVIRONMENT/PacketProcessingService.dll"
    if [ ! -f "$dll_path" ]; then
        return 1
    fi
    
    # Check if process is running
    if pgrep -f "PacketProcessingService.dll.*--environment" > /dev/null; then
        log "PacketProcessingService is already running"
        return 0
    fi
    return 1
}

# Build and start the dotnet program using composer (headless, for systemd/cron)
start_dotnet_headless() {
    local env=$1
    
    if is_dotnet_running; then
        log "PacketProcessingService is already running, skipping startup"
        return 0
    fi
    
    log "Starting PacketProcessingService for environment: $env"
    
    # Check if composer.py exists
    if [ ! -f "$COMPOSER_PATH" ]; then
        log "ERROR: composer.py not found at $COMPOSER_PATH"
        return 1
    fi
    
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        log "ERROR: Python 3 is not installed or not in PATH"
        return 1
    fi
    
    cd "$PROJECT_ROOT" || return 1
    
    # Step 1: Build first
    log "Running build: python3 $COMPOSER_PATH build"
    if ! python3 "$COMPOSER_PATH" build >> "$LOG_FILE" 2>&1; then
        log "ERROR: Build failed"
        return 1
    fi
    log "Build completed successfully"
    
    # Step 2: Start containers and dotnet
    log "Running (headless): python3 $COMPOSER_PATH up $env --mediamtx"
    if python3 "$COMPOSER_PATH" up "$env" --mediamtx >> "$LOG_FILE" 2>&1; then
        log "Successfully started PacketProcessingService"
        return 0
    else
        log "ERROR: Failed to start PacketProcessingService"
        return 1
    fi
}

# Build and start the dotnet program in a new terminal window (interactive use)
start_dotnet_in_terminal() {
    local env=$1

    # Only try if we appear to have a GUI session and gnome-terminal
    if [ -z "${DISPLAY:-}" ]; then
        return 1
    fi
    if ! command -v gnome-terminal &> /dev/null; then
        return 1
    fi

    if is_dotnet_running; then
        log "PacketProcessingService is already running, skipping startup"
        return 0
    fi

    if [ ! -f "$COMPOSER_PATH" ]; then
        log "ERROR: composer.py not found at $COMPOSER_PATH"
        return 1
    fi
    if ! command -v python3 &> /dev/null; then
        log "ERROR: Python 3 is not installed or not in PATH"
        return 1
    fi

    log "Launching PacketProcessingService in a new terminal (environment: $env)"
    gnome-terminal -- bash -lc "
cd '$PROJECT_ROOT' || exit 1
echo \"Step 1: Building...\"
python3 '$COMPOSER_PATH' build
echo
echo \"Step 2: Starting environment ($env) with MediaMtx...\"
python3 '$COMPOSER_PATH' up '$env' --mediamtx
echo
echo 'PacketProcessingService finished. Press Enter to close this window...'
read
" >/dev/null 2>&1 &

    return 0
}

# Main execution
main() {
    log "========================================="
    log "PacketProcessingService Startup Script"
    log "Environment: $ENVIRONMENT"
    log "Project Root: $PROJECT_ROOT"
    log "========================================="
    
    # Check docker
    if ! check_docker; then
        log "Exiting due to docker issues"
        exit 1
    fi
    
    # Determine which environment to use (default to prod, can be overridden by KANAT_ENV)
    local running_env="${ENVIRONMENT:-prod}"
    
    # If KANAT_ENV is not set, prefer prod if available, otherwise dev
    if [ -z "${KANAT_ENV:-}" ]; then
        if check_compose_running "prod"; then
            running_env="prod"
        elif check_compose_running "dev"; then
            running_env="dev"
        else
            # Default to prod if nothing is running (composer.py up will start it)
            running_env="prod"
        fi
    fi
    
    ENVIRONMENT="$running_env"
    log "Using environment: $running_env"
    
    # Log configuration snapshot so it appears in systemd/journalctl logs
    log_config_snapshot
    
    # If we're in a user GUI session (not under systemd), open a new terminal for live output
    if [ -z "${SYSTEMD_INVOCATION_ID:-}" ] && start_dotnet_in_terminal "$running_env"; then
        log "Started PacketProcessingService in a new terminal window"
        log "Startup completed successfully"
        exit 0
    fi

    # Fallback/headless mode (for systemd/cron)
    if start_dotnet_headless "$running_env"; then
        log "Startup completed successfully"
        exit 0
    else
        log "Startup failed"
        exit 1
    fi
}

# Run main function
main "$@"
