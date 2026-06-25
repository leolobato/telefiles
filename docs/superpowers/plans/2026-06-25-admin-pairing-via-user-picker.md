# Admin-Driven Pairing via User Picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the self-service pairing-code flow with admin-only `/pair` that opens Telegram's native user picker and adds the selected users to the allowlist, and quiet successful long-poll logging.

**Architecture:** `Auth` loses the pairing-code machinery and gains `add_user`. `/pair` becomes admin-only and sends a `KeyboardButtonRequestUsers` reply keyboard; a new `users_shared` handler reads the picked IDs and authorizes them, wired into the application alongside dropping `/newcode` and rescoping `/pair` to the admin command menu. The entrypoint stops logging the (now-removed) pairing code and silences successful `httpx` poll logs.

**Tech Stack:** Python 3.11+, `python-telegram-bot` 21.x (`KeyboardButtonRequestUsers`, `UsersShared`/`SharedUser`, `filters.StatusUpdate.USERS_SHARED`), `pytest`.

## Global Constraints

- Working interpreter is **`./venv/bin/python3`** (system `python3` lacks `python-telegram-bot`). Run pytest as `./venv/bin/python3 -m pytest …`.
- Python **3.11+**; `python-telegram-bot` **>=21,<22**.
- Test output must stay **pristine** (zero warnings).
- **Admin is implicitly authorized** (`is_paired` returns True for `ADMIN_ID`); the admin is never written to the allowlist.
- `/pair` and the `users_shared` handler are **admin-only** (`require_admin`).
- **No pairing code anywhere** after this change (no startup log line, no `/pair <code>`, no `/newcode`).
- Preserve existing jail/auth invariants; do not touch `shares.py`, `navigation.py`, `keyboards.py`, `files.py`, `storage.py`, `config.py`.
- TDD: failing test first, then minimal implementation. Commit after each task.

---

### Task 1: `Auth` — drop the pairing-code system, add `add_user`

**Files:**
- Modify: `telefiles/auth.py`
- Test: `tests/test_auth.py` (rewrite)

**Interfaces:**
- Consumes: `telefiles.storage.load_allowlist`, `telefiles.storage.save_allowlist`.
- Produces:
  - `Auth(allowlist_path: pathlib.Path, admin_id: int)` — no longer generates a code.
  - `Auth.add_user(user_id: int, label: str) -> bool` — adds the user to the allowlist and persists; returns `False` if the user is the admin or already present, `True` if newly added.
  - Unchanged: `is_admin(user_id) -> bool`, `is_paired(user_id) -> bool` (admin implicitly paired), `revoke(user_id) -> bool`, `users() -> dict[str, str]`.
  - **Removed:** `pairing_code`, `new_code`, `try_pair`, `_generate_code`.

- [ ] **Step 1: Replace the test file `tests/test_auth.py` with the new contract**

```python
import pytest
from telefiles.auth import Auth


@pytest.fixture
def auth(tmp_path):
    return Auth(tmp_path / "allow.json", admin_id=999)


def test_admin_recognized(auth):
    assert auth.is_admin(999)
    assert not auth.is_admin(1)


def test_admin_is_implicitly_paired(auth):
    assert auth.is_paired(999)
    assert "999" not in auth.users()
    assert not auth.is_paired(1)


def test_add_user_adds_and_persists(auth, tmp_path):
    assert auth.add_user(42, "@alice") is True
    assert auth.is_paired(42)
    assert auth.users()["42"] == "@alice"
    reloaded = Auth(tmp_path / "allow.json", admin_id=999)
    assert reloaded.is_paired(42)


def test_add_user_duplicate_returns_false(auth):
    assert auth.add_user(42, "@alice") is True
    assert auth.add_user(42, "@alice") is False


def test_add_user_admin_returns_false(auth):
    assert auth.add_user(999, "@boss") is False
    assert "999" not in auth.users()


def test_revoke(auth):
    auth.add_user(42, "@alice")
    assert auth.revoke(42) is True
    assert not auth.is_paired(42)
    assert auth.revoke(42) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/python3 -m pytest tests/test_auth.py -v`
