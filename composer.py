#!/usr/bin/env python3
"""
composer - Build and run PacketProcessing with Docker Compose
Usage:
    composer up [dev|prod] [-d]
    composer stop [dev|prod]
    composer kill [dev|prod]
    composer --build
    composer release [win-x64|linux-x64|linux-musl-x64|osx-arm64]
    composer status
    composer help
    
Examples:
    composer up                    # Run prod environment (builds if needed)
    composer up dev                # Run dev environment (builds if needed)
    composer up dev -d             # Run dev in detached mode
    composer stop dev              # Stop dev environment
    composer kill dev              # Kill dev environment (delete DLL and containers)
    composer --build               # Build both dev and prod environments (creates artifacts/releases/)
    composer release linux-x64     # Build and create release package for both dev and prod on specified platform
    composer status                # Show current system status
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

# Try to import tqdm for progress bars, fallback to simple progress if not available
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Configuration
# Handle PyInstaller bundled executable
if getattr(sys, 'frozen', False):
    # Running as compiled executable - use current working directory
    PROJECT_ROOT = Path.cwd()
else:
    # Running as Python script - use script's directory
    PROJECT_ROOT = Path(__file__).parent.absolute()

PACKET_PROCESSING_DIR = PROJECT_ROOT / "PacketProcessing"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
RELEASE_DIR = ARTIFACTS_DIR / "releases"
DEPLOY_DIR = ARTIFACTS_DIR / "packages"
DOCKER_COMPOSE_DEV_FILE = PROJECT_ROOT / "docker-compose.dev.yml"
DOCKER_COMPOSE_PROD_FILE = PROJECT_ROOT / "docker-compose.prod.yml"

def get_latest_package_dir(environment):
    """Get the most recent package directory for the specified environment"""
    if environment not in ['dev', 'prod']:
        return None
    
    if not DEPLOY_DIR.exists():
        return None
    
    # Find all directories matching the pattern
    pattern = f"{environment}_*"
    package_dirs = list(DEPLOY_DIR.glob(pattern))
    
    if not package_dirs:
        return None
    
    # Sort by name (timestamp) and return the most recent
    package_dirs.sort(key=lambda x: x.name, reverse=True)
    return package_dirs[0]

def get_compose_file(environment):
    """Get the compose file for the environment, preferring packages directory.
    Returns (compose_file_path, working_directory)"""
    if environment not in ['dev', 'prod']:
        return None, None
    
    # First, try to find compose file in latest package directory
    package_dir = get_latest_package_dir(environment)
    if package_dir:
        compose_file = package_dir / f"docker-compose.{environment}.yml"
        if compose_file.exists():
            return compose_file, package_dir
    
    # Fall back to root directory
    compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
    return compose_file, PROJECT_ROOT

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

class ProgressBar:
    """Simple progress bar wrapper that works with or without tqdm"""
    def __init__(self, total, desc="", unit="", disable=False):
        self.total = total
        self.desc = desc
        self.unit = unit
        self.current = 0
        self.disable = disable or not HAS_TQDM
        
        if not self.disable:
            self.bar = tqdm(total=total, desc=desc, unit=unit, ncols=80, leave=False)
        else:
            self.bar = None
            if desc:
                print_info(f"{desc}...")
    
    def update(self, n=1):
        self.current += n
        if self.bar:
            self.bar.update(n)
        elif not self.disable:
            # Simple text progress
            percent = int((self.current / self.total) * 100) if self.total > 0 else 0
            print(f"\r{self.desc}: {percent}%", end='', flush=True)
    
    def set_description(self, desc):
        if self.bar:
            self.bar.set_description(desc)
        self.desc = desc
    
    def close(self):
        if self.bar:
            self.bar.close()
        elif not self.disable and self.current > 0:
            print()  # New line after simple progress
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

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

def ensure_release_directory_cleanup():
    """Ensure no dev/prod directories exist outside the artifacts directory"""
    print_info("Checking for stray dev/prod directories...")
    
    # Check project root for dev/prod directories (but exclude known directories)
    project_root = PROJECT_ROOT
    stray_dirs = []
    
    # Directories to exclude from cleanup (these are legitimate project directories)
    excluded_dirs = {
        RELEASE_DIR / 'dev',
        RELEASE_DIR / 'prod',
        DEPLOY_DIR,
        ARTIFACTS_DIR,
        PACKET_PROCESSING_DIR,
    }
    
    for item in project_root.iterdir():
        if item.is_dir() and item.name in ['dev', 'prod', 'release', 'deploy', 'artifacts']:
            # Check if it's not in our excluded directories
            if item not in excluded_dirs:
                stray_dirs.append(item)
    
    if stray_dirs:
        print_warning(f"Found stray directories outside artifacts folder: {[str(d) for d in stray_dirs]}")
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

def copy_build_files_with_progress(environment, release_env_dir):
    """Copy additional files and directories with progress bar"""
    files_to_copy = []
    dirs_to_copy = []
    
    # Collect files to copy
    base_settings = PACKET_PROCESSING_DIR / "appsettings.json"
    if base_settings.exists():
        files_to_copy.append(("appsettings.json", base_settings, release_env_dir / "appsettings.json"))
    
    normalized_environment = ("Development" if environment == 'dev' else "Production")
    env_settings_name = f"appsettings.{normalized_environment}.json"
    env_settings = PACKET_PROCESSING_DIR / env_settings_name
    if env_settings.exists():
        files_to_copy.append((env_settings_name, env_settings, release_env_dir / env_settings_name))
    
    swagger_json = PACKET_PROCESSING_DIR / "swagger.json"
    if swagger_json.exists():
        files_to_copy.append(("swagger.json", swagger_json, release_env_dir / "swagger.json"))
    
    compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
    if compose_file.exists():
        files_to_copy.append((compose_file.name, compose_file, release_env_dir / compose_file.name))
    
    # Collect directories to copy
    properties_dir = PACKET_PROCESSING_DIR / "Properties"
    if properties_dir.exists():
        dirs_to_copy.append(("Properties", properties_dir, release_env_dir / "Properties"))
    
    wwwroot_dir = PACKET_PROCESSING_DIR / "wwwroot"
    if wwwroot_dir.exists():
        dirs_to_copy.append(("wwwroot", wwwroot_dir, release_env_dir / "wwwroot"))
    
    total_ops = len(files_to_copy) + len(dirs_to_copy)
    if total_ops > 0:
        with ProgressBar(total=total_ops, desc="Copying files", unit="item") as pbar:
            # Copy files
            for name, src, dst in files_to_copy:
                pbar.set_description(f"Copying {name}")
                shutil.copy2(src, dst)
                pbar.update(1)
            
            # Copy directories
            for name, src, dst in dirs_to_copy:
                pbar.set_description(f"Copying {name} directory")
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                pbar.update(1)
        
        print_success(f"Copied {total_ops} items")

def build_dll(environment='prod', show_progress=True):
    """Build the .NET DLL for the specified environment"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    # Check if PacketProcessing directory exists
    if not PACKET_PROCESSING_DIR.exists():
        print_error(f"PacketProcessing directory not found: {PACKET_PROCESSING_DIR}")
        print_error("Please run this script from the KanatBackend directory")
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
                cwd=str(PACKET_PROCESSING_DIR),
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
                                  cwd=str(PACKET_PROCESSING_DIR),
                                  check=True,
                                  capture_output=True,
                                  text=True)
            result_code = result.returncode
        
        if result_code == 0:
            print_success(f"Build completed successfully in {release_env_dir}")
            
            # Copy additional files and directories with progress
            copy_build_files_with_progress(environment, release_env_dir)
            
            return True
        else:
            print_error(f"Build failed with return code {result_code}")
            return False
        
    except subprocess.CalledProcessError as e:
        print_error(f"Build failed with return code {e.returncode}")
        print_error(e.stderr)
        return False

