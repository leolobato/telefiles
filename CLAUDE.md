# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot (`python-telegram-bot` v21, long polling) for browsing, uploading, and downloading files from multiple configured, **jailed** directory "shares". Only paired users may use it. MVP scope is exactly four operations — list, `/cd`, `/upload`, tap-to-download — and nothing destructive (no delete/rename/mkdir).

## Environment & commands

**Use the venv interpreter — `./venv/bin/python3` — not system `python3`.** The repo's venv has `python-telegram-bot` and `PyYAML`; the system Python (3.14) does not, so modules that `import telegram` fail under it.

```bash
# install (creates/uses the venv)
./venv/bin/python3 -m pip install -e ".[dev]"

# full test suite (must be pristine — zero warnings is a maintained invariant)
./venv/bin/python3 -m pytest -q

# a single test file / single test
./venv/bin/python3 -m pytest tests/test_shares.py -v
./venv/bin/python3 -m pytest tests/test_handlers_nav.py::test_file_on_page1_maps_to_correct_entry -v

# run the bot (needs BOT_TOKEN + ADMIN_ID in env or .env, and a config.yaml)
./venv/bin/python3 -m telefiles
```

Docker: `docker compose up --build` (edit the share volume mounts in `docker-compose.yml` to match `config.yaml` first — they are commented-out examples by default).

## Configuration

- Env vars: `BOT_TOKEN`, `ADMIN_ID`, `DATA_DIR` (default `./data`). See `.env.example`.
- Shares come from `config.yaml` (`shares:` name→host-path mapping) or, as a fallback, the `SHARES` env var (`name:path,name:path`). See `config.yaml.example`.
- `load_config` fails fast with a clear `ConfigError` on any missing/invalid value.

## Architecture

Layered, with pure logic deliberately kept free of the `telegram` dependency so it stays unit-testable. Data flows: Telegram update → `handlers` → pure logic (`shares`/`navigation`/`files`/`auth`) → filesystem.

- **`shares.py` — the security chokepoint.** `Shares.resolve(share, relpath)` is the ONE place filesystem paths are produced. It resolves symlinks *before* an `is_relative_to` containment check, blocking `..`, absolute-path, and symlink escapes. **Every** file access (listing, download read, upload write) must route through it; never construct a filesystem path from user input any other way.
- **`auth.py` + `storage.py`** — `Auth` holds the allowlist (persisted atomically as JSON via `storage`, temp-file + `os.replace`). Pairing codes are single-use (rotated on success) and compared with `secrets.compare_digest`. The startup pairing code is printed to the logs to bootstrap the first user.
- **`config.py`** — `Config` dataclass + `load_config`; wraps `ShareError` as `ConfigError`.
- **`navigation.py`** — pure, Telegram-free: the `Location` dataclass (`share`, `relpath`, `page`), `list_entries`, `paginate`, and compact callback-data codecs (`cb_*`/`parse_cb`). Callback data encodes an **index**, not a path (Telegram's 64-byte callback_data limit).
- **`keyboards.py`** — builds `InlineKeyboardMarkup` on top of `navigation`. `build_browser` returns `(header, markup, page_dirs, page_files)`; the button callback indices are positions into `page_dirs + page_files` for the displayed page.
- **`handlers.py`** — all command/callback handlers + `BotState` (config, auth, per-user `locations`, `awaiting_upload`), stored on `application.bot_data["state"]`. `require_auth`/`require_admin` decorators gate every handler.
- **`app.py` / `__main__.py`** — `build_application(config)` wires handlers and returns the app without starting; `main()` loads `.env`, builds config, logs the pairing code, runs polling.

## Invariants to preserve when editing

- **Jail:** all filesystem access goes through `shares.resolve`. Upload filenames are *also* run through `files.sanitize_filename` (strips path components) before joining — defense in depth.
- **Auth:** unpaired users get a generic denial and learn nothing (no share/file names leaked). Admin commands are gated by `require_admin` independently of pairing.
- **Size limits:** download refused if `> MAX_SEND_BYTES` (50 MB) before sending; upload refused if `> MAX_RECEIVE_BYTES` (20 MB) before any disk write. These are cloud Bot API limits — a self-hosted Bot API server is out of scope.
- **Navigation index/page coupling:** a tapped button's index is mapped against the page actually displayed. The current page lives in `Location.page` and must be persisted on page (`p`) callbacks and reset to 0 on share-enter/up/descend — otherwise tapping an item on page >1 resolves the wrong entry. `tests/test_handlers_nav.py::test_file_on_page1_maps_to_correct_entry` guards this.

## Testing notes

- Handler tests use mocked `Update`/`Context` (AsyncMock), not a live bot. Pure modules are tested against the real filesystem via `tmp_path`.
- `pyproject.toml` sets `asyncio_mode=auto` and filters a pytest-asyncio internal deprecation warning so output stays pristine — keep it that way.

## Design docs

The full spec and the task-by-task implementation plan live in `docs/superpowers/specs/` and `docs/superpowers/plans/`.