Expected: FAIL — `AttributeError: 'Auth' object has no attribute 'add_user'`.

- [ ] **Step 3: Rewrite `telefiles/auth.py`**

```python
from __future__ import annotations

from pathlib import Path

from telefiles.storage import load_allowlist, save_allowlist


class Auth:
    def __init__(self, allowlist_path: Path, admin_id: int) -> None:
        self._path = allowlist_path
        self._admin_id = admin_id
        self._allow = load_allowlist(allowlist_path)

    def is_admin(self, user_id: int) -> bool:
        return user_id == self._admin_id

    def is_paired(self, user_id: int) -> bool:
        # The admin is always authorized — no need to be added explicitly.
        return self.is_admin(user_id) or str(user_id) in self._allow

    def add_user(self, user_id: int, label: str) -> bool:
        key = str(user_id)
        if self.is_admin(user_id) or key in self._allow:
            return False
        self._allow[key] = label or ""
        save_allowlist(self._path, self._allow)
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

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/python3 -m pytest tests/test_auth.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full suite (other modules still reference the removed code API)**

Run: `./venv/bin/python3 -m pytest -q`
Expected: FAIL — `telefiles/handlers.py` (`cmd_pair`/`cmd_newcode`) and `telefiles/__main__.py` still call the removed `try_pair`/`pairing_code`/`new_code`. This is fixed in Tasks 2–3. `tests/test_auth.py` itself must pass.

- [ ] **Step 6: Commit**

```bash
git add telefiles/auth.py tests/test_auth.py
git commit -m "Replace pairing code with admin add_user in Auth"
```

---

### Task 2: Handlers + app wiring — admin `/pair` user picker, `users_shared`, drop `/newcode`

Handlers and wiring are changed together: the new `users_shared` handler must be registered the moment it exists, and removing `cmd_newcode` spans both files. Splitting them would leave the suite red between commits.

**Files:**
- Modify: `telefiles/handlers.py`
- Modify: `telefiles/app.py`
- Test: `tests/test_handlers_auth.py` (rewrite); `tests/test_app.py` (must still pass, no edits expected)

**Interfaces:**
- Consumes: `telefiles.auth.Auth` (`add_user`, `is_admin`, `is_paired`), existing `require_admin`/`require_auth`, `BotState`, `_state`; `BotCommand`, `filters.StatusUpdate.USERS_SHARED`.
- Produces (in `handlers.py`):
  - `cmd_pair(update, context)` — `@require_admin`; replies with a `ReplyKeyboardMarkup` whose single `KeyboardButton` carries `KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, max_quantity=10, request_name=True, request_username=True)`.
  - `on_users_shared(update, context)` — `@require_admin`; reads `update.effective_message.users_shared.users` (each a `SharedUser` with `.user_id`, `.username`, `.first_name`, `.last_name`), calls `auth.add_user` per user, replies with an added/already-authorized summary and `ReplyKeyboardRemove()`.
  - `_shared_user_label(shared_user) -> str` — `"@username"` if present, else joined first/last name, else `""`.
  - **Removed:** `cmd_newcode`. `cmd_start` unpaired message changed (no code).
- Produces (in `app.py`): `PUBLIC_COMMANDS` = `start`, `cd`, `upload`; `ADMIN_COMMANDS` = public + `pair`, `listusers`, `revoke`; registers `MessageHandler(filters.StatusUpdate.USERS_SHARED, on_users_shared)`; no `/newcode` handler.

- [ ] **Step 1: Replace `tests/test_handlers_auth.py` with the new contract**

```python
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.handlers import (
    BotState, cmd_pair, on_users_shared, require_auth,
)


def make_state(tmp_path, admin_id=999):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="T", admin_id=admin_id, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=admin_id)
    return BotState(config=cfg, auth=auth)


def make_update(user_id):
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


