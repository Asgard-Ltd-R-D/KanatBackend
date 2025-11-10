# Deployment Guide

This guide explains how to build and deploy the KanatBackend application using the build artifacts script and composer tool.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Building Artifacts](#building-artifacts)
- [Creating Installer](#creating-installer)
- [Using the Installer](#using-the-installer)
- [Composer Tool](#composer-tool)
- [Deployment Workflow](#deployment-workflow)
- [Composer GUI](#composer-gui)

> This deployment guide lives alongside the CLI under `Composer_cli/DEPLOY_README.md` so it ships with the packaged installer.

## Overview

The deployment process consists of two main components:

1. **build_artifacts.sh** - Builds release packages and creates a self-extracting installer
2. **composer** - Tool for managing the application lifecycle (build, run, stop, etc.)

## Prerequisites

Before building artifacts, ensure you have:

- **Docker** - Version 20.10 or later
- **.NET SDK** - Version 8.0 or later
- **Python 3** - Version 3.8 or later (for building artifacts)
- **PyInstaller** - Will be installed automatically by the build script
- **Bash** - For running shell scripts

## Building Artifacts

### Using build_artifacts.sh

The `build_artifacts.sh` script builds a release for a specific platform and creates a self-extracting installer.

#### Usage

```bash
./build_artifacts.sh <OS_PLATFORM>
./build_artifacts.sh clean
```

#### Available Platforms

- `win-x64` - Windows 64-bit
- `linux-x64` - Linux 64-bit
- `linux-musl-x64` - Linux 64-bit (musl)
- `osx-arm64` - macOS ARM64 (Apple Silicon)

#### Examples

```bash
# Build for macOS (Apple Silicon)
./build_artifacts.sh osx-arm64

# Build for Linux
./build_artifacts.sh linux-x64

# Build for Windows
./build_artifacts.sh win-x64

# Clean all build artifacts
./build_artifacts.sh clean
```

#### Clean Command

The `clean` command removes all build artifacts:

```bash
./build_artifacts.sh clean
```

This removes:
- `composer` executable
- `installer.run` file
- `artifacts/` directory
- `.venv/` directory (Python virtual environment)
- `.pyi_spec/` directory (PyInstaller spec files)
- `.pyi_build/` directory (PyInstaller build files)

Use this to start fresh or free up disk space.

#### What It Does

1. **Builds Release Packages**: Runs `composer.py release <platform>`. If source code is available, PacketProcessing is recompiled; otherwise existing package tarballs are reused. The output is:
   - `artifacts/releases/{dev,prod}` (DLLs rebuilt when source is present)
   - `artifacts/packages/dev` containing only `packetprocessing_dev_<platform>.tar`
   - `artifacts/packages/prod` containing only `packetprocessing_prod_<platform>.tar`
   - Root-level shared Docker image tarballs (`kanatbackend-questdb.tar`, `postgres_15-alpine.tar`, `datalust_seq_latest.tar`)
   - Root-level compose files (`docker-compose.dev.yml`, `docker-compose.prod.yml`) and `QuestDB/`

2. **Creates Composer Executable**: 
   - Sets up Python virtual environment
   - Installs PyInstaller
   - Builds standalone `composer` executable (no Python required)

3. **Creates Installer**: 
   - Packages everything into `installer.run`
   - Self-extracting archive containing:
     - README.md
     - DEPLOY_README.md
     - composer executable
     - artifacts/ directory with all release assets (structure described below)

#### Output

After running `build_artifacts.sh`, you'll have:

- `installer.run` - Self-extracting installer file
- `artifacts/` - Directory containing:
  - `releases/` - DLL builds for dev and prod
  - `packages/` - Release packages with timestamps

## Creating Installer

The `installer.run` file is a self-extracting shell script that contains all necessary files for deployment.

### Contents of installer.run

When extracted, the installer creates a `BackendApplication` directory with:

```
BackendApplication/
├── README.md
├── DEPLOY_README.md
├── composer                    # Executable tool
├── docker-compose.dev.yml
├── docker-compose.prod.yml
├── QuestDB/
│   └── Dockerfile
└── artifacts/
    ├── releases/               # Initially empty (composer will rebuild from packages)
    └── packages/
        ├── dev/                # Dev release package
        │   └── packetprocessing_dev_<platform>.tar
        ├── prod/               # Prod release package
        │   └── packetprocessing_prod_<platform>.tar
        ├── kanatbackend-questdb.tar
        ├── postgres_15-alpine.tar
        └── datalust_seq_latest.tar
```

## Using the Installer

### Installation

1. **Transfer the installer** to your target machine:
   ```bash
   scp installer.run user@target-machine:/path/to/install/
   ```

2. **Make it executable**:
   ```bash
   chmod +x installer.run
   ```

3. **Run the installer**:
   ```bash
   # Extract to ./BackendApplication/ (current directory)
   ./installer.run

   # Or extract to a specific base directory
   # Files will be in /opt/BackendApplication/
   ./installer.run /opt
   ```

   **Note**: The installer automatically creates a `BackendApplication` directory. If the directory already exists, the installer will exit with an error to prevent overwriting.

4. **Navigate to the installation directory**:
   ```bash
   cd BackendApplication
   # or
   cd /opt/BackendApplication  # if you specified a base directory
   ```

5. **Use composer** to manage the application:
   ```bash
   ./composer --help
   ```

## Composer Tool

The `composer` tool is a standalone executable (no Python required) for managing the KanatBackend application.

### Commands

#### Build Environments

Build both dev and prod environments (rehydrates from packages when running inside the installer):

```bash
./composer build
```

This ensures:
- DLL builds are present in `artifacts/releases/dev/` and `artifacts/releases/prod/` (rebuilt from source when available, otherwise extracted from package tarballs)
- Docker images are loaded from the cache tarballs or rebuilt/pulled and re-cached

#### Run Application

Start the application in production mode (default):

```bash
./composer up
```

Start in development mode:

```bash
./composer up dev
```

Start in detached mode (background):

```bash
./composer up dev -d
```

Detached mode launches the containers and opens a new Terminal window that runs `PacketProcessing.dll`, leaving the originating shell free.

**Note**: 
- Starting one environment automatically stops the other if it's running.
- Composer automatically uses the bundled compose files in the installation root, ensuring you're using the same configuration that was packaged for deployment.

#### Stop Application

Stop the running environment:

```bash
# Stop production
./composer stop

# Stop development
./composer stop dev
```

#### Kill Environment

Kill and clean up an environment (removes containers and DLL):

```bash
# Kill production
./composer kill

# Kill development
./composer kill dev
```

#### Create Release Package

Create a release package for a specific platform:

```bash
./composer release <platform>
```

Platforms: `win-x64`, `linux-x64`, `linux-musl-x64`, `osx-arm64`

This creates release assets under `artifacts/`:
- `artifacts/packages/dev_<timestamp>/` and `prod_<timestamp>/` containing only the environment-specific `packetprocessing_<env>_<platform>.tar`
- Shared Docker image tarballs (`kanatbackend-questdb.tar`, `postgres_15-alpine.tar`, `datalust_seq_latest.tar`) stored once in `artifacts/packages/`
- The root-level compose files (`docker-compose.dev.yml`, `docker-compose.prod.yml`) and `QuestDB/` directory are reused when building the installer.

#### Check Status

View current system status:

```bash
./composer status
```

Shows:
- Running Docker containers
- PacketProcessing build status and whether the process is currently running (with environment/port)
- Available release packages

#### Help

Display help information:

```bash
./composer --help
./composer -h
```

## Composer GUI

- The packaged `composer` executable launches the dashboard GUI automatically when started without arguments (for example, by double-clicking it in Finder/Explorer). This is equivalent to running `./composer --gui`.
- On macOS, the launcher minimizes the originating Terminal window before showing the GUI for a cleaner experience. Command-line usage remains unchanged—supplying arguments bypasses the auto-GUI behavior.
- The GUI offers environment management (Up/Stop/Restart/Kill), Quick Build, log streaming, and live component status for PacketProcessing, Postgres, QuestDB, and Seq.

## Deployment Workflow

### Initial Deployment

1. **Build artifacts on build machine**:
   ```bash
   ./build_artifacts.sh linux-x64
   ```

2. **Transfer installer to target machine**:
   ```bash
   scp installer.run user@target:/opt/
   ```

3. **On target machine, extract installer**:
   ```bash
   cd /opt
   chmod +x installer.run
   ./installer.run
   # This creates /opt/BackendApplication/
   ```

4. **Navigate to installation directory**:
   ```bash
   cd BackendApplication
   ```

5. **Load Docker images** (if needed):
   ```bash
   docker load -i artifacts/packages/kanatbackend-questdb.tar
   docker load -i artifacts/packages/postgres_15-alpine.tar
   docker load -i artifacts/packages/datalust_seq_latest.tar
   ```

6. **Start the application**:
   ```bash
   ./composer up prod
   ```
   
   Composer will automatically use the bundled compose files in the installation root.

### Updating Deployment

1. **Stop current environment**:
   ```bash
   ./composer stop prod
   ```

2. **Extract new installer** (or update files manually):
   ```bash
   # If updating in place, remove old BackendApplication directory first
   rm -rf BackendApplication
   ./installer.run
   cd BackendApplication
   ```

3. **Load new Docker images** (if updated):
   ```bash
   docker load -i artifacts/packages/kanatbackend-questdb.tar
   docker load -i artifacts/packages/postgres_15-alpine.tar
   docker load -i artifacts/packages/datalust_seq_latest.tar
   ```

4. **Start updated environment**:
   ```bash
   ./composer up prod
   ```
   
   Composer will automatically use the refreshed compose files in the installation root.

### Offline Deployment

The release packages are designed for offline deployment:

1. **Build on machine with internet**:
   ```bash
   ./build_artifacts.sh linux-x64
   ```

2. **Transfer installer to offline machine**:
   ```bash
   # Copy installer.run to USB drive or internal network
   ```

3. **On offline machine, extract and run**:
   ```bash
   ./installer.run
   cd BackendApplication

   # Load Docker images from tarballs
   docker load -i artifacts/packages/kanatbackend-questdb.tar
   docker load -i artifacts/packages/postgres_15-alpine.tar
   docker load -i artifacts/packages/datalust_seq_latest.tar

   # Start application (composer uses bundled compose files automatically)
   ./composer up prod
   ```

## Directory Structure

After installation, your directory structure will be:

```
<base_directory>/
└── BackendApplication/        # Created by installer
    ├── README.md
    ├── DEPLOY_README.md
    ├── composer                # Executable
    ├── docker-compose.dev.yml
    ├── docker-compose.prod.yml
    ├── QuestDB/
    │   └── Dockerfile
    └── artifacts/
        ├── releases/
        │   ├── dev/           # Populated after running composer build/up
        │   └── prod/
        └── packages/
            ├── dev/           # packetprocessing_dev_<platform>.tar
            ├── prod/          # packetprocessing_prod_<platform>.tar
            ├── kanatbackend-questdb.tar
            ├── postgres_15-alpine.tar
            └── datalust_seq_latest.tar
```

**Important**: Composer automatically uses the bundled compose files located next to the `composer` executable when running `up` or `build`, falling back to repository defaults only if those files are missing.

## Troubleshooting

### Port Conflicts

If you get port conflicts when starting:

```bash
# Check what's using the ports
docker ps
netstat -tulpn | grep -E '8812|5432|5341'

# Stop conflicting containers
./composer stop
```

### Missing Docker Images

If Docker images are missing:

```bash
# Load images from release package
docker load -i artifacts/packages/kanatbackend-questdb.tar
docker load -i artifacts/packages/postgres_15-alpine.tar
docker load -i artifacts/packages/datalust_seq_latest.tar
```

### Clean Build Artifacts

To remove all build artifacts and start fresh:

```bash
# On build machine
./build_artifacts.sh clean
```

This removes:
- Composer executable
- Installer.run file
- Artifacts directory
- Python virtual environment
- PyInstaller build files

### Build Failures

If build fails:

1. Check prerequisites are installed:
   ```bash
   docker --version
   dotnet --version
   python3 --version
   ```

2. Ensure you have internet connection (for initial build)

3. Check disk space:
   ```bash
   df -h
   ```

### Permission Issues

If you get permission errors:

```bash
# Make scripts executable
chmod +x build_artifacts.sh
chmod +x installer.run
chmod +x composer

# Ensure Docker is accessible
sudo usermod -aG docker $USER
# (logout and login again)
```

## Additional Resources

- See main `README.md` for application documentation
- Check `composer --help` for latest command options
- Review Docker Compose files for service configuration

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review application logs in `PacketProcessing/logs/`
3. Check Docker container logs: `docker compose logs`

