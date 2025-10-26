#!/usr/bin/env python3
"""
composer.py - Build and run PacketProcessing with Docker Compose
Usage:
    python composer.py up [dev|prod] [-d] [--build]
    python composer.py stop [dev|prod]
    python composer.py kill [dev|prod]
    python composer.py --build [dev|prod]
    python composer.py up --build [dev|prod] [-d]
    
Examples:
    python composer.py up           # Run prod environment
    python composer.py up dev       # Run dev environment
    python composer.py stop dev     # Stop dev environment
    python composer.py kill dev     # Kill dev environment (delete DLL and containers)
    python composer.py --build      # Build prod environment
    python composer.py up dev -d    # Run dev in detached mode
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

def main():
    """Main entry point"""
    args = sys.argv[1:]
    
    if not args or '--help' in args or '-h' in args or (len(args) == 1 and args[0] == 'help'):
        print(__doc__)
        return
    
    # Check prerequisites
    if not check_docker():
        sys.exit(1)
    
    if not check_dotnet():
        sys.exit(1)
    
    # Parse arguments
    command = None
    environment = None
    should_build = False
    detached = False
    
    # Parse arguments
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg in ['dev', 'prod']:
            environment = arg
        elif arg == '--build':
            if command is None:
                command = '--build'
            should_build = True
        elif arg == '-d':
            detached = True
        elif arg in ['up', 'stop', 'kill']:
            command = arg
        elif arg.startswith('-'):
            # Unknown option
            print_error(f"Unknown option: {arg}")
            print(__doc__)
            sys.exit(1)
        
        i += 1
    
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
    
    # Handle up and --build commands
    if command == 'up':
        if environment is None:
            environment = 'prod'  # Default to prod for up
        
        # Check if we need to build
        if not should_build:
            release_path = RELEASE_DIR / environment / "PacketProcessing.dll"
            if not release_path.exists():
                print_warning("DLL not found, building...")
                should_build = True
        
        # Build if needed
        if should_build:
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
        
        if not build_dll(environment):
            sys.exit(1)
    
    else:
        print_error("Unknown command or missing required arguments")
        print(__doc__)
        sys.exit(1)

if __name__ == '__main__':
    main()