@pytest.mark.asyncio
async def test_pair_denied_for_non_admin(tmp_path):
    state = make_state(tmp_path, admin_id=999)
    update, msg = make_update(42)  # not the admin
    await cmd_pair(update, make_context(state))
    msg.reply_text.assert_awaited()
    # the denial carries no request-users keyboard
    _, kwargs = msg.reply_text.call_args
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_pair_shows_user_picker_for_admin(tmp_path):
    state = make_state(tmp_path, admin_id=999)
    update, msg = make_update(999)
    await cmd_pair(update, make_context(state))
    msg.reply_text.assert_awaited()
    _, kwargs = msg.reply_text.call_args
    markup = kwargs["reply_markup"]
    button = markup.keyboard[0][0]
    assert button.request_users is not None
    assert button.request_users.user_is_bot is False


@pytest.mark.asyncio
async def test_users_shared_adds_users_for_admin(tmp_path):
    state = make_state(tmp_path, admin_id=999)
    update, msg = make_update(999)  # admin
    update.effective_message.users_shared = SimpleNamespace(
        users=[SimpleNamespace(user_id=42, username="alice", first_name="Al", last_name=None)]
    )
    await on_users_shared(update, make_context(state))
    assert state.auth.is_paired(42)
    assert state.auth.users()["42"] == "@alice"
    msg.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_users_shared_denied_for_non_admin(tmp_path):
    state = make_state(tmp_path, admin_id=999)
    update, msg = make_update(42)  # non-admin, not paired
    update.effective_message.users_shared = SimpleNamespace(
        users=[SimpleNamespace(user_id=7, username="x", first_name="X", last_name=None)]
    )
    await on_users_shared(update, make_context(state))
    assert not state.auth.is_paired(7)  # not added
```

- [ ] **Step 2: Run the handler tests to verify they fail**

Run: `./venv/bin/python3 -m pytest tests/test_handlers_auth.py -v`
Expected: FAIL — `ImportError: cannot import name 'on_users_shared'`.

- [ ] **Step 3: Update the telegram imports in `telefiles/handlers.py`**

Change the import line `from telegram import Update` to:

```python
from telegram import (
    KeyboardButton, KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, Update,
)
```

- [ ] **Step 4: Update `cmd_start`'s unpaired message in `telefiles/handlers.py`**

Replace the unpaired branch reply:

```python
    if not state.auth.is_paired(user_id):
        await update.effective_message.reply_text(
            "👋 You are not authorized. Ask the admin to grant you access."
        )
        return
```

- [ ] **Step 5: Replace `cmd_pair` and remove `cmd_newcode` in `telefiles/handlers.py`**

Delete the existing `cmd_pair` function and the entire `cmd_newcode` function, and insert this in their place:

```python
def _shared_user_label(shared_user) -> str:
    if shared_user.username:
        return f"@{shared_user.username}"
    name = " ".join(p for p in (shared_user.first_name, shared_user.last_name) if p)
    return name or ""


@require_admin
async def cmd_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    button = KeyboardButton(
        "👤 Choose a user to authorize",
        request_users=KeyboardButtonRequestUsers(
            request_id=1,
            user_is_bot=False,
            max_quantity=10,
            request_name=True,
            request_username=True,
        ),
    )
    await update.effective_message.reply_text(
        "Tap the button to pick the user(s) to authorize:",
        reply_markup=ReplyKeyboardMarkup(
            [[button]], resize_keyboard=True, one_time_keyboard=True
        ),
    )


@require_admin
async def on_users_shared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    shared = update.effective_message.users_shared
    users = list(shared.users) if shared else []
    if not users:
        await update.effective_message.reply_text(
            "No users selected.", reply_markup=ReplyKeyboardRemove()
        )
        return
    added, existing = [], []
    for su in users:
        label = _shared_user_label(su)
        display = label or str(su.user_id)
        if state.auth.add_user(su.user_id, label):
            added.append(display)
        else:
            existing.append(display)
    lines = []
    if added:
        lines.append("✅ Authorized: " + ", ".join(added))
    if existing:
        lines.append("ℹ️ Already authorized: " + ", ".join(existing))
    await update.effective_message.reply_text(
        "\n".join(lines), reply_markup=ReplyKeyboardRemove()
    )
