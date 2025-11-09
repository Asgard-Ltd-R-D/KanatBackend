from __future__ import annotations

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover
    tqdm = None

class _Task:
    def __init__(self, total: int, desc: str, unit: str):
        self._desc = desc
        self._bar = tqdm(total=total, desc=desc, unit=unit, ncols=80, leave=False) if tqdm else None
        self._done = 0
    def set_description(self, desc: str) -> None:
        self._desc = desc
        if self._bar:
            self._bar.set_description(desc)
    def update(self, n: int = 1) -> None:
        self._done += n
        if self._bar:
            self._bar.update(n)
    def close(self) -> None:
        if self._bar:
            self._bar.close()

class Progress:
    def task(self, total: int, desc: str, unit: str = "") -> _Task:
        return _Task(total, desc, unit)
