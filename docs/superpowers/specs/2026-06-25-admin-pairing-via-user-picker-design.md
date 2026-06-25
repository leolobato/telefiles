# Admin-Driven Pairing via Native User Picker (Design)

**Date:** 2026-06-25
**Status:** Approved design, pre-implementation
**Supersedes:** the self-service pairing-code mechanism from the MVP design
(`2026-06-25-telefiles-telegram-bot-design.md`).

## Summary

Replace the self-service pairing-code flow with **admin-driven pairing**. The
admin (identified by `ADMIN_ID`, already implicitly authorized) is the only user
who may run `/pair`. `/pair` opens Telegram's **native user picker**; the admin
selects one or more users and the bot extracts their numeric IDs and adds them to
the allowlist. The startup pairing code, `/pair <code>` redemption, and `/newcode`
are removed. Successful long-poll requests are no longer logged (failures only).

## Motivation

- A bot cannot resolve an arbitrary `@username` to a user ID — the Bot API has no
  such lookup. The native user picker (`KeyboardButtonRequestUsers`) is the
  reliable way to turn a chosen user into an ID.
- Centralizing pairing on the admin removes the shared-secret code (and its log
  line) and the self-service surface, matching how this bot is actually operated.

## Behavior

- **`/pair` is admin-only** (`require_admin`). A non-admin who sends it gets
  "⛔ Admin only."
- **`/pair` opens the native user picker.** The bot replies with a one-button
  `ReplyKeyboardMarkup` containing a `KeyboardButtonRequestUsers` button
  ("👤 Choose a user to authorize"), configured with `user_is_bot=False`,
  `request_name=True`, `request_username=True`, and `max_quantity` allowing
  multiple selections.
- **Selection adds the user(s).** Telegram delivers a `users_shared` service
  message listing the chosen users (IDs plus name/username). The bot adds each to
  the allowlist with a friendly label, replies with a confirmation summarizing who
  was added (and who was already authorized), and removes the reply keyboard
  (`ReplyKeyboardRemove`).
- **Already-authorized / admin selected:** adding an existing user is a no-op
  reported as "already authorized"; selecting the admin is likewise a no-op (the
  admin is implicitly paired).
- **Unpaired users:** `/start` tells them to ask the admin to grant access (no
  mention of a code).
- **No pairing code:** the startup code log line, `/pair <code>` redemption, and
  `/newcode` are removed.
- **Quiet polling:** successful long-poll HTTP requests are not logged; failures
  (HTTP 4xx/5xx, network errors) still surface, as do the bot's own logs and the
  global error handler.

## Components

### `auth.py`
- **Remove:** `pairing_code` property, `new_code`, `try_pair`, `_generate_code`,
  and the `secrets` import.
- **Add:** `add_user(user_id: int, label: str) -> bool` — adds the user to the
  allowlist and persists (atomic write via `storage`); returns `False` if the
  user was already present (or is the admin), `True` if newly added.
- **Keep unchanged:** `is_admin`, `is_paired` (admin remains implicitly paired),
  `revoke`, `users`.

### `handlers.py`
- `cmd_pair` — now decorated `@require_admin`; replies with the request-users
  reply keyboard. No longer reads `context.args`.
- `on_users_shared` — new `@require_admin` handler. Reads
  `update.effective_message.users_shared.users`, calls `auth.add_user` for each
  (building a label from username/first name when present), replies with a summary
  of added vs. already-authorized users, and sends `ReplyKeyboardRemove`.
- **Remove:** `cmd_newcode`.
- `cmd_start` — unpaired branch message changes to instruct the user to ask the
  admin for access (no code).

### `app.py`
- **Remove** the `/newcode` `CommandHandler`.
- **Register** `MessageHandler(filters.StatusUpdate.USERS_SHARED, on_users_shared)`.
- Command menu: `/pair` moves from `PUBLIC_COMMANDS` into the admin-scoped list;
  `PUBLIC_COMMANDS` becomes `start`, `cd`, `upload`; `ADMIN_COMMANDS` =
  public + `pair`, `listusers`, `revoke` (no `newcode`). The
  command-coverage test must continue to match the registered command handlers.

### `__main__.py`
- **Remove** the "Pairing code: …" log line; replace with a plain startup line
  (e.g. "telefiles started; use /pair to authorize users").
- Set the `httpx` logger to `WARNING` so successful poll requests are not logged
  while failures still are. The `telefiles` logger stays at `INFO`.

### Docs
- README: replace the "create the bot / pairing" guidance — pairing is now done by
  the admin via `/pair` + the user picker; remove references to the logged code.
- CLAUDE.md: update the auth/pairing description and the admin-scoped command list.

## Data flow

```
admin sends /pair
  -> require_admin passes
  -> bot sends ReplyKeyboardMarkup[ KeyboardButtonRequestUsers ]
admin taps button -> Telegram user picker -> admin selects user(s)
  -> Telegram sends message.users_shared (SharedUser[].user_id, .username, .first_name)
  -> on_users_shared (require_admin)
       for each shared user: auth.add_user(id, label)
       reply summary + ReplyKeyboardRemove
```

## Error handling

- Non-admin invocation of `/pair` or receipt of a `users_shared` update → generic
  "⛔ Admin only." (the latter is defense in depth; only the admin would have the
  keyboard).
- Adding an already-present user or the admin → reported as "already authorized",
  not an error.
- A `users_shared` update with no resolvable users → a short "no users selected"
  reply; no crash.

## Testing

- `auth.add_user`: adds + persists across reload; returns `False` for a duplicate
  and for the admin id; `True` for a new user.
- `cmd_pair`: denied for a non-admin (no keyboard sent); for the admin, the reply
  carries a `ReplyKeyboardMarkup` whose button is a `KeyboardButtonRequestUsers`.
- `on_users_shared`: as admin, adds the shared user id(s) to the allowlist and
  replies; denied for a non-admin (user not added).
- `cmd_start` unpaired message no longer references a code.
- `app.py`: `/newcode` no longer registered; a `users_shared` `MessageHandler` is
  registered; `PUBLIC_COMMANDS`/`ADMIN_COMMANDS` cover exactly the registered
  command handlers (existing coverage test updated for the new command set).

Handler tests use mocked `Update`/`Context` (AsyncMock), consistent with the
existing suite; the working interpreter is `./venv/bin/python3`.

## Out of scope

- Resolving users by `@username` string (not possible via the Bot API).
- Forwarded-message / shared-contact pairing paths (the picker is the single
  chosen mechanism).
- Per-user share permissions (unchanged: all paired users have equal access).
