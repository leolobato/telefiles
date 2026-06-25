# Telefiles — Telegram File Browser Bot (MVP Design)

**Date:** 2026-06-25
**Status:** Approved design, pre-implementation

## Summary

A Telegram bot for browsing, uploading, and downloading files from configured
directories on a host. Authorized (paired) users navigate a set of named,
jailed directory "shares" via inline-keyboard buttons, tap files to download
them, and use `/upload` to send files into the current directory. Polling-based
(no public URL required); runnable directly with Python or via Docker.

## Goals (MVP scope)

Exactly four operations, nothing destructive:

1. **List** files/directories in the current location.
2. **`/cd`** navigation via inline buttons.
3. **`/upload`** — send a file into the current directory.
4. **Download** — tap a file to receive it.

Plus the supporting capability: **pairing** of Telegram user IDs so only
authorized users are served.

## Non-Goals (explicitly out of scope for MVP)

- Destructive / management operations: delete, rename, mkdir, move.
- Per-user share restrictions (all paired users are equal).
- Files larger than Telegram's cloud Bot API limits (50 MB send / 20 MB
  receive) — rejected with a clear message.
- Self-hosted local Bot API server (the API base URL is **not** required to be
  configurable for the MVP; can be added later).
- Webhooks (we use long polling).

## Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Browse scope | **Multiple named roots** ("shares"), each jailed |
| Pairing | **Pairing code printed to logs/CLI**; user sends `/pair <code>` |
| File size | **Cloud Bot API only** (≤50 MB down / ≤20 MB up); oversize rejected |
| Operations | **Just the four** (list, cd, upload, download); nothing destructive |
| Library | **`python-telegram-bot` v21+** (async, `run_polling`) |
| Shares config | **`config.yaml`** (with env-var fallback) |

## Architecture & Modules

A small async Python app, long-polling based.

```
telefiles/
  __main__.py        # entrypoint: load config, build app, run_polling
  config.py          # load + validate config (token, shares, admin id) from env/file
  auth.py            # allowlist load/save, pairing-code logic, @require_auth decorator
  shares.py          # named roots + safe path resolution (jail enforcement)
  navigation.py      # per-user cwd state, inline-keyboard builders, pagination
  handlers.py        # command + callback handlers (/start /pair /cd /upload, file taps)
  storage.py         # JSON persistence for allowlist (atomic writes)
```

Each module has one job. `shares.resolve(share, relpath) -> Path` is the
security chokepoint that all file access routes through.

## Security Model (critical)

- **Jailed shares:** every path resolves through one function that computes
  `Path(root, relpath).resolve()` and asserts the result is still under `root`
  (via `is_relative_to`). Symlinks are resolved *before* the check, so a symlink
  pointing outside a share is rejected. No `..` escape is possible.
- **Auth gate:** every handler is wrapped in `@require_auth`. Unpaired users
  receive a generic "not authorized" message and the bot reveals nothing
  (no share names, no file names) until they are paired.
- **Flat permissions:** all paired users can read/write all shares.
- **Admin:** a single `ADMIN_ID` in config can `/revoke <id>`, `/listusers`,
  and `/newcode` (rotate the pairing code). The startup pairing code bootstraps
  the first user.

## Pairing Flow

1. On startup, if no users are paired, the bot generates a random pairing code
   and prints it to stdout/logs. Admin can also `/newcode` to rotate it.
2. New user sends `/pair <code>`. If it matches, their Telegram ID + username is
   appended to the allowlist and the code is consumed (single-use; regenerated
   on demand / for the next person).
3. Allowlist persisted to `<DATA_DIR>/allowlist.json` via atomic write.

## Navigation UX (`/cd` + listing + download)

- `/start` or `/cd` with no args → inline keyboard listing the **named shares**.
- Tap a share → enter it; the bot shows the current path as text plus an inline
  keyboard:
  - 📁 directory buttons (tap to descend)
  - `⬆️ ..` button (hidden at a share root — cannot escape the jail)
  - 🏠 back-to-shares button
- Files appear as 📄 buttons in the same keyboard; **tapping a file downloads
  it** (the bot sends the document). Files >50 MB return a "too large
  (max 50 MB)" message instead.
- **Pagination:** directories with many entries get ◀️/▶️ page buttons.
  Directories listed before files; both alphabetical.
- Per-user current location is kept **in memory** (dict keyed by user id) and
  resets to the share picker on restart. Navigation state is not persisted.

## Upload Flow

- `/upload` → bot replies "send me the file(s) now; they'll be saved to
  `<current path>`" and sets a per-user "awaiting upload" flag.
- User sends a document → saved into the current directory. Filename is
  sanitized (path components stripped). On name collision, append ` (1)`,
  ` (2)`, … rather than overwrite (no destructive operations).
- Uploads >20 MB are rejected by Telegram; the bot reports the limit.

## Config, Packaging & Docker

**Configuration:**
- Env vars: `BOT_TOKEN`, `ADMIN_ID`, `DATA_DIR`.
- Shares defined in `config.yaml` (name → host path). Env fallback `SHARES`
  in the form `name:path,name:path`.

Example `config.yaml`:

```yaml
shares:
  Photos: /mnt/photos
  Docs: /srv/docs
```

**Runnable two ways:**
- Directly: `pip install -e . && python -m telefiles` (reads env / `.env`).
- Docker: `Dockerfile` + `docker-compose.yml`. Share directories mounted as
  volumes; a `data/` volume holds the allowlist. Compose maps host dirs →
  container paths referenced by the share config.

## Error Handling

- Unauthorized access → generic denial, no information disclosure.
- Path resolution failure / jail violation → "invalid path" (logged in detail
  server-side, generic to the user).
- File too large (either direction) → explicit limit message.
- Missing/invalid config at startup → fail fast with a clear error before the
  bot connects.
- Telegram/network errors → caught by a global error handler; logged; the bot
  keeps running.

## Testing Strategy

Unit-tested (pure / near-pure logic):
- `shares.resolve` — jail enforcement, `..` traversal, symlink escape.
- Filename sanitization and collision suffixing.
- Pagination math (page boundaries, button layout).
- Pairing-code generation / validation / consumption.

Handler-level tests use `python-telegram-bot`'s testing helpers / mocked
`Update` objects to verify auth gating, navigation callbacks, and upload flow.

## Open Questions

None blocking. Future enhancements (post-MVP): local Bot API server for large
files, per-user share permissions, destructive operations with confirmation.
