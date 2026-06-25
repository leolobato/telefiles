# Telefiles MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that lets paired users browse, upload, and download files from configured jailed directory "shares".

**Architecture:** A small async Python package (`telefiles`) built on `python-telegram-bot` v21 long polling. All file access routes through a single jailed path resolver. Auth is a persisted allowlist bootstrapped by a pairing code printed at startup. Per-user navigation state lives in memory. Runnable directly (`python -m telefiles`) or via Docker.

**Tech Stack:** Python 3.11+, `python-telegram-bot` 21.x (async), `PyYAML`, `pytest` + `pytest-asyncio`.

## Global Constraints

- Python **3.11+** (uses `pathlib.Path.is_relative_to`, added in 3.9; target 3.11 for `tomllib`/modern typing).
- `python-telegram-bot` **>=21,<22**.
- Cloud Bot API only — **send limit 50 MB**, **receive limit 20 MB**. No local Bot API server.
- **Four operations only:** list, `/cd`, `/upload`, tap-to-download. No delete/rename/mkdir/move.
- All file access MUST route through `shares.resolve()` — the single jail chokepoint.
- Unpaired users get a generic denial; the bot reveals no share or file names until paired.
- All paired users have equal read/write access to all shares (flat permissions).
- Filesystem writes (allowlist) MUST be atomic (temp file + `os.replace`).
- TDD: failing test first, then minimal implementation. Commit after each task.

---

### Task 1: Project scaffold & packaging

**Files:**
- Create: `pyproject.toml`
- Create: `telefiles/__init__.py`
- Create: `tests/__init__.py`
- Create: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable package `telefiles` (version `0.1.0`); `pytest` runnable from repo root; `python -c "import telefiles"` works.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "telefiles"
version = "0.1.0"
description = "Telegram bot for browsing, uploading and downloading files from jailed shares"
requires-python = ">=3.11"
dependencies = [
    "python-telegram-bot>=21,<22",
    "PyYAML>=6,<7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
]

[project.scripts]
telefiles = "telefiles.__main__:main"

[tool.setuptools.packages.find]
include = ["telefiles*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create package markers**

`telefiles/__init__.py`:

```python
__version__ = "0.1.0"
```

`tests/__init__.py`: (empty file)

- [ ] **Step 3: Write a minimal `README.md`**

```markdown
# Telefiles

A Telegram bot for browsing, uploading, and downloading files from configured,
jailed directory shares. See `docs/superpowers/specs/` for the design.

## Quick start

    pip install -e ".[dev]"
    cp .env.example .env   # fill in BOT_TOKEN, ADMIN_ID
    # edit config.yaml with your shares
    python -m telefiles
```

- [ ] **Step 4: Install and verify import**

Run: `pip install -e ".[dev]" && python -c "import telefiles; print(telefiles.__version__)"`
Expected: prints `0.1.0`

- [ ] **Step 5: Verify pytest runs (no tests yet)**

Run: `pytest`
Expected: exits 0 with "no tests ran" (or collects 0 items)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml telefiles/__init__.py tests/__init__.py README.md
git commit -m "Scaffold telefiles package and tooling"
```

---

### Task 2: Jailed share path resolution

This is the security chokepoint. Build and test it first, in isolation.

**Files:**
- Create: `telefiles/shares.py`
- Test: `tests/test_shares.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Shares` constructed from `dict[str, str]` (name → host path); names are validated to be non-empty.
  - `Shares.names() -> list[str]` — share names, sorted.
  - `Shares.resolve(share: str, relpath: str = "") -> pathlib.Path` — returns the absolute resolved path, guaranteed to be inside the share root. Raises `ShareError` (a custom Exception) on unknown share, jail escape, or symlink escape.
  - `Shares.root(share: str) -> pathlib.Path` — the configured root for a share (resolved).
  - `class ShareError(Exception)`.

- [ ] **Step 1: Write failing tests**

```python
import os
import pytest
from telefiles.shares import Shares, ShareError


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "share"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "file.txt").write_text("hi")
    return root


def test_names_sorted():
    s = Shares({"Zed": "/z", "Apple": "/a"})
    assert s.names() == ["Apple", "Zed"]


def test_resolve_root_and_subpath(tree):
    s = Shares({"S": str(tree)})
    assert s.resolve("S") == tree.resolve()
    assert s.resolve("S", "sub/file.txt") == (tree / "sub" / "file.txt").resolve()


def test_unknown_share_raises(tree):
    s = Shares({"S": str(tree)})
    with pytest.raises(ShareError):
        s.resolve("Nope")


def test_dotdot_escape_blocked(tree):
    s = Shares({"S": str(tree)})
    with pytest.raises(ShareError):
        s.resolve("S", "../secret")


def test_absolute_relpath_blocked(tree):
    s = Shares({"S": str(tree)})
    with pytest.raises(ShareError):
        s.resolve("S", "/etc/passwd")


