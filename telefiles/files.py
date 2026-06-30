from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


def sanitize_filename(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/"))
    base = _UNSAFE.sub("", base).strip().strip(".")
    return base or "file"


def unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    n = 1
    while True:
        candidate = directory / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def build_zip(root: Path, dest: Path) -> int:
    """Zip every regular file under ``root`` (recursively) into ``dest``, with
    arcnames relative to ``root``. Returns the number of files written.

    Symlinks are never followed: ``os.walk(followlinks=False)`` keeps the walk
    out of symlinked directories, and symlinked files are skipped — so a link
    pointing outside the jail can never leak into the archive.
    """
    count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if path.is_symlink() or not path.is_file():
                    continue
                zf.write(path, path.relative_to(root))
                count += 1
    return count