```

- [ ] **Step 6: Run the handler tests to verify they pass**

Run: `./venv/bin/python3 -m pytest tests/test_handlers_auth.py -v`
Expected: PASS (6 tests).

- [ ] **Step 7: Update the command constants in `telefiles/app.py`**

Replace the `PUBLIC_COMMANDS` and `ADMIN_COMMANDS` definitions with:

```python
# Commands shown to every user (default scope).
PUBLIC_COMMANDS = [
    BotCommand("start", "Open the share picker / browse"),
    BotCommand("cd", "Same as /start — browse shares"),
    BotCommand("upload", "Upload a file into the current folder"),
]

# Full list shown only in the admin's chat (chat-scoped). Must cover every
# registered command handler so autocomplete stays in sync with the bot.
ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand("pair", "Authorize a user (opens the user picker)"),
    BotCommand("listusers", "List paired users"),
    BotCommand("revoke", "Remove a user: /revoke <user_id>"),
]
```

- [ ] **Step 8: Update the handler registrations in `build_application` (`telefiles/app.py`)**

Remove the `/newcode` line and register the `users_shared` handler so the block reads:

```python
    app.add_handler(CommandHandler("start", h.cmd_start))
    app.add_handler(CommandHandler("cd", h.cmd_start))
    app.add_handler(CommandHandler("pair", h.cmd_pair))
    app.add_handler(CommandHandler("upload", h.cmd_upload))
    app.add_handler(CommandHandler("listusers", h.cmd_listusers))
    app.add_handler(CommandHandler("revoke", h.cmd_revoke))
    app.add_handler(CallbackQueryHandler(h.on_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.USERS_SHARED, h.on_users_shared))
    app.add_handler(MessageHandler(filters.Document.ALL, h.on_document))
    app.add_error_handler(_on_error)
```

- [ ] **Step 9: Run the app tests and the full suite**

Run: `./venv/bin/python3 -m pytest tests/test_app.py -v && ./venv/bin/python3 -m pytest -q`
Expected: PASS, pristine. (`test_command_lists_cover_every_registered_command` confirms `ADMIN_COMMANDS` == registered command set `{start, cd, pair, upload, listusers, revoke}`; `test_build_application_registers_handlers` still sees ≥9 handlers: 6 commands + callback + 2 message handlers. `__main__.py` still references the removed code API, but no test imports/executes `main()`, so the suite is green; Task 3 cleans `__main__.py`.)

- [ ] **Step 10: Commit**

```bash
git add telefiles/handlers.py telefiles/app.py tests/test_handlers_auth.py
git commit -m "Make /pair an admin user picker; wire users_shared; drop /newcode"
```

---

### Task 3: Entrypoint — quiet polling logs, drop pairing-code log

**Files:**
- Modify: `telefiles/__main__.py`
- Test: `tests/test_main.py` (create)

**Interfaces:**
- Consumes: `telefiles.app.build_application`, `telefiles.config.load_config`.
- Produces: `_configure_logging() -> None` — sets root logging to INFO and the `httpx` logger to WARNING. `main()` calls it, logs a plain startup line, and no longer references `pairing_code`.

- [ ] **Step 1: Write the failing test `tests/test_main.py`**

```python
import logging
from telefiles.__main__ import _configure_logging


