from __future__ import annotations

def info(message: str) -> None:
    print(f"[INFO] {message}")

def warn(message: str) -> None:
    print(f"[WARN] {message}")

def error(message: str) -> None:
    print(f"[ERROR] {message}")

def success(message: str) -> None:
    print(f"[OK] {message}")

