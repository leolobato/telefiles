from __future__ import annotations

from dataclasses import dataclass

from telefiles.shares import Shares, ShareError

PAGE_SIZE = 20

CB_UP = "up"
CB_HOME = "home"


@dataclass
class Location:
    share: str | None = None
    relpath: str = ""
    page: int = 0


def list_entries(shares: Shares, loc: Location) -> tuple[list[str], list[str]]:
    if loc.share is None:
        raise ShareError("cannot list entries at the share picker")
    base = shares.resolve(loc.share, loc.relpath)
    dirs: list[str] = []
    files: list[str] = []
    for child in base.iterdir():
        if child.is_dir():
            dirs.append(child.name)
        else:
            files.append(child.name)
    def _key(s):
        return s.lower()
    return sorted(dirs, key=_key), sorted(files, key=_key)


def paginate(items: list, page: int, page_size: int = PAGE_SIZE) -> tuple[list, int, int]:
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start:start + page_size], page, total_pages


def cb_share(name: str) -> str:
    return f"s|{name}"


def cb_dir(index: int) -> str:
    return f"d|{index}"


def cb_file(index: int) -> str:
    return f"f|{index}"


def cb_page(page: int) -> str:
    return f"p|{page}"


def parse_cb(data: str) -> tuple[str, str]:
    if data in (CB_UP, CB_HOME):
        return data, ""
    kind, _, value = data.partition("|")
    return kind, value