def is_environment_running(environment):
    """Check if the specified environment is currently running"""
    if environment not in ['dev', 'prod']:
        return False
    
    project_name = f"kanatbackend-{environment}"
    compose_file, work_dir = get_compose_file(environment)
    if not compose_file:
        return False
    
    try:
        # Check if any containers for this project are running
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'ps', '-q']
        result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            # Check if any of the containers are actually running (not just created)
            container_ids = result.stdout.strip().split('\n')
            for container_id in container_ids:
                if container_id:
                    # Check container status
                    status_cmd = ['docker', 'inspect', '--format', '{{.State.Status}}', container_id]
                    status_result = subprocess.run(status_cmd, capture_output=True, text=True)
                    if status_result.returncode == 0 and status_result.stdout.strip() == 'running':
                        return True
        return False
    except Exception:
        return False

def run_docker_compose(environment='prod', detached=False, show_logs=True, project_name=None):
    """Run Docker Compose for the specified environment"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    compose_file, work_dir = get_compose_file(environment)
    if not compose_file or not compose_file.exists():
        print_error(f"Docker Compose file not found: {compose_file}")
        return False
    
    if project_name is None:
        # Use environment-specific project names for separate container/network/volume namespaces
        project_name = f"kanatbackend-{environment}"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Starting Docker Compose for {environment.upper()}... [{timestamp}]")
    
    # Show which compose file is being used
    if work_dir != PROJECT_ROOT:
        print_info(f"Using compose file from package: {compose_file}")
    
    try:
        if detached:
            # Start in detached mode first
            cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'up', '-d']
            print_info("Starting services in detached mode...")
            
            result = subprocess.run(cmd, cwd=work_dir, check=True, capture_output=True, text=True)
            
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
        # Docker Compose errors are often in stdout, not stderr
        error_output = e.stdout if e.stdout else e.stderr
        if error_output:
            # Extract the actual error message
            error_lines = error_output.strip().split('\n')
            # Find the error line (usually contains "Error" or "failed")
            for line in error_lines:
                if 'Error' in line or 'error' in line or 'failed' in line:
                    print_error(f"Error: {line}")
                    break
            # If no specific error line found, print the last few lines
            if len(error_lines) > 0:
                # Print the last meaningful error line
                for line in reversed(error_lines):
                    if line.strip() and ('Error' in line or 'error' in line or 'failed' in line or 'port' in line.lower()):
                        print_error(f"Error: {line}")
                        break
        return False

def run_dll(environment='prod', detached=False):
    """Run the .NET DLL for the specified environment"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    dll_path = RELEASE_DIR / environment / "PacketProcessing.dll"
    
    if not dll_path.exists():
        print_error(f"DLL not found: {dll_path}")
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
    compose_file, work_dir = get_compose_file(environment)
    if not compose_file:
        print_error(f"Docker Compose file not found for {environment}")
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Stopping environment: {environment.upper()}... [{timestamp}]")
    
    # Stop Docker Compose containers
    print_info("Stopping Docker Compose containers...")
    try:
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'stop']
        subprocess.run(cmd, cwd=work_dir, check=True, capture_output=True, text=True)
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
    compose_file, work_dir = get_compose_file(environment)
    if not compose_file:
        print_error(f"Docker Compose file not found for {environment}")
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print_header(f"Killing environment: {environment.upper()}... [{timestamp}]")
    
    # First stop the environment
    stop_environment(environment)
    
    # Remove Docker Compose containers
    print_info("Removing Docker Compose containers...")
    try:
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'rm', '-f']
        subprocess.run(cmd, cwd=work_dir, check=True, capture_output=True, text=True)
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

