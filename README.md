# Telefiles

A Telegram bot for browsing, uploading, and downloading files from configured,
jailed directory shares. See `docs/superpowers/specs/` for the design.

## Quick start

    pip install -e ".[dev]"
    cp .env.example .env   # fill in BOT_TOKEN, ADMIN_ID
    # edit config.yaml with your shares
    python -m telefiles
