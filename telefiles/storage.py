from __future__ import annotations

import json
import os
from pathlib import Path


def load_allowlist(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {str(k): str(v) for k, v in data.items()}


def save_allowlist(path: Path, allow: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(allow, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)