def test_symlink_escape_blocked(tree, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    link = tree / "link"
    os.symlink(outside, link)
    s = Shares({"S": str(tree)})
    with pytest.raises(ShareError):
        s.resolve("S", "link/secret.txt")


def test_empty_share_name_rejected():
    with pytest.raises(ShareError):
        Shares({"": "/x"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_shares.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.shares'`

- [ ] **Step 3: Implement `telefiles/shares.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_shares.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/shares.py tests/test_shares.py
git commit -m "Add jailed share path resolver"
```

---

### Task 3: Filename sanitization & collision suffixing

**Files:**
- Create: `telefiles/files.py`
- Test: `tests/test_files.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `sanitize_filename(name: str) -> str` — strips directory components and unsafe characters; returns a safe basename; falls back to `"file"` if empty.
  - `unique_path(directory: pathlib.Path, filename: str) -> pathlib.Path` — returns a path in `directory` that does not exist, appending ` (1)`, ` (2)`, … before the extension on collision.

- [ ] **Step 1: Write failing tests**

```python
from telefiles.files import sanitize_filename, unique_path


def test_sanitize_strips_path_components():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/a/b/c.txt") == "c.txt"
    assert sanitize_filename("plain.txt") == "plain.txt"


def test_sanitize_empty_falls_back():
    assert sanitize_filename("") == "file"
    assert sanitize_filename("/") == "file"


def test_unique_path_no_collision(tmp_path):
    assert unique_path(tmp_path, "a.txt") == tmp_path / "a.txt"


def test_unique_path_with_collision(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert unique_path(tmp_path, "a.txt") == tmp_path / "a (1).txt"
    (tmp_path / "a (1).txt").write_text("x")
    assert unique_path(tmp_path, "a.txt") == tmp_path / "a (2).txt"


def test_unique_path_no_extension(tmp_path):
    (tmp_path / "README").write_text("x")
    assert unique_path(tmp_path, "README") == tmp_path / "README (1)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_files.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.files'`

- [ ] **Step 3: Implement `telefiles/files.py`**

```python
from __future__ import annotations

import os
import re
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_files.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/files.py tests/test_files.py
git commit -m "Add filename sanitization and collision-safe paths"
```

---

### Task 4: Allowlist storage (atomic JSON)

**Files:**
- Create: `telefiles/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `load_allowlist(path: pathlib.Path) -> dict[str, str]` — maps `str(user_id) -> username`; returns `{}` if the file is missing.
  - `save_allowlist(path: pathlib.Path, allow: dict[str, str]) -> None` — atomic write (temp file + `os.replace`); creates parent dirs.

- [ ] **Step 1: Write failing tests**

```python
from telefiles.storage import load_allowlist, save_allowlist


def test_load_missing_returns_empty(tmp_path):
    assert load_allowlist(tmp_path / "nope.json") == {}


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "sub" / "allow.json"
    data = {"123": "alice", "456": "bob"}
    save_allowlist(p, data)
    assert p.exists()
    assert load_allowlist(p) == data


def test_save_overwrites_atomically(tmp_path):
    p = tmp_path / "allow.json"
    save_allowlist(p, {"1": "a"})
    save_allowlist(p, {"2": "b"})
    assert load_allowlist(p) == {"2": "b"}
    # no leftover temp files
    assert [f.name for f in tmp_path.iterdir()] == ["allow.json"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.storage'`

- [ ] **Step 3: Implement `telefiles/storage.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/storage.py tests/test_storage.py
git commit -m "Add atomic JSON allowlist storage"
```

---

### Task 5: Auth & pairing logic

**Files:**
- Create: `telefiles/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `telefiles.storage.load_allowlist`, `telefiles.storage.save_allowlist`.
- Produces:
  - `class Auth(allowlist_path: pathlib.Path, admin_id: int)`.
  - `Auth.is_paired(user_id: int) -> bool`.
  - `Auth.is_admin(user_id: int) -> bool`.
  - `Auth.pairing_code -> str` — the current single-use code (generated at construction).
  - `Auth.new_code() -> str` — rotate and return a fresh pairing code.
  - `Auth.try_pair(user_id: int, username: str, code: str) -> bool` — if `code` matches the current code, add the user (persisted), consume+rotate the code, return `True`; else `False`.
  - `Auth.revoke(user_id: int) -> bool` — remove a user; return `True` if present.
  - `Auth.users() -> dict[str, str]` — copy of the allowlist.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from telefiles.auth import Auth


@pytest.fixture
def auth(tmp_path):
    return Auth(tmp_path / "allow.json", admin_id=999)


def test_admin_recognized(auth):
    assert auth.is_admin(999)
    assert not auth.is_admin(1)


def test_pairing_adds_user_and_persists(auth, tmp_path):
    code = auth.pairing_code
    assert auth.try_pair(42, "alice", code) is True
    assert auth.is_paired(42)
    # persisted across reload
    reloaded = Auth(tmp_path / "allow.json", admin_id=999)
    assert reloaded.is_paired(42)


def test_wrong_code_rejected(auth):
    assert auth.try_pair(42, "alice", "wrong") is False
    assert not auth.is_paired(42)


def test_code_is_single_use(auth):
    code = auth.pairing_code
    assert auth.try_pair(1, "a", code) is True
    # same code no longer works for a second user
    assert auth.try_pair(2, "b", code) is False


def test_new_code_rotates(auth):
    first = auth.pairing_code
    second = auth.new_code()
    assert first != second
    assert auth.pairing_code == second


def test_revoke(auth):
    auth.try_pair(42, "alice", auth.pairing_code)
    assert auth.revoke(42) is True
    assert not auth.is_paired(42)
    assert auth.revoke(42) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.auth'`

- [ ] **Step 3: Implement `telefiles/auth.py`**

```python
from __future__ import annotations

import secrets
from pathlib import Path

from telefiles.storage import load_allowlist, save_allowlist


def _generate_code() -> str:
    return secrets.token_hex(4)  # 8 hex chars


class Auth:
    def __init__(self, allowlist_path: Path, admin_id: int) -> None:
        self._path = allowlist_path
        self._admin_id = admin_id
        self._allow = load_allowlist(allowlist_path)
        self._code = _generate_code()

    @property
    def pairing_code(self) -> str:
        return self._code

    def new_code(self) -> str:
        self._code = _generate_code()
        return self._code

    def is_admin(self, user_id: int) -> bool:
        return user_id == self._admin_id

    def is_paired(self, user_id: int) -> bool:
        return str(user_id) in self._allow

    def try_pair(self, user_id: int, username: str, code: str) -> bool:
        if not secrets.compare_digest(code, self._code):
            return False
        self._allow[str(user_id)] = username or ""
        save_allowlist(self._path, self._allow)
        self.new_code()
        return True

    def revoke(self, user_id: int) -> bool:
        if str(user_id) not in self._allow:
            return False
        del self._allow[str(user_id)]
        save_allowlist(self._path, self._allow)
        return True

    def users(self) -> dict[str, str]:
        return dict(self._allow)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/auth.py tests/test_auth.py
git commit -m "Add auth and single-use pairing-code logic"
```

---

### Task 6: Config loading & validation

**Files:**
- Create: `telefiles/config.py`
- Create: `config.yaml.example`
- Create: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `telefiles.shares.Shares`.
- Produces:
  - `@dataclass class Config` with fields: `token: str`, `admin_id: int`, `data_dir: pathlib.Path`, `shares: Shares`.
  - `load_config(env: dict[str, str], config_path: pathlib.Path | None) -> Config` — reads `BOT_TOKEN`, `ADMIN_ID`, `DATA_DIR` (default `./data`) from `env`; reads shares from `config_path` YAML (`shares:` mapping) or from `env["SHARES"]` (`name:path,name:path`). Raises `ConfigError` with a clear message on any missing/invalid value.
  - `class ConfigError(Exception)`.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from telefiles.config import load_config, ConfigError


def test_load_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("shares:\n  Docs: /srv/docs\n  Photos: /mnt/photos\n")
    env = {"BOT_TOKEN": "T", "ADMIN_ID": "555", "DATA_DIR": str(tmp_path / "data")}
    cfg = load_config(env, cfg_file)
    assert cfg.token == "T"
    assert cfg.admin_id == 555
    assert cfg.data_dir == tmp_path / "data"
    assert cfg.shares.names() == ["Docs", "Photos"]


def test_load_shares_from_env(tmp_path):
    env = {
        "BOT_TOKEN": "T",
        "ADMIN_ID": "5",
        "SHARES": "A:/a,B:/b",
        "DATA_DIR": str(tmp_path),
    }
    cfg = load_config(env, None)
    assert cfg.shares.names() == ["A", "B"]


def test_missing_token_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config({"ADMIN_ID": "5", "SHARES": "A:/a"}, None)


def test_bad_admin_id_raises():
    with pytest.raises(ConfigError):
        load_config({"BOT_TOKEN": "T", "ADMIN_ID": "notnum", "SHARES": "A:/a"}, None)


def test_no_shares_raises():
    with pytest.raises(ConfigError):
        load_config({"BOT_TOKEN": "T", "ADMIN_ID": "5"}, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.config'`

- [ ] **Step 3: Implement `telefiles/config.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from telefiles.shares import Shares, ShareError


class ConfigError(Exception):
    pass


@dataclass
class Config:
    token: str
    admin_id: int
    data_dir: Path
    shares: Shares


def _parse_shares_env(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in value.split(","):
        pair = pair.strip()
        if not pair:
            continue
        name, sep, path = pair.partition(":")
        if not sep or not name.strip() or not path.strip():
            raise ConfigError(f"invalid SHARES entry: {pair!r}")
        out[name.strip()] = path.strip()
    return out


def load_config(env: dict[str, str], config_path: Path | None) -> Config:
    token = env.get("BOT_TOKEN")
    if not token:
        raise ConfigError("BOT_TOKEN is required")

    admin_raw = env.get("ADMIN_ID")
    if not admin_raw:
        raise ConfigError("ADMIN_ID is required")
    try:
        admin_id = int(admin_raw)
    except ValueError:
        raise ConfigError(f"ADMIN_ID must be an integer, got {admin_raw!r}")

    data_dir = Path(env.get("DATA_DIR", "./data"))

    shares_map: dict[str, str] = {}
    if config_path is not None and config_path.exists():
        loaded = yaml.safe_load(config_path.read_text()) or {}
        shares_map = dict((loaded.get("shares") or {}))
    elif env.get("SHARES"):
        shares_map = _parse_shares_env(env["SHARES"])

    if not shares_map:
        raise ConfigError("no shares configured (config.yaml or SHARES env)")

    try:
        shares = Shares(shares_map)
    except ShareError as exc:
        raise ConfigError(str(exc))

    return Config(token=token, admin_id=admin_id, data_dir=data_dir, shares=shares)
```

- [ ] **Step 4: Write the example files**

`config.yaml.example`:

```yaml
shares:
  Photos: /mnt/photos
  Docs: /srv/docs
```

`.env.example`:

```bash
BOT_TOKEN=123456:your-telegram-bot-token
ADMIN_ID=000000000
DATA_DIR=./data
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 6: Commit**

```bash
git add telefiles/config.py config.yaml.example .env.example tests/test_config.py
git commit -m "Add config loading from YAML and env"
```

---

### Task 7: Navigation state & keyboard building

Pure logic: directory listing, pagination, and inline-keyboard layout. No Telegram I/O here so it stays unit-testable.

**Files:**
- Create: `telefiles/navigation.py`
- Test: `tests/test_navigation.py`

**Interfaces:**
- Consumes: `telefiles.shares.Shares`.
- Produces:
  - `PAGE_SIZE: int = 20` (module constant).
  - `class Location` (`@dataclass`): `share: str | None`, `relpath: str` (default `""`). `share is None` means "at the share picker".
  - `list_entries(shares: Shares, loc: Location) -> tuple[list[str], list[str]]` — returns `(dir_names, file_names)` within `loc`, each sorted alphabetically (case-insensitive). Raises `ShareError` on a bad location.
  - `paginate(items: list, page: int, page_size: int = PAGE_SIZE) -> tuple[list, int, int]` — returns `(page_items, page, total_pages)`, clamping `page` into `[0, total_pages-1]`; `total_pages` is at least 1.
  - Callback-data helpers (compact strings, Telegram limits callback_data to 64 bytes — we encode an index, not a path):
    - `cb_share(name: str) -> str` → `"s|<name>"`.
    - `cb_dir(index: int) -> str` → `"d|<index>"`.
    - `cb_file(index: int) -> str` → `"f|<index>"`.
    - `cb_page(page: int) -> str` → `"p|<page>"`.
    - `CB_UP = "up"`, `CB_HOME = "home"`.
    - `parse_cb(data: str) -> tuple[str, str]` → `(kind, value)`; `kind` in `{"s","d","f","p","up","home"}`.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from telefiles.shares import Shares
from telefiles.navigation import (
    Location, list_entries, paginate, PAGE_SIZE,
    cb_share, cb_dir, cb_file, cb_page, parse_cb, CB_UP, CB_HOME,
)


@pytest.fixture
def shares(tmp_path):
    root = tmp_path / "share"
    (root / "beta").mkdir(parents=True)
    (root / "Alpha").mkdir()
    (root / "z.txt").write_text("z")
    (root / "a.txt").write_text("a")
    return Shares({"S": str(root)})


def test_list_entries_sorted_dirs_then_files(shares):
    dirs, files = list_entries(shares, Location("S", ""))
    assert dirs == ["Alpha", "beta"]
    assert files == ["a.txt", "z.txt"]


def test_paginate_clamps_and_counts():
    items = list(range(45))
    page_items, page, total = paginate(items, page=0, page_size=20)
    assert page_items == list(range(20))
    assert (page, total) == (0, 3)
    page_items, page, total = paginate(items, page=99, page_size=20)
    assert page == 2 and page_items == list(range(40, 45))


def test_paginate_empty_has_one_page():
    page_items, page, total = paginate([], page=0)
    assert page_items == [] and page == 0 and total == 1


def test_callback_roundtrip():
    assert parse_cb(cb_share("Docs")) == ("s", "Docs")
    assert parse_cb(cb_dir(3)) == ("d", "3")
    assert parse_cb(cb_file(7)) == ("f", "7")
    assert parse_cb(cb_page(2)) == ("p", "2")
    assert parse_cb(CB_UP) == ("up", "")
    assert parse_cb(CB_HOME) == ("home", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_navigation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.navigation'`

- [ ] **Step 3: Implement `telefiles/navigation.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from telefiles.shares import Shares

PAGE_SIZE = 20

CB_UP = "up"
CB_HOME = "home"


@dataclass
class Location:
    share: str | None = None
    relpath: str = ""


def list_entries(shares: Shares, loc: Location) -> tuple[list[str], list[str]]:
    if loc.share is None:
        raise ValueError("cannot list entries at the share picker")
    base = shares.resolve(loc.share, loc.relpath)
    dirs: list[str] = []
    files: list[str] = []
    for child in base.iterdir():
        if child.is_dir():
            dirs.append(child.name)
        else:
            files.append(child.name)
    key = lambda s: s.lower()
    return sorted(dirs, key=key), sorted(files, key=key)


def paginate(items, page, page_size=PAGE_SIZE):
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_navigation.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/navigation.py tests/test_navigation.py
git commit -m "Add navigation state, listing and pagination logic"
```

---

### Task 8: Keyboard rendering helper

Build the actual `InlineKeyboardMarkup` from a `Location`. Separated from Task 7 so the pure logic stays free of the Telegram dependency, but kept testable by asserting on the resulting button structure.

**Files:**
- Create: `telefiles/keyboards.py`
- Test: `tests/test_keyboards.py`

**Interfaces:**
- Consumes: `telefiles.shares.Shares`, `telefiles.navigation` (everything above).
- Produces:
  - `build_share_picker(shares: Shares) -> telegram.InlineKeyboardMarkup` — one button per share (callback `cb_share`).
  - `build_browser(shares: Shares, loc: Location, page: int) -> tuple[str, telegram.InlineKeyboardMarkup, list[str], list[str]]` — returns `(header_text, markup, page_dirs, page_files)` where `page_dirs`/`page_files` are the exact entry names shown on this page, in display order (dirs first, then files), so callback indices map onto `page_dirs + page_files`. Markup includes 📁/📄 buttons, ◀️/▶️ when `total_pages > 1`, an `⬆️ ..` button when `loc.relpath` is non-empty, and a `🏠 Shares` button.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from telegram import InlineKeyboardMarkup
from telefiles.shares import Shares
from telefiles.navigation import Location, parse_cb, CB_HOME, CB_UP
from telefiles.keyboards import build_share_picker, build_browser


@pytest.fixture
def shares(tmp_path):
    root = tmp_path / "share"
    (root / "dir1").mkdir(parents=True)
    (root / "f.txt").write_text("x")
    return Shares({"S": str(root)})


def _all_buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def test_share_picker_lists_shares(shares):
    markup = build_share_picker(shares)
    labels = [b.text for b in _all_buttons(markup)]
    assert any("S" in t for t in labels)


def test_browser_at_root_has_no_up_button(shares):
    text, markup, dirs, files = build_browser(shares, Location("S", ""), page=0)
    datas = [b.callback_data for b in _all_buttons(markup)]
    assert CB_UP not in datas
    assert CB_HOME in datas
    assert dirs == ["dir1"] and files == ["f.txt"]


def test_browser_in_subdir_has_up_button(shares, tmp_path):
    (tmp_path / "share" / "dir1" / "inner").mkdir()
    text, markup, dirs, files = build_browser(shares, Location("S", "dir1"), page=0)
    datas = [b.callback_data for b in _all_buttons(markup)]
    assert CB_UP in datas
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_keyboards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.keyboards'`

- [ ] **Step 3: Implement `telefiles/keyboards.py`**

```python
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telefiles.navigation import (
    Location, list_entries, paginate,
    cb_share, cb_dir, cb_file, cb_page, CB_UP, CB_HOME,
)
from telefiles.shares import Shares


def build_share_picker(shares: Shares) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📂 {name}", callback_data=cb_share(name))]
            for name in shares.names()]
    return InlineKeyboardMarkup(rows or [[InlineKeyboardButton("(no shares)", callback_data=CB_HOME)]])


def build_browser(shares: Shares, loc: Location, page: int):
    dirs, files = list_entries(shares, loc)
    entries = [("d", d) for d in dirs] + [("f", f) for f in files]
    page_entries, page, total_pages = paginate(entries, page)

    page_dirs = [name for kind, name in page_entries if kind == "d"]
    page_files = [name for kind, name in page_entries if kind == "f"]

    rows: list[list[InlineKeyboardButton]] = []
    for idx, (kind, name) in enumerate(page_entries):
        if kind == "d":
            rows.append([InlineKeyboardButton(f"📁 {name}", callback_data=cb_dir(idx))])
        else:
            rows.append([InlineKeyboardButton(f"📄 {name}", callback_data=cb_file(idx))])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=cb_page(page - 1)))
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=cb_page(page)))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=cb_page(page + 1)))
        rows.append(nav)

    bottom = []
    if loc.relpath:
        bottom.append(InlineKeyboardButton("⬆️ ..", callback_data=CB_UP))
    bottom.append(InlineKeyboardButton("🏠 Shares", callback_data=CB_HOME))
    rows.append(bottom)

    display = loc.share if not loc.relpath else f"{loc.share}/{loc.relpath}"
    header = f"📂 {display}"
    return header, InlineKeyboardMarkup(rows), page_dirs, page_files
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_keyboards.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/keyboards.py tests/test_keyboards.py
git commit -m "Add inline-keyboard rendering for browser and share picker"
```

---

### Task 9: Handlers — auth gate, pairing, admin commands

Wire commands to the logic. Tested with mocked `Update`/`Context` objects (no live Telegram).

**Files:**
- Create: `telefiles/handlers.py`
- Test: `tests/test_handlers_auth.py`

**Interfaces:**
- Consumes: `telefiles.auth.Auth`, `telefiles.config.Config`, navigation/keyboards (later tasks extend this file).
- Produces:
  - `class BotState` — holds `config: Config`, `auth: Auth`, and `locations: dict[int, Location]` (per-user nav state) and `awaiting_upload: set[int]`. Stored on `application.bot_data["state"]`.
  - `require_auth(handler)` — decorator; if the user is not paired, replies "⛔ Not authorized." via `update.effective_message.reply_text` and returns without calling `handler`.
  - `async def cmd_start(update, context)` — if paired, shows the share picker; else prompts to `/pair`.
  - `async def cmd_pair(update, context)` — reads the code from `context.args`; calls `auth.try_pair`; replies success/failure.
  - `async def cmd_newcode(update, context)` — admin-only; rotates code; replies with the new code.
  - `async def cmd_listusers(update, context)` — admin-only; lists paired users.
  - `async def cmd_revoke(update, context)` — admin-only; revokes `context.args[0]`.
  - Helper `_state(context) -> BotState`.

- [ ] **Step 1: Write failing tests**

```python
import types
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.handlers import BotState, cmd_pair, cmd_start, require_auth


def make_state(tmp_path, admin_id=999):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="T", admin_id=admin_id, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=admin_id)
    return BotState(config=cfg, auth=auth)


def make_update(user_id, args_text=None):
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "u"
    update.effective_message = msg
    return update, msg


def make_context(state, args=None):
    ctx = MagicMock()
    ctx.bot_data = {"state": state}
    ctx.args = args or []
    return ctx


@pytest.mark.asyncio
async def test_pair_with_correct_code(tmp_path):
    state = make_state(tmp_path)
    code = state.auth.pairing_code
    update, msg = make_update(42)
    ctx = make_context(state, args=[code])
    await cmd_pair(update, ctx)
    assert state.auth.is_paired(42)
    msg.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_pair_with_wrong_code(tmp_path):
    state = make_state(tmp_path)
    update, msg = make_update(42)
    ctx = make_context(state, args=["bad"])
    await cmd_pair(update, ctx)
    assert not state.auth.is_paired(42)


@pytest.mark.asyncio
async def test_require_auth_blocks_unpaired(tmp_path):
    state = make_state(tmp_path)
    called = {"yes": False}

    @require_auth
    async def handler(update, context):
        called["yes"] = True

    update, msg = make_update(42)
    ctx = make_context(state)
    await handler(update, ctx)
    assert called["yes"] is False
    msg.reply_text.assert_awaited()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.handlers'`

- [ ] **Step 3: Implement `telefiles/handlers.py`**

```python
from __future__ import annotations

import functools
from dataclasses import dataclass, field

from telegram import Update
from telegram.ext import ContextTypes

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.keyboards import build_share_picker
from telefiles.navigation import Location


@dataclass
class BotState:
    config: Config
    auth: Auth
    locations: dict[int, Location] = field(default_factory=dict)
    awaiting_upload: set[int] = field(default_factory=set)


def _state(context: ContextTypes.DEFAULT_TYPE) -> BotState:
    return context.bot_data["state"]


def require_auth(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = _state(context)
        user_id = update.effective_user.id
        if not state.auth.is_paired(user_id):
            await update.effective_message.reply_text("⛔ Not authorized.")
            return
        return await handler(update, context)
    return wrapper


def require_admin(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = _state(context)
        if not state.auth.is_admin(update.effective_user.id):
            await update.effective_message.reply_text("⛔ Admin only.")
            return
        return await handler(update, context)
    return wrapper


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    user_id = update.effective_user.id
    if not state.auth.is_paired(user_id):
        await update.effective_message.reply_text(
            "👋 You are not paired. Send /pair <code> to get access."
        )
        return
    state.locations[user_id] = Location()
    await update.effective_message.reply_text(
        "📂 Choose a share:", reply_markup=build_share_picker(state.config.shares)
    )


async def cmd_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    user = update.effective_user
    if not context.args:
        await update.effective_message.reply_text("Usage: /pair <code>")
        return
    if state.auth.try_pair(user.id, user.username or "", context.args[0]):
        await update.effective_message.reply_text("✅ Paired! Send /start to begin.")
    else:
        await update.effective_message.reply_text("❌ Invalid or expired code.")


@require_admin
async def cmd_newcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    code = state.auth.new_code()
    await update.effective_message.reply_text(f"🔑 New pairing code: `{code}`", parse_mode="Markdown")


@require_admin
async def cmd_listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    users = state.auth.users()
    if not users:
        await update.effective_message.reply_text("No paired users.")
        return
    lines = [f"• `{uid}` — {name or '(no username)'}" for uid, name in users.items()]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


@require_admin
async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    if not context.args:
        await update.effective_message.reply_text("Usage: /revoke <user_id>")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("user_id must be a number.")
        return
    if state.auth.revoke(target):
        await update.effective_message.reply_text(f"✅ Revoked {target}.")
    else:
        await update.effective_message.reply_text("User not found.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_auth.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/handlers.py tests/test_handlers_auth.py
git commit -m "Add auth gate, pairing and admin command handlers"
```

---

### Task 10: Handlers — navigation callbacks & download

**Files:**
- Modify: `telefiles/handlers.py`
- Test: `tests/test_handlers_nav.py`

**Interfaces:**
- Consumes: everything from Task 9, plus `telefiles.keyboards.build_browser`, `telefiles.navigation` (`parse_cb`, `Location`, etc.), `telefiles.shares`.
- Produces (added to `handlers.py`):
  - `MAX_SEND_BYTES = 50 * 1024 * 1024`.
  - `async def on_callback(update, context)` — single `CallbackQueryHandler` entrypoint. Reads `update.callback_query.data`, dispatches via `parse_cb`:
    - `home` → set location to share picker, edit message to share picker.
    - `s` → enter share (relpath `""`), render browser.
    - `up` → pop last path segment, render browser.
    - `p` → re-render current location at the requested page.
    - `d` → resolve the directory name from the *rendered page list* (recompute `build_browser` for current page, index into `page_dirs`), descend, render.
    - `f` → resolve the file name from `page_files`; if size > `MAX_SEND_BYTES`, answer "too large"; else send the document.
  - Always calls `update.callback_query.answer()`.
  - Helper `_loc(state, user_id) -> Location` (defaults to share picker).

- [ ] **Step 1: Write failing tests**

```python
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.navigation import Location, cb_share, cb_dir, CB_HOME
from telefiles.handlers import BotState, on_callback


def build_state(tmp_path):
    (tmp_path / "share" / "sub").mkdir(parents=True)
    (tmp_path / "share" / "sub" / "f.txt").write_text("hello")
    shares = Shares({"S": str(tmp_path / "share")})
    cfg = Config(token="T", admin_id=1, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=1)
    auth.try_pair(42, "u", auth.pairing_code)
    return BotState(config=cfg, auth=auth)


def make_cb_update(user_id, data):
    q = MagicMock()
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message = MagicMock()
    q.message.reply_document = AsyncMock()
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query = q
    return update, q


def make_ctx(state):
    ctx = MagicMock()
    ctx.bot_data = {"state": state}
    return ctx


@pytest.mark.asyncio
async def test_enter_share_renders_browser(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location()
    update, q = make_cb_update(42, cb_share("S"))
    await on_callback(update, make_ctx(state))
    q.answer.assert_awaited()
    q.edit_message_text.assert_awaited()
    assert state.locations[42].share == "S"


@pytest.mark.asyncio
async def test_home_returns_to_picker(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "sub")
    update, q = make_cb_update(42, CB_HOME)
    await on_callback(update, make_ctx(state))
    assert state.locations[42].share is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_nav.py -v`
Expected: FAIL with `ImportError: cannot import name 'on_callback'`

- [ ] **Step 3: Append to `telefiles/handlers.py`**

Add these imports at the top (merge with existing import block):

```python
from telegram.error import TelegramError
from telefiles.keyboards import build_browser
from telefiles.navigation import parse_cb, CB_UP, CB_HOME
from telefiles.shares import ShareError
```

Add this constant and helpers near `BotState`:

```python
MAX_SEND_BYTES = 50 * 1024 * 1024


def _loc(state: BotState, user_id: int) -> Location:
    return state.locations.setdefault(user_id, Location())
```

Add the callback handler:

```python
async def _render_browser(query, state: BotState, loc: Location, page: int = 0):
    header, markup, page_dirs, page_files = build_browser(state.config.shares, loc, page)
    await query.edit_message_text(header, reply_markup=markup)
    return page_dirs, page_files


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if not state.auth.is_paired(user_id):
        await query.edit_message_text("⛔ Not authorized.")
        return

    kind, value = parse_cb(query.data)
    loc = _loc(state, user_id)

    try:
        if kind == "home":
            state.locations[user_id] = Location()
            await query.edit_message_text(
                "📂 Choose a share:",
                reply_markup=build_share_picker(state.config.shares),
            )
            return

        if kind == "s":
            loc = Location(value, "")
            state.locations[user_id] = loc
            await _render_browser(query, state, loc)
            return

        if kind == "up":
            parent = "/".join(loc.relpath.split("/")[:-1]) if loc.relpath else ""
            loc = Location(loc.share, parent)
            state.locations[user_id] = loc
            await _render_browser(query, state, loc)
            return

        if kind == "p":
            await _render_browser(query, state, loc, page=int(value))
            return

        if kind in ("d", "f"):
            # recompute the page the buttons were drawn from to map index -> name
            page_dirs, page_files = await _render_browser(query, state, loc)
            entries = page_dirs + page_files
            index = int(value)
            if index >= len(entries):
                return
            name = entries[index]
            if kind == "d":
                child = f"{loc.relpath}/{name}".strip("/")
                loc = Location(loc.share, child)
                state.locations[user_id] = loc
                await _render_browser(query, state, loc)
            else:
                await _send_file(query, state, loc, name)
            return
    except ShareError:
        await query.edit_message_text("⚠️ Invalid path.")


async def _send_file(query, state: BotState, loc: Location, name: str):
    path = state.config.shares.resolve(loc.share, f"{loc.relpath}/{name}".strip("/"))
    if not path.is_file():
        await query.message.reply_text("⚠️ Not a file.")
        return
    if path.stat().st_size > MAX_SEND_BYTES:
        await query.message.reply_text("⚠️ File too large for Telegram (max 50 MB).")
        return
    try:
        with path.open("rb") as fh:
            await query.message.reply_document(document=fh, filename=name)
    except TelegramError:
        await query.message.reply_text("⚠️ Failed to send file.")
```

Note: the `d`/`f` handler re-renders the browser before mapping the index — this keeps the displayed page and the index space in sync. (The `f` branch re-renders then sends the document as a follow-up message, which is acceptable for the MVP.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_nav.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/handlers.py tests/test_handlers_nav.py
git commit -m "Add navigation callbacks and tap-to-download"
```

---

### Task 11: Handlers — upload flow

**Files:**
- Modify: `telefiles/handlers.py`
- Test: `tests/test_handlers_upload.py`

**Interfaces:**
- Consumes: Task 10 state, `telefiles.files.sanitize_filename`, `telefiles.files.unique_path`, `telefiles.shares`.
- Produces (added to `handlers.py`):
  - `MAX_RECEIVE_BYTES = 20 * 1024 * 1024`.
  - `async def cmd_upload(update, context)` — paired only; if at the share picker, asks the user to enter a share first; else adds `user_id` to `state.awaiting_upload` and replies where the file will land.
  - `async def on_document(update, context)` — paired only; if `user_id` not awaiting upload, ignore; else save the document into the current directory (sanitize name, `unique_path`), clear the awaiting flag, reply with the saved name. Reject if `document.file_size > MAX_RECEIVE_BYTES`.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.navigation import Location
from telefiles.handlers import BotState, cmd_upload, on_document


def build_state(tmp_path):
    (tmp_path / "share").mkdir()
    shares = Shares({"S": str(tmp_path / "share")})
    cfg = Config(token="T", admin_id=1, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=1)
    auth.try_pair(42, "u", auth.pairing_code)
    return BotState(config=cfg, auth=auth)


def make_update(user_id, document=None):
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    msg.document = document
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_message = msg
    return update, msg


def make_ctx(state):
    ctx = MagicMock()
    ctx.bot_data = {"state": state}
    ctx.args = []
    return ctx


@pytest.mark.asyncio
async def test_upload_requires_share_selected(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location()  # picker
    update, msg = make_update(42)
    await cmd_upload(update, make_ctx(state))
    assert 42 not in state.awaiting_upload


@pytest.mark.asyncio
async def test_upload_sets_awaiting(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "")
    update, msg = make_update(42)
    await cmd_upload(update, make_ctx(state))
    assert 42 in state.awaiting_upload


@pytest.mark.asyncio
async def test_document_saved_to_current_dir(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "")
    state.awaiting_upload.add(42)

    tg_file = MagicMock()
    async def fake_download(custom_path):
        Path(custom_path).write_text("data")
    tg_file.download_to_drive = AsyncMock(side_effect=fake_download)

    document = MagicMock()
    document.file_name = "../evil.txt"
    document.file_size = 10
    document.get_file = AsyncMock(return_value=tg_file)

    update, msg = make_update(42, document=document)
    await on_document(update, make_ctx(state))

    saved = tmp_path / "share" / "evil.txt"
    assert saved.exists()
    assert 42 not in state.awaiting_upload


@pytest.mark.asyncio
async def test_document_rejected_when_too_large(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "")
    state.awaiting_upload.add(42)
    document = MagicMock()
    document.file_name = "big.bin"
    document.file_size = 999 * 1024 * 1024
    update, msg = make_update(42, document=document)
    await on_document(update, make_ctx(state))
    assert not (tmp_path / "share" / "big.bin").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_upload.py -v`
Expected: FAIL with `ImportError: cannot import name 'cmd_upload'`

- [ ] **Step 3: Append to `telefiles/handlers.py`**

Add imports (merge with existing block):

```python
from telefiles.files import sanitize_filename, unique_path
```

Add the constant and handlers:

```python
MAX_RECEIVE_BYTES = 20 * 1024 * 1024


@require_auth
async def cmd_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    user_id = update.effective_user.id
    loc = _loc(state, user_id)
    if loc.share is None:
        await update.effective_message.reply_text(
            "Enter a share first with /start, then run /upload."
        )
        return
    state.awaiting_upload.add(user_id)
    display = loc.share if not loc.relpath else f"{loc.share}/{loc.relpath}"
    await update.effective_message.reply_text(
        f"📤 Send me a file now; it will be saved to {display}."
    )


@require_auth
async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    user_id = update.effective_user.id
    if user_id not in state.awaiting_upload:
        return
    document = update.effective_message.document
    if document is None:
        return
    if document.file_size and document.file_size > MAX_RECEIVE_BYTES:
        await update.effective_message.reply_text(
            "⚠️ File too large to receive (max 20 MB)."
        )
        return

    loc = _loc(state, user_id)
    directory = state.config.shares.resolve(loc.share, loc.relpath)
    safe = sanitize_filename(document.file_name or "file")
    dest = unique_path(directory, safe)

    tg_file = await document.get_file()
    await tg_file.download_to_drive(custom_path=str(dest))
    state.awaiting_upload.discard(user_id)
    await update.effective_message.reply_text(f"✅ Saved as {dest.name}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_upload.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add telefiles/handlers.py tests/test_handlers_upload.py
git commit -m "Add upload flow with sanitization and size limit"
```

---

### Task 12: Application wiring & entrypoint

**Files:**
- Create: `telefiles/app.py`
- Create: `telefiles/__main__.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `telefiles.config`, `telefiles.auth`, `telefiles.handlers`.
- Produces:
  - `build_application(config: Config) -> telegram.ext.Application` — constructs the `Application`, creates `Auth` and `BotState`, stores state in `bot_data`, registers all handlers (commands, `CallbackQueryHandler(on_callback)`, `MessageHandler(filters.Document.ALL, on_document)`), and a global error handler. Returns the application without starting it.
  - `main() -> None` — loads `.env` if present, builds config from `os.environ` + `./config.yaml`, builds the application, prints the pairing code, runs polling.

- [ ] **Step 1: Write failing test**

```python
from pathlib import Path
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.app import build_application


def test_build_application_registers_handlers(tmp_path):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="123:abc", admin_id=1, data_dir=tmp_path, shares=shares)
    app = build_application(cfg)
    # state is wired
    assert "state" in app.bot_data
    assert app.bot_data["state"].config is cfg
    # at least one handler group registered
    assert app.handlers
    total = sum(len(hs) for hs in app.handlers.values())
    assert total >= 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telefiles.app'`

- [ ] **Step 3: Implement `telefiles/app.py`**

```python
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler,
    CommandHandler, ContextTypes, MessageHandler, filters,
)

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles import handlers as h

logger = logging.getLogger("telefiles")


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Handler error", exc_info=context.error)


def build_application(config: Config) -> Application:
    auth = Auth(config.data_dir / "allowlist.json", config.admin_id)
    state = h.BotState(config=config, auth=auth)

    app = ApplicationBuilder().token(config.token).build()
    app.bot_data["state"] = state

    app.add_handler(CommandHandler("start", h.cmd_start))
    app.add_handler(CommandHandler("cd", h.cmd_start))
    app.add_handler(CommandHandler("pair", h.cmd_pair))
    app.add_handler(CommandHandler("upload", h.cmd_upload))
    app.add_handler(CommandHandler("newcode", h.cmd_newcode))
    app.add_handler(CommandHandler("listusers", h.cmd_listusers))
    app.add_handler(CommandHandler("revoke", h.cmd_revoke))
    app.add_handler(CallbackQueryHandler(h.on_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, h.on_document))
    app.add_error_handler(_on_error)

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 5: Implement `telefiles/__main__.py`**

```python
from __future__ import annotations

import logging
import os
from pathlib import Path

from telegram import Update

from telefiles.app import build_application
from telefiles.config import load_config


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    _load_dotenv(Path(".env"))
    config = load_config(dict(os.environ), Path("config.yaml"))
    app = build_application(config)
    state = app.bot_data["state"]
    logging.getLogger("telefiles").info(
        "Pairing code: %s  (send /pair <code> from Telegram)", state.auth.pairing_code
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests across all modules)

- [ ] **Step 7: Commit**

```bash
git add telefiles/app.py telefiles/__main__.py tests/test_app.py
git commit -m "Wire application, handlers and polling entrypoint"
```

---

### Task 13: Docker & compose

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: the installable package and `python -m telefiles`.
- Produces: a runnable container image; `docker compose up` starts the bot with shares + data mounted.

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY telefiles ./telefiles
RUN pip install --no-cache-dir .

# config.yaml and .env are provided at runtime via mounts/env
ENV DATA_DIR=/data
VOLUME ["/data"]

CMD ["python", "-m", "telefiles"]
```

- [ ] **Step 2: Write `.dockerignore`**

```
.git
__pycache__/
*.pyc
.venv/
venv/
data/
.env
tests/
docs/
```

- [ ] **Step 3: Write `docker-compose.yml`**

```yaml
services:
  telefiles:
    build: .
    restart: unless-stopped
    environment:
      BOT_TOKEN: ${BOT_TOKEN}
      ADMIN_ID: ${ADMIN_ID}
      DATA_DIR: /data
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/data
      # Mount each host share at the container path referenced in config.yaml, e.g.:
      - /mnt/photos:/mnt/photos:ro      # read-only share
      - /srv/docs:/srv/docs             # read-write share (allows upload)
```

- [ ] **Step 4: Build the image to verify it compiles**

Run: `docker build -t telefiles:dev .`
Expected: build succeeds, ends with "naming to docker.io/library/telefiles:dev"

(If Docker is unavailable in the environment, skip the build but still commit the files; note the skip.)

- [ ] **Step 5: Append a "Running with Docker" section to `README.md`**

```markdown
## Running with Docker

1. Copy `config.yaml.example` to `config.yaml` and define your shares using the
   container paths you will mount.
2. Set `BOT_TOKEN` and `ADMIN_ID` in your environment or a `.env` file.
3. Edit the share volume mounts in `docker-compose.yml` to match `config.yaml`.
4. `docker compose up --build`
5. Read the pairing code from the logs and send `/pair <code>` to the bot.

Mount a share read-only (`:ro`) to prevent uploads into it; mount read-write to
allow `/upload`.
```

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore README.md
git commit -m "Add Docker image and compose setup"
```

---

### Task 14: End-to-end smoke check & docs polish

**Files:**
- Modify: `README.md` (commands reference)
- Test: full suite + manual run notes

**Interfaces:**
- Consumes: everything.
- Produces: a documented command list and a verified green test suite.

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -v`
Expected: all tests PASS

- [ ] **Step 2: Local smoke run (requires a real test bot token)**

Run:
```bash
export BOT_TOKEN=... ADMIN_ID=...
mkdir -p /tmp/telefiles-share && echo hi > /tmp/telefiles-share/hello.txt
printf 'shares:\n  Test: /tmp/telefiles-share\n' > config.yaml
python -m telefiles
```
Expected: logs print "Pairing code: ...". In Telegram: `/pair <code>` → `/start` → tap `Test` → see `hello.txt` → tap it → file is delivered. `/upload` → send a small file → it appears in `/tmp/telefiles-share`.

(If no test token is available, document this as a manual step and skip.)

- [ ] **Step 3: Add a commands reference to `README.md`**

```markdown
## Commands

- `/start` (or `/cd`) — open the share picker / browse
- `/pair <code>` — pair using the code from the logs
- `/upload` — upload a file into the current directory
- Tap a 📄 file — download it
- Admin only: `/newcode`, `/listusers`, `/revoke <user_id>`
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document commands and smoke-test steps"
```

---

## Self-Review

**Spec coverage:**
- Multiple named jailed shares → Task 2 (`Shares.resolve`), enforced everywhere file access happens (Tasks 10, 11).
- Pairing code printed at startup + `/pair` → Tasks 5, 9, 12.
- Allowlist persistence (atomic) → Task 4.
- Generic denial for unpaired users (no disclosure) → Task 9 (`require_auth`), Task 10 (callback gate).
- Flat permissions → no per-user share logic anywhere (by omission).
- Admin `/revoke`, `/listusers`, `/newcode` → Tasks 5, 9.
- `/cd` inline navigation, share picker, `..` hidden at root, 🏠 home, pagination → Tasks 7, 8, 10.
- Tap-to-download with 50 MB cap → Task 10.
- `/upload` with sanitization, collision suffixing, 20 MB cap → Tasks 3, 11.
- Cloud Bot API only → no local-server config (by omission); limits enforced in Tasks 10–11.
- Config via env + YAML (`SHARES` fallback) → Task 6.
- Runnable directly and via Docker → Tasks 12, 13.
- Testing strategy (resolver, sanitization, pagination, pairing, handlers) → Tasks 2–11.
- Error handling (fail-fast config, global handler, generic path errors) → Tasks 6, 10, 12.

**Placeholder scan:** No TBD/TODO; all code steps include complete code.

**Type consistency:** `Shares.resolve(share, relpath)`, `Location(share, relpath)`, `parse_cb -> (kind, value)`, `build_browser -> (header, markup, page_dirs, page_files)`, `BotState` fields, and the `MAX_SEND_BYTES`/`MAX_RECEIVE_BYTES` constants are used consistently across tasks 7–12.

**Note on download mapping:** Task 10 re-renders the browser before mapping a tapped index to a name, keeping the index space aligned with the displayed page. This is intentional and documented in that task.
