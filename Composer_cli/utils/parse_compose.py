from __future__ import annotations
from pathlib import Path
from typing import List
import re

_IMAGE = re.compile(r"^\s*image:\s*(.+)$")
# Minimal parser used here; expand as needed.

def required_images_from_compose(compose_file: Path) -> List[str]:
    images: list[str] = []
    try:
        lines = compose_file.read_text().splitlines()
        for line in lines:
            m = _IMAGE.match(line)
            if m:
                name = m.group(1).strip().strip("\"'")
                if name and name not in images:
                    images.append(name)
    except Exception:
        pass
    return images