def get_required_images_from_compose(compose_file):
    """Get list of Docker images required by compose file (only pullable base images, not built images)"""
    images = []
    
    try:
        with open(compose_file, 'r') as f:
            lines = f.readlines()
        
        import re
        # Look for "image:" lines
        image_pattern = r'^\s*image:\s*(.+)$'
        # Look for build context lines
        context_pattern = r'^\s*context:\s*(.+)$'
        # Look for service names (indented under services:, not top-level keys)
        # Service names are indented with 2 spaces and followed by a colon
        service_pattern = r'^  (\w[\w-]*):\s*$'
        
        i = 0
        services = {}  # service_name -> {'has_build': bool, 'image': str, 'build_context': str}
        in_services_section = False
        
        # First pass: parse all services to understand their structure
        current_service = None
        while i < len(lines):
            line = lines[i]
            
            # Check if we're in the services section
            if re.match(r'^services:\s*$', line):
                in_services_section = True
                i += 1
                continue
            
            # Check if we've left the services section (hit a top-level key)
            if in_services_section and re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*:\s*$', line) and not line.startswith(' '):
                in_services_section = False
                current_service = None
            
            # Only look for services when we're in the services section
            if in_services_section:
                # Check if this is a new service definition (2 spaces indent)
                service_match = re.match(service_pattern, line)
                if service_match:
                    current_service = service_match.group(1)
                    if current_service not in services:
                        services[current_service] = {'has_build': False, 'image': None, 'build_context': None}
                    i += 1
                    continue
            
            if current_service:
                # Check for image: tag
                image_match = re.match(image_pattern, line)
                if image_match:
                    image_name = image_match.group(1).strip().strip('"\'')
                    services[current_service]['image'] = image_name
                
                # Check for build: section
                if re.match(r'^\s*build:', line):
                    services[current_service]['has_build'] = True
                    # Look for context: in the next few lines
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j]
                        next_stripped = next_line.strip()
                        
                        # Check if we've left the build section
                        if next_stripped and not next_line.startswith(' ') and not next_line.startswith('\t'):
                            break
                        if next_stripped and ':' in next_stripped and not next_stripped.startswith('context:'):
                            if not next_line.startswith('    '):  # Not indented = new section
                                break
                        
                        context_match = re.match(context_pattern, next_line)
                        if context_match:
                            context_path_str = context_match.group(1).strip().strip('"\'')
                            services[current_service]['build_context'] = context_path_str
                            break
                        j += 1
                        if j - i > 10:  # Safety limit
                            break
            
            i += 1
        
        # Second pass: collect images based on service structure
        for service_name, service_info in services.items():
            if service_info['has_build']:
                # Service has build: - get base image from Dockerfile, ignore image: tag
                if service_info['build_context']:
                    # Resolve context path relative to compose file directory
                    context_path_str = service_info['build_context']
                    # Handle relative paths like ./QuestDB
                    if context_path_str.startswith('./'):
                        context_path_str = context_path_str[2:]
                    context_path = compose_file.parent / context_path_str
                    dockerfile_path = context_path / 'Dockerfile'
                    if dockerfile_path.exists():
                        # Read Dockerfile to get base image
                        with open(dockerfile_path, 'r') as df:
                            for df_line in df:
                                if df_line.strip().startswith('FROM'):
                                    base_image = df_line.strip().split('FROM', 1)[1].strip().split()[0]
                                    if base_image and base_image not in images:
                                        images.append(base_image)
                                    break
            else:
                # Service has no build: - use image: tag (but skip built image names)
                if service_info['image']:
                    image_name = service_info['image']
                    # Skip built image names (kanatbackend-questdb-*)
                    if 'kanatbackend-questdb' not in image_name:
                        if image_name not in images:
                            images.append(image_name)
    
    except Exception as e:
        print_warning(f"Could not parse compose file for required images: {e}")
    
    return images

