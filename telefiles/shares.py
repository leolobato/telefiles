from __future__ import annotations

from pathlib import Path


class ShareError(Exception):
    """Raised on unknown share, jail escape, or invalid path."""


class Shares:
    def __init__(self, mapping: dict[str, str]) -> None:
        if not mapping:
            raise ShareError("no shares configured")
        self._roots: dict[str, Path] = {}
        for name, path in mapping.items():
            if not name or not name.strip():
                raise ShareError("share name must be non-empty")
            self._roots[name] = Path(path).resolve()

    def names(self) -> list[str]:
        return sorted(self._roots)

    def root(self, share: str) -> Path:
        try:
            return self._roots[share]
        except KeyError:
            raise ShareError(f"unknown share: {share!r}")

    def resolve(self, share: str, relpath: str = "") -> Path:
        root = self.root(share)
        if relpath.startswith("/"):
            raise ShareError("absolute paths are not allowed")
        candidate = (root / relpath).resolve()
        if candidate != root and not candidate.is_relative_to(root):
            raise ShareError("path escapes share root")
        return candidate
