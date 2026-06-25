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