def get_docker_images_from_compose(compose_file):
    """Get list of Docker images used in a compose file (actual image names after building)"""
    images = []
    # Use consistent project name 'kanatbackend' so images are named kanatbackend-questdb-dev/prod
    project_name = "kanatbackend"
    
    # Primary method: Use docker compose config --images to get all image names
    # This works for both image: tags and build: contexts after images are built
    try:
        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'config', '--images']
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
        compose_images = [line.strip() for line in result.stdout.split('\n') if line.strip()]
        images.extend(compose_images)
    except subprocess.CalledProcessError:
        # Fallback: try to get images from docker compose images command
        try:
            cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'images', '-q']
            result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
            image_ids = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            
            # Get image names and tags from image IDs
            for image_id in image_ids:
                cmd = ['docker', 'inspect', '--format={{.RepoTags}}', image_id]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                tags = result.stdout.strip().strip('[]').replace('"', '').split(',')
                for tag in tags:
                    if tag.strip():
                        images.append(tag.strip())
        except subprocess.CalledProcessError:
            # Last fallback: parse compose file directly for image: tags
            try:
                import re
                with open(compose_file, 'r') as f:
                    content = f.read()
                    image_pattern = r'^\s*image:\s*(.+)$'
                    for line in content.split('\n'):
                        match = re.match(image_pattern, line)
                        if match:
                            image_name = match.group(1).strip().strip('"\'')
                            if image_name and image_name not in images:
                                images.append(image_name)
            except Exception:
                pass
    
    # Remove duplicates while preserving order
    seen = set()
    unique_images = []
    for img in images:
        if img and img not in seen:
            seen.add(img)
            unique_images.append(img)
    
    return unique_images

