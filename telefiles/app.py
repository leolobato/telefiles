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
