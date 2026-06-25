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
- Telegram-ID allowlist; new users pair with a one-time code printed to the logs
- Browse with `/cd` and inline buttons (directories, `..`, home, pagination)
- Tap a file to download it (up to 50 MB)
- `/upload` a file into the current directory (up to 20 MB)
- Admin commands to rotate the pairing code and manage users

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
uploaded documents in group contexts (not needed for one-on-one chats), and
`/setcommands` to register the command list for autocomplete.

### Find your numeric user ID (for `ADMIN_ID`)

The admin is identified by their numeric Telegram user ID, not their username.
Get yours by messaging a bot such as [@userinfobot](https://t.me/userinfobot) —
it replies with your ID (a number like `8431001234`). Use that as `ADMIN_ID`.

The admin can always rotate the pairing code (`/newcode`) and manage users, and is
the one who bootstraps the first pairing.

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

On startup the bot logs a **pairing code**. Anyone who sends `/pair <code>` to the
bot is added to the allowlist (the code is single-use and rotates after each
successful pairing; the admin can mint a new one with `/newcode`).

### With Docker

1. Create `config.yaml` defining your shares using the **container** paths you
   will mount.
2. Set `BOT_TOKEN` and `ADMIN_ID` in your environment or `.env`.
3. Edit the share volume mounts in `docker-compose.yml` to match `config.yaml`
   (they ship commented out). Mount a share read-only (`:ro`) to forbid uploads
   into it; mount read-write to allow `/upload`.
4. `docker compose up --build`
5. Read the pairing code from the logs and send `/pair <code>` to the bot.

## Using the bot

1. Send `/start` to the bot, then `/pair <code>` using the code from the logs.
2. `/start` (or `/cd`) again to open the share picker.
3. Tap a share, then navigate with the 📁 / `⬆️ ..` / 🏠 buttons.
4. Tap a 📄 file to download it.
5. Send `/upload` while inside a directory, then send the file — it is saved there.

### Commands

- `/start` (or `/cd`) — open the share picker / browse
- `/pair <code>` — pair using the code from the logs
- `/upload` — upload a file into the current directory
- Tap a 📄 file — download it
- Admin only: `/newcode` (rotate the pairing code), `/listusers`,
  `/revoke <user_id>`

## Notes & limits

- File sizes are bounded by the cloud Bot API: **50 MB** for downloads, **20 MB**
  for uploads. Larger files are rejected with a message.
- The allowlist is persisted to `<DATA_DIR>/allowlist.json`. Keep this directory
  on a volume so pairings survive restarts.
- All paired users have equal read/write access to all shares.

See `docs/superpowers/specs/` and `docs/superpowers/plans/` for the full design
and implementation plan, and `CLAUDE.md` for development guidance.