def create_release_package(platform):
    """Create a release package by building DLLs and packaging Docker images, DLLs, and configuration files for both dev and prod.
    Builds DLLs for the specified platform and creates packages in artifacts/packages/.
    Works offline - uses existing Docker images or builds from local context only (no internet required).
    """
    if platform not in ['win-x64', 'linux-x64', 'linux-musl-x64', 'osx-arm64']:
        print_error(f"Invalid platform: {platform}. Must be one of: win-x64, linux-x64, linux-musl-x64, osx-arm64")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print_header(f"Creating release package for both dev and prod on {platform}... [{timestamp}]")
    
    # Create packages directory structure - override existing
    if DEPLOY_DIR.exists():
        print_info("Removing existing packages directory...")
        shutil.rmtree(DEPLOY_DIR)
    
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create timestamped directories for both environments
    deploy_dev_dir = DEPLOY_DIR / f"dev_{timestamp}"
    deploy_prod_dir = DEPLOY_DIR / f"prod_{timestamp}"
    deploy_dev_dir.mkdir(parents=True, exist_ok=True)
    deploy_prod_dir.mkdir(parents=True, exist_ok=True)
    
    print_success(f"Created package directories: {deploy_dev_dir.name}, {deploy_prod_dir.name}")
    
    # Build DLLs for both environments with progress
    print_info("Building DLLs for specified platform...")
    with ProgressBar(total=2, desc="Building DLLs", unit="env") as pbar:
        pbar.set_description("Building dev DLL")
        if not build_dll_for_platform('dev', platform):
            return False
        pbar.update(1)
        
        pbar.set_description("Building prod DLL")
        if not build_dll_for_platform('prod', platform):
            return False
        pbar.update(1)
    
    # Get images to export:
    # 1. Built QuestDB images (kanatbackend-questdb-dev, kanatbackend-questdb-prod)
    # 2. Base images (postgres:15-alpine, datalust/seq:latest) - but NOT questdb/questdb:latest
    print_info("Getting Docker images to export...")
    
    # Get all images from compose files (includes both built and base images)
    all_compose_images = set()
    for compose_file in [DOCKER_COMPOSE_DEV_FILE, DOCKER_COMPOSE_PROD_FILE]:
        compose_images = get_docker_images_from_compose(compose_file)
        all_compose_images.update(compose_images)
    
    # Get base images separately to ensure we have postgres and seq
    base_images = set()
    for compose_file in [DOCKER_COMPOSE_DEV_FILE, DOCKER_COMPOSE_PROD_FILE]:
        required_base_images = get_required_images_from_compose(compose_file)
        # Filter out questdb base image, only keep postgres and seq
        for img in required_base_images:
            if 'questdb' not in img.lower():
                base_images.add(img)
    
    # Combine: built images from compose + base images (postgres, seq only)
    # Filter out questdb base image if it somehow got included
    all_images_to_export = set()
    for img in all_compose_images:
        # Include all built images (kanatbackend-questdb-dev, kanatbackend-questdb-prod)
        # and base images that are not questdb
        if 'questdb/questdb' not in img.lower():
            all_images_to_export.add(img)
    
    # Also add base images (postgres, seq) to ensure they're included
    all_images_to_export.update(base_images)
    
    all_images_to_export = sorted(list(all_images_to_export))
    
    if not all_images_to_export:
        print_warning("No Docker images found to export")
    else:
        print_info(f"Images to export: {', '.join(all_images_to_export)}")
        
        # Verify images exist, pull base images and build compose services as needed
        missing_images = []
        for image_name in all_images_to_export:
            try:
                cmd = ['docker', 'image', 'inspect', image_name]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError:
                missing_images.append(image_name)
        
        if missing_images:
            print_info(f"Some images missing, will pull base images and build compose services...")
            
            # Separate base images (need to be pulled) from built images (need to be built)
            missing_base_images = [img for img in missing_images if 'kanatbackend' not in img]
            missing_built_images = [img for img in missing_images if 'kanatbackend' in img]
            
            # First, try to pull missing base images
            if missing_base_images:
                print_info(f"Pulling missing base images: {', '.join(missing_base_images)}")
                for idx, image_name in enumerate(missing_base_images, 1):
                    print_info(f"[{idx}/{len(missing_base_images)}] Pulling {image_name}...")
                    try:
                        cmd = ['docker', 'pull', image_name]
                        # If stdout is a TTY, let Docker show its native progress bars directly
                        if sys.stdout.isatty():
                            subprocess.run(cmd, check=True)
                        else:
                            # Not a TTY, stream output to show progress
                            process = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )
                            # Stream output character by character to preserve \r updates
                            while True:
                                char = process.stdout.read(1)
                                if not char:
                                    break
                                sys.stdout.write(char)
                                sys.stdout.flush()
                            process.wait()
                            if process.returncode != 0:
                                raise subprocess.CalledProcessError(process.returncode, cmd)
                            print()  # Newline after streaming
                        print_success(f"Pulled {image_name}")
                    except subprocess.CalledProcessError as e:
                        print_error(f"Failed to pull base image {image_name}: {e}")
                        print_error("Release requires internet connection to pull base Docker images")
                        return False
            
            # Then, build compose services for missing built images
            if missing_built_images:
                print_info(f"Building compose services for: {', '.join(missing_built_images)}")
                try:
                    project_name = "kanatbackend"
                    for compose_file in [DOCKER_COMPOSE_DEV_FILE, DOCKER_COMPOSE_PROD_FILE]:
                        env_name = "dev" if "dev" in compose_file.name else "prod"
                        print_info(f"Building {env_name.upper()} compose services...")
                        cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'build']
                        # Show Docker's native progress output
                        if sys.stdout.isatty():
                            subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
                        else:
                            process = subprocess.Popen(
                                cmd,
                                cwd=PROJECT_ROOT,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )
                            while True:
                                char = process.stdout.read(1)
                                if not char:
                                    break
                                sys.stdout.write(char)
                                sys.stdout.flush()
                            process.wait()
                            if process.returncode != 0:
                                raise subprocess.CalledProcessError(process.returncode, cmd)
                    print_success("Docker Compose images built successfully")
                except subprocess.CalledProcessError as e:
                    print_error(f"Failed to build Docker Compose images: {e}")
                    return False
            
            # Re-check if all images exist now
            still_missing = []
            for image_name in all_images_to_export:
                try:
                    cmd = ['docker', 'image', 'inspect', image_name]
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError:
                    still_missing.append(image_name)
            
            if still_missing:
                print_error(f"Still missing required Docker images: {', '.join(still_missing)}")
                return False
        
        # Export images to both dev and prod package directories (images are shared)
        print_info(f"Exporting {len(all_images_to_export)} Docker image(s) to both dev and prod packages...")
        with ProgressBar(total=len(all_images_to_export), desc="Exporting images", unit="image") as img_pbar:
            for image_name in all_images_to_export:
                img_pbar.set_description(f"Exporting {image_name.split(':')[0] if ':' in image_name else image_name}")
                # Clean image name for filename
                safe_name = image_name.replace('/', '_').replace(':', '_')
                tar_filename = f"{safe_name}.tar"
                
                # Export to both dev and prod directories
                for deploy_dir in [deploy_dev_dir, deploy_prod_dir]:
                    tar_path = deploy_dir / tar_filename
                    try:
                        cmd = ['docker', 'save', '-o', str(tar_path), image_name]
                        subprocess.run(cmd, check=True, capture_output=True, text=True)
                    except subprocess.CalledProcessError as e:
                        print_error(f"Failed to export {image_name} to {deploy_dir.name}: {e}")
                        return False
                img_pbar.update(1)
        
        print_success(f"Exported {len(all_images_to_export)} image(s) to both dev and prod packages")
    
    # Process both environments for DLLs and compose files
    with ProgressBar(total=2, desc="Processing environments", unit="env") as env_pbar:
        for environment in ['dev', 'prod']:
            deploy_dir = deploy_dev_dir if environment == 'dev' else deploy_prod_dir
            compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
            
            env_pbar.set_description(f"Processing {environment.upper()}")
            print_header(f"Processing {environment.upper()} environment...")
            
            # Create DLL tar
            dll_dir = RELEASE_DIR / environment
            if not dll_dir.exists():
                print_error(f"DLL directory not found: {dll_dir}")
                return False
            
            dll_tar_path = deploy_dir / f"packetprocessing_{environment}_{platform}.tar"
            try:
                with ProgressBar(total=1, desc=f"Creating {environment.upper()} DLL tar", unit="file") as tar_pbar:
                    cmd = ['tar', '-czf', str(dll_tar_path), '-C', str(dll_dir.parent), environment]
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                    tar_pbar.update(1)
                print_success(f"Created DLL tar: {dll_tar_path.name}")
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to create DLL tar: {e}")
                return False
            
            # Copy docker-compose file
            compose_dest = deploy_dir / compose_file.name
            if compose_file.exists():
                shutil.copy2(compose_file, compose_dest)
                print_success(f"Copied {compose_file.name}")
            
            # Copy QuestDB directory (contains Dockerfile needed for building QuestDB images)
            questdb_dir = PROJECT_ROOT / "QuestDB"
            if questdb_dir.exists():
                questdb_dest = deploy_dir / "QuestDB"
                if questdb_dest.exists():
                    shutil.rmtree(questdb_dest)
                shutil.copytree(questdb_dir, questdb_dest)
                print_success(f"Copied QuestDB directory")
            
            env_pbar.update(1)
    
    # Stop Docker Compose (cleanup)
    print_info("Stopping Docker Compose services...")
    for environment in ['dev', 'prod']:
        compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
        project_name = f"kanatbackend-{environment}"
        try:
            cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'down']
            subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            pass  # Ignore if not running
    
    print_success(f"Release package created successfully in {DEPLOY_DIR}")
    print_info(f"Package contents:")
    for deploy_dir in [deploy_dev_dir, deploy_prod_dir]:
        print_info(f"  {deploy_dir.name}:")
        for item in deploy_dir.iterdir():
            size = item.stat().st_size if item.is_file() else "dir"
            size_str = f"{size / (1024*1024):.2f} MB" if isinstance(size, int) else str(size)
            print_info(f"    - {item.name} ({size_str})")
    
    return True