def test_configure_logging_quiets_httpx():
    _configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    # the app's own logger still emits at INFO
    assert logging.getLogger("telefiles").getEffectiveLevel() == logging.INFO
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./venv/bin/python3 -m pytest tests/test_main.py -v`
Expected: FAIL — `ImportError: cannot import name '_configure_logging'` (the current `main()` also still references `state.auth.pairing_code`).

- [ ] **Step 3: Rewrite `telefiles/__main__.py`**

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


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    # Silence the per-request "getUpdates 200 OK" lines; failures still log.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    _configure_logging()
    _load_dotenv(Path(".env"))
    config = load_config(dict(os.environ), Path("config.yaml"))
    app = build_application(config)
    logging.getLogger("telefiles").info(
        "telefiles started; use /pair (admin) to authorize users"
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./venv/bin/python3 -m pytest tests/test_main.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `./venv/bin/python3 -m pytest -q`
Expected: PASS, pristine.

- [ ] **Step 6: Commit**

```bash
git add telefiles/__main__.py tests/test_main.py
git commit -m "Quiet successful poll logs; drop pairing-code startup log"
```

---

### Task 4: Docs — README and CLAUDE.md

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the behavior built in Tasks 1–3. Produces: documentation only.

- [ ] **Step 1: Update the pairing flow in `README.md` (read the file first)**

The bot no longer prints a code and users no longer self-pair. Make these precise edits against the current wording (do not duplicate sections):

- In the setup/`ADMIN_ID` area, state that **the admin is authorized automatically** and is the only one who can add others.
- Replace the run-section pairing step ("Read the pairing code from the logs and send `/pair <code>` …") with: the admin sends **`/pair`**, taps the **"👤 Choose a user to authorize"** button, and selects the user(s) from Telegram's native picker; chosen users are added to the allowlist.
- In the **Commands** section, change the `/pair` line to `/pair — (admin) authorize a user via the native user picker` and **remove** the `/newcode` entry.
- In **Notes & limits**, drop any text about the pairing code populating `allowlist.json`; keep the "admin is always authorized" note.

- [ ] **Step 2: Update `CLAUDE.md` (read the file first)**

- In the `auth.py` architecture bullet, replace the pairing-code description with: the admin authorizes users via the native user picker (`/pair` → `users_shared` → `Auth.add_user`); there is no pairing code; the admin (`ADMIN_ID`) is implicitly authorized.
- In the invariants/commands notes, remove references to the pairing code and `/newcode`; note that `/pair` is admin-only and that successful long-poll requests are not logged (failures only).

- [ ] **Step 3: Run the full suite to confirm nothing regressed**

Run: `./venv/bin/python3 -m pytest -q`
Expected: PASS, pristine.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Document admin user-picker pairing; drop pairing code"
```

---

## Self-Review

**Spec coverage:**
- Admin-only `/pair` opening the native picker → Task 2 (`cmd_pair` `@require_admin` + `KeyboardButtonRequestUsers`).
- Selection adds user(s) with label, summary, keyboard removed → Task 2 (`on_users_shared`, `_shared_user_label`, `ReplyKeyboardRemove`).
- `Auth.add_user`, removal of the code system → Task 1.
- Already-authorized / admin-selected no-op → Task 1 (`add_user` returns False) + Task 2 summary.
- Unpaired `/start` message without a code → Task 2 (Step 4).
- Drop `/newcode`, register `users_shared`, rescope `/pair` to admin menu → Task 2 (Steps 7–8).
- Remove pairing-code startup log; quiet `httpx` to failures only → Task 3.
- Docs → Task 4.
- Non-admin denial for `/pair` and `users_shared` → Task 2 tests.

**Placeholder scan:** No TBD/TODO; all code steps contain complete code. README/CLAUDE.md edits (Task 4) are documentation prose against known short files and are described precisely rather than diffed.

**Type consistency:** `add_user(user_id: int, label: str) -> bool` defined in Task 1, called identically in Task 2. `cmd_pair`/`on_users_shared` names match between definition (Task 2 handlers) and registration (Task 2 app) and the tests. `PUBLIC_COMMANDS`/`ADMIN_COMMANDS` command set matches the registered `CommandHandler`s, enforced by the existing `test_command_lists_cover_every_registered_command`. `_configure_logging` defined and tested in Task 3.

**Intermediate red:** Task 1's full-suite step is intentionally red (handlers/`__main__` still call the old API); Task 2 turns the suite green again. `__main__.py` keeps a stale `pairing_code` reference until Task 3, but no test imports `main()`, so the suite is green after Task 2. Both noted in the relevant steps.
```
