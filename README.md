# Telefiles

A Telegram bot for browsing, uploading, and downloading files from configured,
**jailed** directory "shares" on a host. Only paired users may use it, navigation
is done with inline buttons, and each share is sandboxed so users can never escape
above its root.

It runs over long polling (no public URL or webhook needed — works behind NAT or
in Docker) and can be run directly with Python or via Docker.

## Features

- Multiple named shares, each jailed to its own directory (no `..`, absolute-path,
  or symlink escapes)
- Telegram-ID allowlist; the admin authorizes users via Telegram's native user picker
- Browse with `/cd` and inline buttons (directories, `..`, home, pagination)
- Tap a file to download it (up to 50 MB)
- `/upload` a file into the current directory (up to 20 MB)
- Admin commands to manage users

## 1. Create the bot in Telegram

You need a **bot token** (which API to talk to) and your **numeric user ID**
(who the admin is).

### Get a bot token from BotFather

1. In Telegram, open a chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts: choose a display name and a username
   (the username must end in `bot`, e.g. `my_files_bot`).
3. BotFather replies with a token that looks like
   `123456789:AAEhBOweik6ad...`. This is your `BOT_TOKEN` — keep it secret.

Optional, via BotFather: `/setprivacy` → **Disable** so the bot reliably receives
uploaded documents in group contexts (not needed for one-on-one chats). You do
**not** need `/setcommands` — the bot publishes its command menu automatically on
startup (public commands for everyone, plus the admin-only commands scoped to the
admin's chat).

### Find your numeric user ID (for `ADMIN_ID`)

The admin is identified by their numeric Telegram user ID, not their username.
Get yours by messaging a bot such as [@userinfobot](https://t.me/userinfobot) —
it replies with your ID (a number like `8431001234`). Use that as `ADMIN_ID`.

The admin is **automatically authorized** — no pairing required. The admin is the
only one who can authorize other users.

## 2. Configure

Set the environment and define your shares.

```bash
cp .env.example .env          # fill in BOT_TOKEN and ADMIN_ID
cp config.yaml.example config.yaml
```

`.env`:

```bash
BOT_TOKEN=123456789:AAEhBOweik6ad...
ADMIN_ID=8431001234
DATA_DIR=./data               # where the allowlist is stored
```

`config.yaml` — map a share name to a host directory:

```yaml
shares:
  Photos: /mnt/photos
  Docs: /srv/docs
```

(Shares can alternatively be set with the `SHARES` env var as
`Name:/path,Name:/path`.)

## 3. Run

### Directly with Python

```bash
python -m pip install -e ".[dev]"
python -m telefiles
```

The admin is automatically authorized. To grant access to another user, the admin
sends **`/pair`**, taps the **"👤 Choose a user to authorize"** button, and selects
the user(s) from Telegram's native picker; the chosen users are added to the
allowlist.

### With Docker

1. Create `config.yaml` defining your shares using the **container** paths you
   will mount.
2. Set `BOT_TOKEN` and `ADMIN_ID` in your environment or `.env`.
3. Edit the share volume mounts in `docker-compose.yml` to match `config.yaml`
   (they ship commented out). Mount a share read-only (`:ro`) to forbid uploads
   into it; mount read-write to allow `/upload`.
4. `docker compose up --build`
5. The admin is automatically authorized. To add another user, the admin sends
   **`/pair`**, taps **"👤 Choose a user to authorize"**, and picks the user(s)
   from Telegram's native picker.

## Using the bot

1. The admin sends `/start` to open the share picker. Other users must be
   authorized first (see the `/pair` flow below).
2. `/start` (or `/cd`) to open the share picker.
3. Tap a share, then navigate with the 📁 / `⬆️ ..` / 🏠 buttons.
4. Tap a 📄 file to download it.
5. Send `/upload` while inside a directory, then send the file — it is saved there.

### Commands

- `/start` (or `/cd`) — open the share picker / browse
- `/pair` — (admin) authorize a user via the native user picker
- `/upload` — upload a file into the current directory
- Tap a 📄 file — download it
- Admin only: `/listusers`, `/revoke <user_id>`

## Notes & limits

- File sizes are bounded by the cloud Bot API: **50 MB** for downloads, **20 MB**
  for uploads. Larger files are rejected with a message.
- The allowlist is persisted to `<DATA_DIR>/allowlist.json`. Keep this directory
  on a volume so authorized users survive restarts.
- The **admin** (`ADMIN_ID`) is always authorized and does not need to be added —
  `/pair` is for granting access to other users.
- All paired users have equal read/write access to all shares.

See `docs/superpowers/specs/` and `docs/superpowers/plans/` for the full design
and implementation plan, and `CLAUDE.md` for development guidance.
