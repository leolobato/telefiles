# Telefiles

A Telegram bot for browsing, uploading, and downloading files from configured,
jailed directory shares. See `docs/superpowers/specs/` for the design.

## Quick start

    pip install -e ".[dev]"
    cp .env.example .env   # fill in BOT_TOKEN, ADMIN_ID
    # edit config.yaml with your shares
    python -m telefiles

## Running with Docker

1. Copy `config.yaml.example` to `config.yaml` and define your shares using the
   container paths you will mount.
2. Set `BOT_TOKEN` and `ADMIN_ID` in your environment or a `.env` file.
3. Edit the share volume mounts in `docker-compose.yml` to match `config.yaml`.
4. `docker compose up --build`
5. Read the pairing code from the logs and send `/pair <code>` to the bot.

Mount a share read-only (`:ro`) to prevent uploads into it; mount read-write to
allow `/upload`.

## Commands

- `/start` (or `/cd`) — open the share picker / browse
- `/pair <code>` — pair using the code from the logs
- `/upload` — upload a file into the current directory
- Tap a 📄 file — download it
- Admin only: `/newcode`, `/listusers`, `/revoke <user_id>`
