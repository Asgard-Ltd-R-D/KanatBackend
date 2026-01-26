from __future__ import annotations
import sys

# ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def _color_supported() -> bool:
    """Check if stdout supports color."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _print_colored(message: str, color_code: str) -> None:
    if _color_supported():
        print(f"{color_code}{message}{RESET}")
    else:
        print(message)

def info(message: str) -> None:
    print(f"[INFO] {message}")

def warn(message: str) -> None:
    print(f"[WARN] {message}")

def error(message: str) -> None:
    print(f"[ERROR] {message}")

def success(message: str) -> None:
    print(f"[OK] {message}")

def print_started(service_name: str) -> None:
    msg = f"[INFO] Started {service_name}"
    # We want "Started" to be green, or the whole message? 
    # User asked: "green 'Started' or 'Stoppoed' on the mediamtx and on the PacketProcessingService"
    # "green for started and red for stopped"
    # Let's make the whole line colored or just the keyword?
    # Usually "Started ServiceName" in green looks good.
    if _color_supported():
        print(f"[INFO] {GREEN}Started{RESET} {service_name}")
    else:
        print(f"[INFO] Started {service_name}")

def print_stopped(service_name: str) -> None:
    if _color_supported():
        print(f"[INFO] {RED}Stopped{RESET} {service_name}")
    else:
        print(f"[INFO] Stopped {service_name}")
