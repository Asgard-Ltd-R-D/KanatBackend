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

# Start the dotnet program using composer
start_dotnet() {
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
    
    # Start the service in detached mode
    cd "$PROJECT_ROOT" || return 1
    log "Running: python3 $COMPOSER_PATH up $env -d"
    
    if python3 "$COMPOSER_PATH" up "$env" -d >> "$LOG_FILE" 2>&1; then
        log "Successfully started PacketProcessingService"
        return 0
    else
        log "ERROR: Failed to start PacketProcessingService"
        return 1
    fi
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
    
    # Determine which environment is running (check prod first, then dev)
    local running_env=""
    if check_compose_running "prod"; then
        running_env="prod"
        ENVIRONMENT="prod"
    elif check_compose_running "dev"; then
        running_env="dev"
        ENVIRONMENT="dev"
    else
        log "No docker compose stack found running. Waiting for stack to start..."
        # Try waiting for prod first, then dev
        if wait_for_compose "prod"; then
            running_env="prod"
            ENVIRONMENT="prod"
        elif wait_for_compose "dev"; then
            running_env="dev"
            ENVIRONMENT="dev"
        else
            log "ERROR: No docker compose stack is running after waiting"
            exit 1
        fi
    fi
    
    log "Detected running environment: $running_env"
    
    # Start the dotnet program
    if start_dotnet "$running_env"; then
        log "Startup completed successfully"
        exit 0
    else
        log "Startup failed"
        exit 1
    fi
}

# Run main function
main "$@"

