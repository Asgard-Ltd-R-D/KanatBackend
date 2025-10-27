#!/usr/bin/env python3
"""
composer.py - Build and run PacketProcessing with Docker Compose
Usage:
    python composer.py up [dev|prod] [-d] [--build] [-r [index]]
    python composer.py stop [dev|prod]
    python composer.py kill [dev|prod]
    python composer.py --build [dev|prod] [-r [index]]
    python composer.py up --build [dev|prod] [-d] [-r [index]]
    python composer.py release [dev|prod] [win-x64|linux-x64|linux-musl-x64|osx-arm64]
    python composer.py status
    python composer.py --help
    
Examples:
    python composer.py up                    # Run prod environment (uses newest deploy package if available)
    python composer.py up dev                # Run dev environment (uses newest deploy package if available)
    python composer.py stop dev              # Stop dev environment
    python composer.py kill dev              # Kill dev environment (delete DLL and containers)
    python composer.py --build               # Build prod environment (uses newest deploy package if available)
    python composer.py up dev -d             # Run dev in detached mode
    python composer.py --build -r            # List available deploy versions
    python composer.py --build -r 2          # Build using deploy version 2
    python composer.py up --build -r 2       # Build and run using deploy version 2
    python composer.py release dev linux-x64 # Create release package for dev environment on linux-x64
    python composer.py release prod osx-arm64 # Create release package for prod environment on osx-arm64
    python composer.py status                # Show current system status
"""

import sys
import os
import subprocess
import shutil
import platform
import time
import threading
from pathlib import Path
from datetime import datetime

# Configuration
PROJECT_ROOT = Path(__file__).parent
PACKET_PROCESSING_DIR = PROJECT_ROOT / "PacketProcessing"
RELEASE_DIR = PROJECT_ROOT / "release"
DEPLOY_DIR = PROJECT_ROOT / "deploy"
DOCKER_COMPOSE_DEV_FILE = PROJECT_ROOT / "docker-compose.dev.yml"
DOCKER_COMPOSE_PROD_FILE = PROJECT_ROOT / "docker-compose.prod.yml"

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(message):
    """Print colored header message"""
    print(f"{Colors.HEADER}{Colors.BOLD}{message}{Colors.ENDC}")

def print_info(message):
    """Print colored info message"""
    print(f"{Colors.OKBLUE}{message}{Colors.ENDC}")

def print_success(message):
    """Print colored success message"""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