def build_dll_for_platform(environment, platform):
    """Build the .NET DLL for the specified environment and platform"""
    if environment not in ['dev', 'prod']:
        print_error(f"Invalid environment: {environment}. Must be 'dev' or 'prod'")
        return False
    
    # Check if PacketProcessing directory exists
    if not PACKET_PROCESSING_DIR.exists():
        print_error(f"PacketProcessing directory not found: {PACKET_PROCESSING_DIR}")
        print_error("Please run this script from the KanatBackend directory")
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
            cwd=str(PACKET_PROCESSING_DIR),
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
            
            # Copy additional files and directories with progress
            copy_build_files_with_progress(environment, release_env_dir)
            
            return True
        else:
            print_error(f"Build failed with return code {result_code}")
            return False
        
    except subprocess.CalledProcessError as e:
        print_error(f"Build failed with return code {e.returncode}")
        print_error(e.stderr)
        return False

def check_deploy_dir_exists():
    """Check if deploy directory exists and has valid content"""
    if not DEPLOY_DIR.exists():
        return False
    
    # Check for at least one environment directory
    env_dirs = [d for d in DEPLOY_DIR.iterdir() if d.is_dir() and (d.name.startswith('dev_') or d.name.startswith('prod_'))]
    return len(env_dirs) > 0

