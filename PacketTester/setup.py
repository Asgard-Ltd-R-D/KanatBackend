#!/usr/bin/env python3
"""
PacketTester Setup Script
Creates venv, installs dependencies, and launches the GUI
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(ROOT, ".venv")
PY = sys.executable

def run(cmd, cwd=None, check=True):
    """Run a command and print it"""
    print(f"$ {' '.join(cmd)}")
    if check:
        subprocess.check_call(cmd, cwd=cwd or ROOT)
    else:
        subprocess.call(cmd, cwd=cwd or ROOT)

def ensure_venv():
    """Create venv if it doesn't exist and return venv python path"""
    if not os.path.exists(VENV_DIR):
        print("Creating virtual environment...")
        run([PY, "-m", "venv", VENV_DIR])
    
    # Return venv python path
    if sys.platform == "win32":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")

def ensure_tk_for_macos():
    """Ensure tkinter is available on macOS"""
    if sys.platform != "darwin":
        return
    
    try:
        import tkinter
        print("✓ tkinter is available")
        return
    except ImportError:
        print("⚠ tkinter not found, attempting to install via Homebrew...")
        try:
            run(["brew", "install", "python-tk@3.13"], check=False)
            print("✓ Installed python-tk via Homebrew")
        except Exception as ex:
            print(f"⚠ Could not auto-install tkinter: {ex}")
            print("  Please run: brew install python-tk@3.13")

def main():
    print("=" * 60)
    print("PacketTester Setup")
    print("=" * 60)
    
    # Ensure tkinter on macOS
    ensure_tk_for_macos()
    
    # Create/use venv
    venv_py = ensure_venv()
    print(f"✓ Using Python: {venv_py}")
    
    # Upgrade pip
    print("\nUpgrading pip...")
    run([venv_py, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "-q"])
    
    # Install requirements
    req = os.path.join(ROOT, "requirements.txt")
    if os.path.exists(req):
        print("\nInstalling dependencies...")
        run([venv_py, "-m", "pip", "install", "-r", req])
    else:
        print("⚠ requirements.txt not found, skipping dependency install")
    
    # Launch GUI
    gui = os.path.join(ROOT, "gui.py")
    print("\n" + "=" * 60)
    print("Launching PacketTester GUI...")
    print("=" * 60 + "\n")
    os.execv(venv_py, [venv_py, gui])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup interrupted by user")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Setup failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n✗ Setup failed: {e}")
        sys.exit(1)