def print_error(message):
    """Print colored error message"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")

def print_warning(message):
    """Print colored warning message"""
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")

def check_docker():
    """Check if Docker is installed and available"""
    try:
        result = subprocess.run(['docker', '--version'], 
                               capture_output=True, text=True, check=True)
        print_success(f"Docker found: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("Docker is not installed or not available in PATH")
        print_info("Please install Docker from https://www.docker.com/")
        return False

def check_dotnet():
    """Check if .NET SDK is installed"""
    try:
        result = subprocess.run(['dotnet', '--version'], 
                               capture_output=True, text=True, check=True)
        print_success(f".NET SDK found: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error(".NET SDK is not installed or not available in PATH")
        print_info("Please install .NET SDK from https://dotnet.microsoft.com/download")
        return False

def validate_release_path(path):
    """Validate that a path is within the release directory"""
    try:
        path = Path(path).resolve()
        release_dir = RELEASE_DIR.resolve()
        return path.is_relative_to(release_dir)
    except (ValueError, OSError):
        return False

def ensure_release_directory_cleanup():
    """Ensure no dev/prod directories exist outside the release directory"""
    print_info("Checking for stray dev/prod directories...")
    
    # Check project root for dev/prod directories (but exclude known directories)
    project_root = PROJECT_ROOT
    stray_dirs = []
    
    # Directories to exclude from cleanup (these are legitimate project directories)
    excluded_dirs = {
        RELEASE_DIR / 'dev',
        RELEASE_DIR / 'prod',
        DEPLOY_DIR,  # Don't touch the deploy directory
        PACKET_PROCESSING_DIR,  # Don't touch the PacketProcessing directory
    }
    
    for item in project_root.iterdir():
        if item.is_dir() and item.name in ['dev', 'prod']:
            # Check if it's not in our excluded directories
            if item not in excluded_dirs:
                stray_dirs.append(item)
    
    if stray_dirs:
        print_warning(f"Found stray directories outside release folder: {[str(d) for d in stray_dirs]}")
        print_info("Cleaning up stray directories...")
        
        for stray_dir in stray_dirs:
            try:
                shutil.rmtree(stray_dir)
                print_success(f"Removed stray directory: {stray_dir}")
            except Exception as e:
                print_error(f"Failed to remove stray directory {stray_dir}: {e}")
    else:
        print_success("No stray dev/prod directories found")

def get_os_info():
    """Get current OS information"""
    os_name = platform.system()
    os_platform = platform.machine()
    return os_name, os_platform

def build_dll(environment='prod', show_progress=True):
    """Build the .NET DLL for the specified environment"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Building PacketProcessing for {environment.upper()}... [{timestamp}]")
    
    # Create release directory
    release_env_dir = RELEASE_DIR / environment
    if release_env_dir.exists():
        print_info(f"Removing previous build in {release_env_dir}")
        shutil.rmtree(release_env_dir)
    
    release_env_dir.mkdir(parents=True, exist_ok=True)
    
    # Build the project
    os_name, os_platform = get_os_info()
    print_info(f"Building for {os_name} ({os_platform}) on {environment.upper()} environment")
    
    try:
        # Determine runtime identifier
        if os_name == 'Linux':
            rid = 'linux-x64'
        elif os_name == 'Darwin':
            if os_platform == 'arm64':
                rid = 'osx-arm64'
            else:
                rid = 'osx-x64'
        elif os_name == 'Windows':
            rid = 'win-x64'
        else:
            print_warning(f"Unknown OS: {os_name}, using portable runtime")
            rid = None
        
        # Build command
        build_cmd = ['dotnet', 'publish', 
                    '-c', 'Release',
                    '-o', str(release_env_dir)]
        
        if rid:
            build_cmd.extend(['-r', rid, '--self-contained', 'false'])
        
        print_info(f"Running: {' '.join(build_cmd)}")
        
        if show_progress:
            # Run with live output
            process = subprocess.Popen(
                build_cmd,
                cwd=PACKET_PROCESSING_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Stream output
            for line in process.stdout:
                print(line, end='')
            
            process.wait()
            result_code = process.returncode
        else:
            result = subprocess.run(build_cmd, 
                                  cwd=PACKET_PROCESSING_DIR,
                                  check=True,
                                  capture_output=True,
                                  text=True)
            result_code = result.returncode
        
        if result_code == 0:
            print_success(f"Build completed successfully in {release_env_dir}")
            
            # Copy additional files and directories
            print_info("Copying additional files and directories...")
            
            # Copy appsettings files
            base_settings = PACKET_PROCESSING_DIR / "appsettings.json"
            if base_settings.exists():
                shutil.copy2(base_settings, release_env_dir / "appsettings.json")
                print_success("Copied appsettings.json")
            
            # Copy environment-specific appsettings
            normalized_environment = ("Development" if environment == 'dev' else "Production")
            env_settings_name = f"appsettings.{normalized_environment}.json"
            env_settings = PACKET_PROCESSING_DIR / env_settings_name
            
            if env_settings.exists():
                shutil.copy2(env_settings, release_env_dir / env_settings_name)
                print_success(f"Copied {env_settings_name}")
            else:
                print_warning(f"{env_settings_name} not found, skipping")
            
            # Copy swagger.json
            swagger_json = PACKET_PROCESSING_DIR / "swagger.json"
            if swagger_json.exists():
                shutil.copy2(swagger_json, release_env_dir / "swagger.json")
                print_success("Copied swagger.json")
            
            # Copy Properties directory
            properties_dir = PACKET_PROCESSING_DIR / "Properties"
            if properties_dir.exists():
                dest_properties = release_env_dir / "Properties"
                if dest_properties.exists():
                    shutil.rmtree(dest_properties)
                shutil.copytree(properties_dir, dest_properties)
                print_success("Copied Properties directory")
            
            # Copy wwwroot directory
            wwwroot_dir = PACKET_PROCESSING_DIR / "wwwroot"
            if wwwroot_dir.exists():
                dest_wwwroot = release_env_dir / "wwwroot"
                if dest_wwwroot.exists():
                    shutil.rmtree(dest_wwwroot)
                shutil.copytree(wwwroot_dir, dest_wwwroot)
                print_success("Copied wwwroot directory")
            
            return True
        else:
            print_error(f"Build failed with return code {result_code}")
            return False
        
    except subprocess.CalledProcessError as e:
        print_error(f"Build failed with return code {e.returncode}")
        print_error(e.stderr)
        return False

def run_docker_compose(environment='prod', detached=False, show_logs=True, project_name=None):
    """Run Docker Compose for the specified environment"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
    
    if not compose_file.exists():
        print_error(f"Docker Compose file not found: {compose_file}")
        return False
    
    if project_name is None:
        project_name = f"kanatbackend-{environment}"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Starting Docker Compose for {environment.upper()}... [{timestamp}]")
    
    try:
        if detached:
            # Start in detached mode first
            cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'up', '-d']
            print_info("Starting services in detached mode...")
            
            subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
            
            if show_logs:
                # Show logs after starting
                print_header("Docker Compose Logs:")
                log_cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'logs', '-f']
                try:
                    subprocess.run(log_cmd, cwd=PROJECT_ROOT)
                except KeyboardInterrupt:
                    print_warning("\nStopping log view (services still running)")
        else:
            # Run normally with output
            cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'up']
            print_info(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
        
        return True
        
    except subprocess.CalledProcessError as e:
        print_error(f"Docker Compose failed with return code {e.returncode}")
        return False

def run_dll(environment='prod', detached=False):
    """Run the .NET DLL for the specified environment"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    dll_path = RELEASE_DIR / environment / "PacketProcessing.dll"
    
    if not dll_path.exists():
        print_error(f"DLL not found: {dll_path}")
        print_info(f"Building for {environment.upper()}...")
        if not build_dll(environment):
            return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Running PacketProcessing for {environment.upper()}... [{timestamp}]")
    print_info(f"Executing: dotnet {dll_path}")
    
    try:
        cmd = ['dotnet', str(dll_path)]
        env = os.environ.copy()
        # Set the correct ASP.NET Core environment
        env['ASPNETCORE_ENVIRONMENT'] = 'Development' if environment == 'dev' else 'Production'
        print_info(f"Environment: {env['ASPNETCORE_ENVIRONMENT']}")
        
        if detached:
            print_info("Starting application in background...")
            process = subprocess.Popen(
                cmd,
                env=env,
                cwd=RELEASE_DIR / environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print_success(f"Application started with PID: {process.pid} in detached mode")
            print_info("Application is running in background (no logs will be shown)")
        else:
            print_info("Running application (Press Ctrl+C to stop)")
            process = subprocess.Popen(
                cmd,
                env=env,
                cwd=RELEASE_DIR / environment
            )
            
            # Stream output
            try:
                process.wait()
            except KeyboardInterrupt:
                print_warning("\nStopping application...")
                process.terminate()
                process.wait()
                print_success("Application stopped")
        
        return True
        
    except subprocess.CalledProcessError as e:
        print_error(f"Application failed with return code {e.returncode}")
        return False
    except Exception as e:
        print_error(f"Failed to start application: {str(e)}")
        return False

def stop_environment(environment):
    """Stop the environment (Docker Compose and DLL process)"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    project_name = f"kanatbackend-{environment}"
    compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Stopping environment: {environment.upper()}... [{timestamp}]")
    
    # Stop Docker Compose containers
    print_info("Stopping Docker Compose containers...")
    try:
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'stop']
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
        print_success("Docker Compose containers stopped")
    except subprocess.CalledProcessError:
        print_warning("No Docker Compose containers to stop")
    
    # Kill any running DLL processes
    print_info("Killing running DLL processes...")
    try:
        result = subprocess.run(['pgrep', '-f', 'PacketProcessing.dll'], 
                               capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    subprocess.run(['kill', pid], check=True)
                    print_success(f"Killed process {pid}")
                except subprocess.CalledProcessError:
                    pass
        else:
            print_info("No running DLL processes found")
    except FileNotFoundError:
        print_warning("pgrep not found, skipping process cleanup")
    
    print_success(f"Environment {environment.upper()} stopped")
    return True

def kill_environment(environment):
    """Kill the environment (delete DLL and remove Docker Compose containers)"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    project_name = f"kanatbackend-{environment}"
    compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Killing environment: {environment.upper()}... [{timestamp}]")
    
    # First stop the environment
    stop_environment(environment)
    
    # Remove Docker Compose containers
    print_info("Removing Docker Compose containers...")
    try:
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'rm', '-f']
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
        print_success("Docker Compose containers removed")
    except subprocess.CalledProcessError:
        print_warning("No Docker Compose containers to remove")
    
    # Delete DLL directory
    release_env_dir = RELEASE_DIR / environment
    if release_env_dir.exists():
        print_info(f"Deleting DLL directory: {release_env_dir}")
        try:
            shutil.rmtree(release_env_dir)
            print_success("DLL directory deleted")
        except Exception as e:
            print_error(f"Failed to delete DLL directory: {e}")
    else:
        print_info("No DLL directory to delete")
    
    print_success(f"Environment {environment.upper()} killed")
    return True

def create_release_package(environment, platform):
    """Create a release package with Docker images, DLL, and configuration files"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    if platform not in ['win-x64', 'linux-x64', 'linux-musl-x64', 'osx-arm64']:
        print_error(f"Invalid platform: {platform}. Must be one of: win-x64, linux-x64, linux-musl-x64, osx-arm64")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print_header(f"Creating release package for {environment.upper()} on {platform}... [{timestamp}]")
    
    # Create deploy directory structure with environment prefix
    deploy_timestamp_dir = DEPLOY_DIR / f"{environment}_{timestamp}"
    deploy_timestamp_dir.mkdir(parents=True, exist_ok=True)
    
    print_success(f"Created deploy directory: {deploy_timestamp_dir}")
    
    # Build DLL for the specified platform
    print_info(f"Building DLL for {platform}...")
    if not build_dll_for_platform(environment, platform):
        return False
    
    # Get Docker images from compose file
    compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
    project_name = f"kanatbackend-{environment}"
    
    # Start Docker Compose to build images
    print_info("Starting Docker Compose to ensure images are built...")
    try:
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'up', '-d', '--build']
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
        print_success("Docker Compose images built successfully")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to build Docker Compose images: {e}")
        return False
    
    # Export Docker images
    print_info("Exporting Docker images...")
    docker_images = []
    
    # Get list of images used by the compose file
    try:
        # Get images from compose
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'images', '-q']
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
        image_ids = [line.strip() for line in result.stdout.split('\n') if line.strip()]
        
        # Get image names and tags
        for image_id in image_ids:
            cmd = ['docker', 'inspect', '--format={{.RepoTags}}', image_id]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            tags = result.stdout.strip().strip('[]').replace('"', '').split(',')
            for tag in tags:
                if tag.strip():
                    docker_images.append(tag.strip())
        
        print_info(f"Found Docker images: {', '.join(docker_images)}")
        
        # Export each image
        for image_name in docker_images:
            # Clean image name for filename
            safe_name = image_name.replace('/', '_').replace(':', '_')
            tar_filename = f"{safe_name}.tar"
            tar_path = deploy_timestamp_dir / tar_filename
            
            print_info(f"Exporting {image_name} to {tar_filename}...")
            try:
                cmd = ['docker', 'save', '-o', str(tar_path), image_name]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                print_success(f"Exported {image_name} to {tar_filename}")
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to export {image_name}: {e}")
                return False
    
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to get Docker images: {e}")
        return False
    
    # Create DLL tar
    print_info("Creating DLL tar...")
    dll_dir = RELEASE_DIR / environment
    if not dll_dir.exists():
        print_error(f"DLL directory not found: {dll_dir}")
        return False
    
    dll_tar_path = deploy_timestamp_dir / f"packetprocessing_{environment}_{platform}.tar"
    try:
        cmd = ['tar', '-czf', str(dll_tar_path), '-C', str(dll_dir.parent), environment]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print_success(f"Created DLL tar: {dll_tar_path.name}")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create DLL tar: {e}")
        return False
    
    # Create deployment files tar
    print_info("Creating deployment files tar...")
    deploy_files_tar_path = deploy_timestamp_dir / f"deployment_files_{environment}.tar"
    
    # Create temporary directory for deployment files
    temp_deploy_dir = deploy_timestamp_dir / "temp_deploy"
    temp_deploy_dir.mkdir(exist_ok=True)
    
    # Copy composer.py
    shutil.copy2(PROJECT_ROOT / "composer.py", temp_deploy_dir / "composer.py")
    
    # Copy docker-compose file
    compose_filename = f"docker-compose.{environment}.yml"
    shutil.copy2(compose_file, temp_deploy_dir / compose_filename)
    
    try:
        cmd = ['tar', '-czf', str(deploy_files_tar_path), '-C', str(temp_deploy_dir), '.']
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print_success(f"Created deployment files tar: {deploy_files_tar_path.name}")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create deployment files tar: {e}")
        return False
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_deploy_dir, ignore_errors=True)
    
    # Stop Docker Compose
    print_info("Stopping Docker Compose...")
    try:
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'down']
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
        print_success("Docker Compose stopped")
    except subprocess.CalledProcessError:
        print_warning("Failed to stop Docker Compose (may not be running)")
    
    print_success(f"Release package created successfully in {deploy_timestamp_dir}")
    print_info(f"Package contents:")
    for item in deploy_timestamp_dir.iterdir():
        size = item.stat().st_size if item.is_file() else "dir"
        print_info(f"  - {item.name} ({size} bytes)" if isinstance(size, int) else f"  - {item.name} ({size})")
    
    return True

def get_deploy_versions():
    """Get all deploy versions sorted by timestamp (newest first)"""
    if not DEPLOY_DIR.exists():
        return []
    
    versions = []
    for item in DEPLOY_DIR.iterdir():
        if item.is_dir():
            try:
                # Parse new format: environment_timestamp (e.g., dev_20251026_150739)
                if '_' in item.name:
                    parts = item.name.split('_', 1)
                    if len(parts) == 2 and parts[0] in ['dev', 'prod']:
                        environment = parts[0]
                        timestamp = datetime.strptime(parts[1], "%Y%m%d_%H%M%S")
                        versions.append((timestamp, item, environment))
                        continue
                
                # Parse old format: timestamp only (e.g., 20251026_150739) - for backward compatibility
                timestamp = datetime.strptime(item.name, "%Y%m%d_%H%M%S")
                versions.append((timestamp, item, None))  # None means unknown environment
            except ValueError:
                # Skip directories that don't match either format
                continue
    
    # Sort by timestamp (newest first)
    versions.sort(key=lambda x: x[0], reverse=True)
    return versions

def list_deploy_versions():
    """List all available deploy versions with indices"""
    versions = get_deploy_versions()
    
    if not versions:
        print_info("No deploy versions found")
        return []
    
    print_header("Available deploy versions:")
    for i, (timestamp, version_dir, environment) in enumerate(versions, 1):
        timestamp_str = version_dir.name
        try:
            if environment:
                # New format: environment_timestamp
                dt = datetime.strptime(timestamp_str.split('_', 1)[1], "%Y%m%d_%H%M%S")
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                env_info = f" [{environment.upper()}]"
            else:
                # Old format: timestamp only
                dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                env_info = " [UNKNOWN ENV]"
        except ValueError:
            formatted_time = timestamp_str
            env_info = ""
        
        # Count files in the directory
        file_count = len([f for f in version_dir.iterdir() if f.is_file()])
        print_info(f"  {i}. {formatted_time}{env_info} ({file_count} files)")
    
    return versions

def show_status():
    """Show current system status"""
    print_header("System Status")
    
    # Check Docker containers
    print_info("Docker Containers:")
    try:
        result = subprocess.run(['docker', 'ps', '-a', '--format', 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'], 
                              capture_output=True, text=True, check=True)
        if result.stdout.strip():
            print(result.stdout)
        else:
            print_info("  No containers found")
    except subprocess.CalledProcessError:
        print_error("  Failed to get Docker container status")
    
    # Check running PacketProcessing processes
    print_info("\nPacketProcessing Processes:")
    try:
        result = subprocess.run(['pgrep', '-f', 'PacketProcessing.dll'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    ps_result = subprocess.run(['ps', '-p', pid, '-o', 'pid,etime,command'], 
                                             capture_output=True, text=True, check=True)
                    print(ps_result.stdout.strip())
                except subprocess.CalledProcessError:
                    pass
        else:
            print_info("  No PacketProcessing processes running")
    except subprocess.CalledProcessError:
        print_info("  No PacketProcessing processes running")
    
    # Check release directories
    print_info("\nRelease Builds:")
    if RELEASE_DIR.exists():
        for env_dir in RELEASE_DIR.iterdir():
            if env_dir.is_dir():
                dll_path = env_dir / "PacketProcessing.dll"
                status = "✓ Built" if dll_path.exists() else "✗ Missing DLL"
                print_info(f"  {env_dir.name}: {status}")
    else:
        print_info("  No release directory found")
    
    # Check deploy packages
    print_info("\nDeploy Packages:")
    versions = get_deploy_versions()
    if versions:
        for timestamp, version_dir, environment in versions[:5]:  # Show only last 5
            timestamp_str = version_dir.name
            try:
                if environment:
                    # New format: environment_timestamp
                    dt = datetime.strptime(timestamp_str.split('_', 1)[1], "%Y%m%d_%H%M%S")
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    env_info = f" [{environment.upper()}]"
                else:
                    # Old format: timestamp only
                    dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    env_info = " [UNKNOWN ENV]"
            except ValueError:
                formatted_time = timestamp_str
                env_info = ""
            
            file_count = len([f for f in version_dir.iterdir() if f.is_file()])
            print_info(f"  {formatted_time}{env_info} ({file_count} files)")
    else:
        print_info("  No deploy packages found")
    
    # Check Docker Compose project status
    print_info("\nDocker Compose Projects:")
    try:
        # First, list all compose projects
        result = subprocess.run(['docker', 'compose', 'ls', '--format', 'json'], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.returncode == 0 and result.stdout.strip():
            import json
            projects = json.loads(result.stdout)
            if projects:
                for project in projects:
                    name = project.get('Name', 'Unknown')
                    status = project.get('Status', 'Unknown')
                    config_files = project.get('ConfigFiles', 'Unknown')
                    print_info(f"  {name.upper()}: {status}")
                    if 'dev' in name.lower():
                        print_info(f"    Config: {config_files}")
            else:
                print_info("  No Docker Compose projects found")
        else:
            print_info("  No Docker Compose projects found")
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        print_info("  Failed to get Docker Compose project status")

def get_deploy_environment(deploy_dir):
    """Extract environment information from deploy directory name"""
    dir_name = deploy_dir.name
    
    # Check new format: environment_timestamp (e.g., dev_20251026_150739)
    if '_' in dir_name:
        parts = dir_name.split('_', 1)
        if len(parts) == 2 and parts[0] in ['dev', 'prod']:
            return parts[0]
    
    # Check old format: timestamp only (e.g., 20251026_150739) - for backward compatibility
    try:
        datetime.strptime(dir_name, "%Y%m%d_%H%M%S")
        # This is an old format directory, try to detect environment from files
        return detect_environment_from_files(deploy_dir)
    except ValueError:
        return None

def detect_environment_from_files(deploy_dir):
    """Try to detect environment from files in deploy directory (for backward compatibility)"""
    # Look for DLL tar files that contain environment info
    dll_files = [f for f in deploy_dir.iterdir() if f.is_file() and f.name.startswith('packetprocessing_') and f.suffix == '.tar']
    
    for dll_file in dll_files:
        # Extract environment from filename like packetprocessing_dev_osx-arm64.tar
        parts = dll_file.name.split('_')
        if len(parts) >= 2 and parts[1] in ['dev', 'prod']:
            return parts[1]
    
    # Look for deployment files tar
    deploy_files = [f for f in deploy_dir.iterdir() if f.is_file() and f.name.startswith('deployment_files_') and f.suffix == '.tar']
    
    for deploy_file in deploy_files:
        # Extract environment from filename like deployment_files_dev.tar
        parts = deploy_file.name.split('_')
        if len(parts) >= 3 and parts[2].replace('.tar', '') in ['dev', 'prod']:
            return parts[2].replace('.tar', '')
    
    return None

def get_selected_deploy_version(deploy_version_index=None):
    """Get the selected deploy version directory"""
    versions = get_deploy_versions()
    
    if not versions:
        return None
    
    if deploy_version_index is None:
        # Return the newest version (index 0)
        return versions[0][1]  # Return just the directory path
    
    # Validate index
    if deploy_version_index < 1 or deploy_version_index > len(versions):
        print_error(f"Invalid deploy version index: {deploy_version_index}")
        print_error(f"Available versions: 1-{len(versions)}")
        return None
    
    # Return the selected version (convert to 0-based index)
    return versions[deploy_version_index - 1][1]  # Return just the directory path

def load_docker_images_from_deploy(deploy_dir):
    """Load Docker images from tar files in deploy directory"""
    print_info("Loading Docker images from deploy package...")
    
    tar_files = [f for f in deploy_dir.iterdir() if f.is_file() and f.suffix == '.tar' and not f.name.startswith('packetprocessing_') and not f.name.startswith('deployment_files_')]
    
    if not tar_files:
        print_warning("No Docker image tar files found in deploy package")
        return False
    
    for tar_file in tar_files:
        print_info(f"Loading Docker image from {tar_file.name}...")
        try:
            cmd = ['docker', 'load', '-i', str(tar_file)]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print_success(f"Loaded image from {tar_file.name}")
            # Print the loaded image name if available
            if result.stdout:
                print_info(f"  {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to load image from {tar_file.name}: {e}")
            return False
    
    return True

def extract_dll_from_deploy(deploy_dir, environment):
    """Extract DLL from deploy package"""
    print_info("Extracting DLL from deploy package...")
    
    # Find the DLL tar file
    dll_tar_pattern = f"packetprocessing_{environment}_*.tar"
    dll_tar_files = [f for f in deploy_dir.iterdir() if f.is_file() and f.name.startswith(f"packetprocessing_{environment}_") and f.suffix == '.tar']
    
    if not dll_tar_files:
        print_error(f"No DLL tar file found for environment {environment}")
        return False
    
    dll_tar_file = dll_tar_files[0]  # Take the first match
    print_info(f"Extracting DLL from {dll_tar_file.name}...")
    
    try:
        # Ensure release directory exists
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Extract to release directory (ensure we extract into the release directory, not outside it)
        cmd = ['tar', '-xzf', str(dll_tar_file), '-C', str(RELEASE_DIR)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Validate that the extracted directory is within the release folder
        extracted_path = RELEASE_DIR / environment
        if not validate_release_path(extracted_path):
            print_error(f"Extraction created directory outside release folder: {extracted_path}")
            return False
        
        print_success(f"Extracted DLL to {extracted_path}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to extract DLL: {e}")
        return False

def extract_deployment_files_from_deploy(deploy_dir, environment):
    """Extract deployment files from deploy package"""
    print_info("Extracting deployment files from deploy package...")
    
    # Find the deployment files tar
    deploy_tar_files = [f for f in deploy_dir.iterdir() if f.is_file() and f.name.startswith(f"deployment_files_{environment}") and f.suffix == '.tar']
    
    if not deploy_tar_files:
        print_warning(f"No deployment files tar found for environment {environment}")
        return True  # Not critical, continue
    
    deploy_tar_file = deploy_tar_files[0]
    print_info(f"Extracting deployment files from {deploy_tar_file.name}...")
    
    try:
        # Create temporary directory for extraction
        temp_dir = PROJECT_ROOT / "temp_deploy_extract"
        temp_dir.mkdir(exist_ok=True)
        
        # Extract to temp directory
        cmd = ['tar', '-xzf', str(deploy_tar_file), '-C', str(temp_dir)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Copy composer.py if it exists
        composer_src = temp_dir / "composer.py"
        if composer_src.exists():
            shutil.copy2(composer_src, PROJECT_ROOT / "composer.py")
            print_success("Updated composer.py from deploy package")
        
        # Copy docker-compose file if it exists
        compose_filename = f"docker-compose.{environment}.yml"
        compose_src = temp_dir / compose_filename
        if compose_src.exists():
            shutil.copy2(compose_src, PROJECT_ROOT / compose_filename)
            print_success(f"Updated {compose_filename} from deploy package")
        
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        print_success("Extracted deployment files")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to extract deployment files: {e}")
        return False

def build_dll_for_platform(environment, platform):
    """Build the .NET DLL for the specified environment and platform"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Building PacketProcessing for {environment.upper()} on {platform}... [{timestamp}]")
    
    # Create release directory
    release_env_dir = RELEASE_DIR / environment
    if release_env_dir.exists():
        print_info(f"Removing previous build in {release_env_dir}")
        shutil.rmtree(release_env_dir)
    
    release_env_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Build command
        build_cmd = ['dotnet', 'publish', 
                    '-c', 'Release',
                    '-o', str(release_env_dir),
                    '-r', platform,
                    '--self-contained', 'false']
        
        print_info(f"Running: {' '.join(build_cmd)}")
        
        # Run with live output
        process = subprocess.Popen(
            build_cmd,
            cwd=PACKET_PROCESSING_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Stream output
        for line in process.stdout:
            print(line, end='')
        
        process.wait()
        result_code = process.returncode
        
        if result_code == 0:
            print_success(f"Build completed successfully in {release_env_dir}")
            
            # Copy additional files and directories
            print_info("Copying additional files and directories...")
            
            # Copy appsettings files
            base_settings = PACKET_PROCESSING_DIR / "appsettings.json"
            if base_settings.exists():
                shutil.copy2(base_settings, release_env_dir / "appsettings.json")
                print_success("Copied appsettings.json")
            
            # Copy environment-specific appsettings
            normalized_environment = ("Development" if environment == 'dev' else "Production")
            env_settings_name = f"appsettings.{normalized_environment}.json"
            env_settings = PACKET_PROCESSING_DIR / env_settings_name
            
            if env_settings.exists():
                shutil.copy2(env_settings, release_env_dir / env_settings_name)
                print_success(f"Copied {env_settings_name}")
            else:
                print_warning(f"{env_settings_name} not found, skipping")
            
            # Copy swagger.json
            swagger_json = PACKET_PROCESSING_DIR / "swagger.json"
            if swagger_json.exists():
                shutil.copy2(swagger_json, release_env_dir / "swagger.json")
                print_success("Copied swagger.json")
            
            # Copy Properties directory
            properties_dir = PACKET_PROCESSING_DIR / "Properties"
            if properties_dir.exists():
                dest_properties = release_env_dir / "Properties"
                if dest_properties.exists():
                    shutil.rmtree(dest_properties)
                shutil.copytree(properties_dir, dest_properties)
                print_success("Copied Properties directory")
            
            # Copy wwwroot directory
            wwwroot_dir = PACKET_PROCESSING_DIR / "wwwroot"
            if wwwroot_dir.exists():
                dest_wwwroot = release_env_dir / "wwwroot"
                if dest_wwwroot.exists():
                    shutil.rmtree(dest_wwwroot)
                shutil.copytree(wwwroot_dir, dest_wwwroot)
                print_success("Copied wwwroot directory")
            
            return True
        else:
            print_error(f"Build failed with return code {result_code}")
            return False
        
    except subprocess.CalledProcessError as e:
        print_error(f"Build failed with return code {e.returncode}")
        print_error(e.stderr)
        return False

def main():
    """Main entry point"""
    args = sys.argv[1:]
    
    # Handle help and no arguments
    if not args or '--help' in args or '-h' in args:
        print(__doc__)
        return
    
    # Check prerequisites
    if not check_docker():
        sys.exit(1)
    
    if not check_dotnet():
        sys.exit(1)
    
    # Ensure no stray dev/prod directories exist outside release folder
    ensure_release_directory_cleanup()
    
    # Parse arguments
    command = None
    environment = None
    platform = None
    should_build = False
    detached = False
    deploy_version_index = None
    
    # Parse arguments
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg in ['dev', 'prod']:
            environment = arg
        elif arg in ['win-x64', 'linux-x64', 'linux-musl-x64', 'osx-arm64']:
            platform = arg
        elif arg == '--build':
            if command is None:
                command = '--build'
            should_build = True
        elif arg == '-d':
            detached = True
        elif arg == '-r':
            if i + 1 < len(args):
                try:
                    deploy_version_index = int(args[i + 1])
                    i += 1  # Skip the next argument since we consumed it
                except ValueError:
                    print_error("Invalid deploy version index. Must be a number.")
                    sys.exit(1)
            else:
                # Just list versions
                versions = list_deploy_versions()
                sys.exit(0)
        elif arg in ['up', 'stop', 'kill', 'release', 'status']:
            command = arg
        elif arg.startswith('-'):
            # Unknown option
            print_error(f"Unknown option: {arg}")
            print(__doc__)
            sys.exit(1)
        
        i += 1
    
    # Handle release command
    if command == 'release':
        if environment is None:
            print_error("Environment must be specified for 'release' command")
            print("Usage: python composer.py release [dev|prod] [win-x64|linux-x64|linux-musl-x64|osx-arm64]")
            sys.exit(1)
        if platform is None:
            print_error("Platform must be specified for 'release' command")
            print("Usage: python composer.py release [dev|prod] [win-x64|linux-x64|linux-musl-x64|osx-arm64]")
            sys.exit(1)
        if not create_release_package(environment, platform):
            sys.exit(1)
        return
    
    # Handle stop and kill commands
    if command == 'stop':
        if environment is None:
            print_error("Environment must be specified for 'stop' command")
            print("Usage: python composer.py stop [dev|prod]")
            sys.exit(1)
        if not stop_environment(environment):
            sys.exit(1)
        return
    
    if command == 'kill':
        if environment is None:
            print_error("Environment must be specified for 'kill' command")
            print("Usage: python composer.py kill [dev|prod]")
            sys.exit(1)
        if not kill_environment(environment):
            sys.exit(1)
        return
    
    # Handle status command
    if command == 'status':
        show_status()
        return
    
    # Handle up and --build commands
    if command == 'up':
        if environment is None:
            environment = 'prod'  # Default to prod for up
        
        # Check if we need to build or load from deploy package
        if not should_build:
            release_path = RELEASE_DIR / environment / "PacketProcessing.dll"
            if not release_path.exists():
                print_warning("DLL not found, checking for deploy packages...")
                should_build = True
        
        # Build/load if needed
        if should_build:
            # Check if we should use a deploy package
            deploy_version = get_selected_deploy_version(deploy_version_index)
            
            if deploy_version:
                # Get environment from deploy package
                deploy_env = get_deploy_environment(deploy_version)
                
                if deploy_env is None:
                    print_error(f"Could not determine environment for deploy package: {deploy_version.name}")
                    print_error("Please use a deploy package created with the updated composer")
                    sys.exit(1)
                
                # Check if deploy package environment matches requested environment
                if deploy_env != environment:
                    print_warning(f"Deploy package is for {deploy_env.upper()} environment, but {environment.upper()} was requested")
                    print_warning(f"Using {deploy_env.upper()} environment from deploy package")
                    environment = deploy_env  # Override the requested environment
                
                print_header(f"Using deploy package: {deploy_version.name} [{environment.upper()}]")
                
                # Load Docker images from deploy package
                if not load_docker_images_from_deploy(deploy_version):
                    print_error("Failed to load Docker images from deploy package")
                    sys.exit(1)
                
                # Extract DLL from deploy package
                if not extract_dll_from_deploy(deploy_version, environment):
                    print_error("Failed to extract DLL from deploy package")
                    sys.exit(1)
                
                # Extract deployment files from deploy package
                if not extract_deployment_files_from_deploy(deploy_version, environment):
                    print_error("Failed to extract deployment files from deploy package")
                    sys.exit(1)
                
                print_success("Successfully loaded deploy package")
            else:
                # No deploy package available, build from source
                if deploy_version_index is not None:
                    print_error("No deploy versions found")
                    sys.exit(1)
                
                print_info("No deploy package found, building from source...")
                if not build_dll(environment):
                    sys.exit(1)
        
        # Start Docker Compose
        print_header(f"Starting environment: {environment.upper()}")
        if not run_docker_compose(environment, detached=True, show_logs=False):
            print_error("Docker Compose failed, aborting")
            sys.exit(1)
        
        # Wait a bit for services to start
        print_info("Waiting for Docker services to start...")
        time.sleep(5)
        
        # Run DLL
        if not run_dll(environment, detached):
            sys.exit(1)
    
    elif command == '--build' or should_build:
        if environment is None:
            environment = 'prod'  # Default to prod for build
        
        # Check if we should use a deploy package
        deploy_version = get_selected_deploy_version(deploy_version_index)
        
        if deploy_version:
            # Get environment from deploy package
            deploy_env = get_deploy_environment(deploy_version)
            
            if deploy_env is None:
                print_error(f"Could not determine environment for deploy package: {deploy_version.name}")
                print_error("Please use a deploy package created with the updated composer")
                sys.exit(1)
            
            # Check if deploy package environment matches requested environment
            if deploy_env != environment:
                print_warning(f"Deploy package is for {deploy_env.upper()} environment, but {environment.upper()} was requested")
                print_warning(f"Using {deploy_env.upper()} environment from deploy package")
                environment = deploy_env  # Override the requested environment
            
            print_header(f"Using deploy package: {deploy_version.name} [{environment.upper()}]")
            
            # Load Docker images from deploy package
            if not load_docker_images_from_deploy(deploy_version):
                print_error("Failed to load Docker images from deploy package")
                sys.exit(1)
            
            # Extract DLL from deploy package
            if not extract_dll_from_deploy(deploy_version, environment):
                print_error("Failed to extract DLL from deploy package")
                sys.exit(1)
            
            # Extract deployment files from deploy package
            if not extract_deployment_files_from_deploy(deploy_version, environment):
                print_error("Failed to extract deployment files from deploy package")
                sys.exit(1)
            
            print_success("Successfully loaded deploy package")
        else:
            # No deploy package available, build from source
            if deploy_version_index is not None:
                print_error("No deploy versions found")
                sys.exit(1)
            
            print_info("No deploy package found, building from source...")
            if not build_dll(environment):
                sys.exit(1)
    
    else:
        print_error("Unknown command or missing required arguments")
        print(__doc__)
        sys.exit(1)

if __name__ == '__main__':
    main()