def load_from_deploy(environment):
    """Load build from deploy directory"""
    if not check_deploy_dir_exists():
        return False
    
    # Find the most recent deploy directory for this environment
    env_dirs = [d for d in DEPLOY_DIR.iterdir() 
                if d.is_dir() and d.name.startswith(f"{environment}_")]
    
    if not env_dirs:
        print_info(f"No deploy package found for {environment.upper()} environment")
        return False
    
    # Sort by name (timestamp) and get the most recent
    env_dirs.sort(key=lambda x: x.name, reverse=True)
    deploy_dir = env_dirs[0]
    
    print_info(f"Found deploy package: {deploy_dir.name}")
    
    # Load Docker images
    tar_files = [f for f in deploy_dir.iterdir() 
                 if f.is_file() and f.suffix == '.tar' 
                 and not f.name.startswith('packetprocessing_')]
    
    if tar_files:
        print_info(f"Loading {len(tar_files)} Docker image(s) from deploy package...")
        with ProgressBar(total=len(tar_files), desc="Loading images", unit="image") as pbar:
            for tar_file in tar_files:
                pbar.set_description(f"Loading {tar_file.name.split('.')[0]}")
                try:
                    cmd = ['docker', 'load', '-i', str(tar_file)]
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                    pbar.update(1)
                except subprocess.CalledProcessError as e:
                    print_info(f"Could not load image from {tar_file.name}: {e}")
                    return False
        print_success(f"Loaded {len(tar_files)} image(s)")
    
    # Extract DLL
    dll_tar_files = [f for f in deploy_dir.iterdir() 
                     if f.is_file() and f.name.startswith(f"packetprocessing_{environment}_") 
                     and f.suffix == '.tar']
    
    if not dll_tar_files:
        print_info(f"No DLL tar file found for {environment.upper()} in deploy package")
        return False
    
    print_info("Extracting DLL from deploy package...")
    dll_tar_file = dll_tar_files[0]
    try:
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        with ProgressBar(total=1, desc="Extracting DLL", unit="file") as pbar:
            cmd = ['tar', '-xzf', str(dll_tar_file), '-C', str(RELEASE_DIR)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            pbar.update(1)
        print_success(f"Extracted DLL to {RELEASE_DIR / environment}")
    except subprocess.CalledProcessError as e:
        print_info(f"Could not extract DLL: {e}")
        return False
    
    # Copy docker-compose file if it exists
    compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
    compose_src = deploy_dir / compose_file.name
    if compose_src.exists():
        shutil.copy2(compose_src, compose_file)
        print_success(f"Updated {compose_file.name} from deploy package")
    
    return True

def build_both_environments():
    """Build both dev and prod environments.
    First tries to load from packages directory (no internet required).
    If packages don't exist, builds from source (requires internet for Docker images).
    """
    print_header("Building both dev and prod environments...")
    
    # First, try to load from packages directory
    if check_deploy_dir_exists():
        print_info("Packages directory found, attempting to load from packages...")
        with ProgressBar(total=2, desc="Loading from packages", unit="env") as pbar:
            pbar.set_description("Loading dev")
            dev_loaded = load_from_deploy('dev')
            pbar.update(1)
            
            pbar.set_description("Loading prod")
            prod_loaded = load_from_deploy('prod')
            pbar.update(1)
        
        if dev_loaded and prod_loaded:
            print_success("Successfully loaded both environments from packages directory")
            return True
        else:
            # First option failed - write as information
            print_info("Could not fully load from packages directory, will build from source")
    else:
        print_info("Packages directory not found, will build from source")
    
    # Build from source (second option) - requires internet for Docker images
    print_info("Building from source files in PacketProcessing directory (requires internet for Docker images)...")
    
    # Build .NET DLLs
    with ProgressBar(total=2, desc="Building DLLs", unit="env") as pbar:
        pbar.set_description("Building dev DLL")
        if not build_dll('dev', show_progress=True):
            # Second option failed - write as error
            print_error("Failed to build dev environment DLL from source")
            return False
        pbar.update(1)
        
        pbar.set_description("Building prod DLL")
        if not build_dll('prod', show_progress=True):
            # Second option failed - write as error
            print_error("Failed to build prod environment DLL from source")
            return False
        pbar.update(1)
    
    # Build Docker images (requires internet)
    # Images are shared between dev and prod, so build once
    print_info("Building Docker images (requires internet connection)...")
    
    # Get all required images from both compose files (they should be the same)
    all_required_images = set()
    for compose_file in [DOCKER_COMPOSE_DEV_FILE, DOCKER_COMPOSE_PROD_FILE]:
        required_images = get_required_images_from_compose(compose_file)
        all_required_images.update(required_images)
    
    if all_required_images:
        print_info(f"Pulling required base images: {', '.join(sorted(all_required_images))}")
        sorted_images = sorted(all_required_images)
        for idx, image_name in enumerate(sorted_images, 1):
            print_info(f"[{idx}/{len(sorted_images)}] Pulling {image_name}...")
            try:
                cmd = ['docker', 'pull', image_name]
                # If stdout is a TTY, let Docker show its native progress bars directly
                if sys.stdout.isatty():
                    # Run directly - Docker will show its progress bars
                    subprocess.run(cmd, check=True)
                else:
                    # Not a TTY, stream output to show progress
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )
                    
                    # Stream output character by character to preserve \r updates
                    while True:
                        char = process.stdout.read(1)
                        if not char:
                            break
                        sys.stdout.write(char)
                        sys.stdout.flush()
                    
                    process.wait()
                    if process.returncode != 0:
                        raise subprocess.CalledProcessError(process.returncode, cmd)
                    print()  # Newline after streaming
                
                print_success(f"Pulled {image_name}")
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to pull base image {image_name}: {e}")
                print_error("Building from source requires internet connection to pull Docker images")
                return False
        print_success(f"Pulled {len(all_required_images)} base image(s)")
    
    # Build compose services for both dev and prod
    # Build both to get kanatbackend-questdb-dev and kanatbackend-questdb-prod images
    # Use compose files from packages if available, otherwise use root
    print_info("Building Docker Compose services for both dev and prod...")
    try:
        project_name = "kanatbackend"
        # Build both dev and prod compose files
        for environment in ['dev', 'prod']:
            compose_file, work_dir = get_compose_file(environment)
            if not compose_file:
                # Fall back to root compose files for building
                compose_file = DOCKER_COMPOSE_DEV_FILE if environment == 'dev' else DOCKER_COMPOSE_PROD_FILE
                work_dir = PROJECT_ROOT
            
            print_info(f"Building {environment.upper()} compose services...")
            if work_dir != PROJECT_ROOT:
                print_info(f"Using compose file from package: {compose_file}")
            cmd = ['docker', 'compose', '-p', project_name, '-f', str(compose_file), 'build']
            # Show Docker's native progress output
            if sys.stdout.isatty():
                subprocess.run(cmd, cwd=work_dir, check=True)
            else:
                process = subprocess.Popen(
                    cmd,
                    cwd=work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                while True:
                    char = process.stdout.read(1)
                    if not char:
                        break
                    sys.stdout.write(char)
                    sys.stdout.flush()
                process.wait()
                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, cmd)
        print_success("Docker Compose images built successfully for both dev and prod")
    except subprocess.CalledProcessError as e:
        # Docker compose build failed - this is an error
        print_error(f"Failed to build Docker Compose images: {e}")
        print_error("Building from source requires internet connection to pull Docker images")
        return False
    
    print_success("Successfully built both environments from source")
    return True

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
    print_info("\nRelease Builds (artifacts/releases):")
    if RELEASE_DIR.exists():
        for env_dir in RELEASE_DIR.iterdir():
            if env_dir.is_dir() and env_dir.name in ['dev', 'prod']:
                dll_path = env_dir / "PacketProcessing.dll"
                status = "✓ Built" if dll_path.exists() else "✗ Missing DLL"
                print_info(f"  {env_dir.name}: {status}")
    else:
        print_info("  No releases directory found")
    
    # Check deploy packages
    print_info("\nRelease Packages (artifacts/packages):")
    if DEPLOY_DIR.exists():
        env_dirs = [d for d in DEPLOY_DIR.iterdir() 
                    if d.is_dir() and (d.name.startswith('dev_') or d.name.startswith('prod_'))]
        if env_dirs:
            # Sort by name (timestamp) and show most recent
            env_dirs.sort(key=lambda x: x.name, reverse=True)
            for deploy_dir in env_dirs[:5]:  # Show only last 5
                file_count = len([f for f in deploy_dir.iterdir() if f.is_file()])
                print_info(f"  {deploy_dir.name} ({file_count} files)")
        else:
            print_info("  No release packages found")
    else:
        print_info("  No packages directory found")

def main():
    """Main entry point"""
    args = sys.argv[1:]
    
    # Handle help and no arguments
    if not args or '--help' in args or '-h' in args or 'help' in args:
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
    detached = False
    
    # Parse arguments
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg in ['dev', 'prod']:
            environment = arg
        elif arg in ['win-x64', 'linux-x64', 'linux-musl-x64', 'osx-arm64']:
            platform = arg
        elif arg == '-d':
            detached = True
        elif arg in ['up', 'stop', 'kill', 'release', 'status', '--build']:
            command = arg
        elif arg.startswith('-'):
            # Unknown option
            print_error(f"Unknown option: {arg}")
            print(__doc__)
            sys.exit(1)
        
        i += 1
    
    # Handle release command
    if command == 'release':
        if platform is None:
            print_error("Platform must be specified for 'release' command")
            print("Usage: composer release [win-x64|linux-x64|linux-musl-x64|osx-arm64]")
            sys.exit(1)
        if not create_release_package(platform):
            sys.exit(1)
        return
    
    # Handle stop and kill commands
    if command == 'stop':
        if environment is None:
            print_error("Environment must be specified for 'stop' command")
            print("Usage: composer stop [dev|prod]")
            sys.exit(1)
        if not stop_environment(environment):
            sys.exit(1)
        return
    
    if command == 'kill':
        if environment is None:
            print_error("Environment must be specified for 'kill' command")
            print("Usage: composer kill [dev|prod]")
            sys.exit(1)
        if not kill_environment(environment):
            sys.exit(1)
        return
    
    # Handle status command
    if command == 'status':
        show_status()
        return
    
    # Handle build command
    if command == '--build':
        if not build_both_environments():
            sys.exit(1)
        return
    
    # Handle up command
    if command == 'up':
        if environment is None:
            environment = 'prod'  # Default to prod for up
        
        # Check if the other environment is running and stop it
        other_environment = 'dev' if environment == 'prod' else 'prod'
        if is_environment_running(other_environment):
            print_warning(f"{other_environment.upper()} environment is running. Stopping it first...")
            if not stop_environment(other_environment):
                print_error(f"Failed to stop {other_environment.upper()} environment")
                sys.exit(1)
            print_success(f"Stopped {other_environment.upper()} environment")
        
        with ProgressBar(total=3, desc="Starting environment", unit="step") as pbar:
            # Check if release exists, if not build both
            release_path = RELEASE_DIR / environment / "PacketProcessing.dll"
            if not release_path.exists():
                pbar.set_description("Building environments")
                print_warning(f"DLL not found for {environment.upper()}, building both environments...")
                if not build_both_environments():
                    sys.exit(1)
            pbar.update(1)
            
            # Start Docker Compose
            pbar.set_description("Starting Docker Compose")
            print_header(f"Starting environment: {environment.upper()}")
            if not run_docker_compose(environment, detached=True, show_logs=False):
                print_error("Docker Compose failed, aborting")
                sys.exit(1)
            pbar.update(1)
            
            # Wait a bit for services to start
            pbar.set_description("Waiting for services")
            print_info("Waiting for Docker services to start...")
            time.sleep(5)
            pbar.update(1)
        
        # Run DLL
        print_header(f"Starting PacketProcessing application...")
        if not run_dll(environment, detached):
            sys.exit(1)
    
    else:
        print_error("Unknown command or missing required arguments")
        print(__doc__)
        sys.exit(1)

if __name__ == '__main__':
    main()
