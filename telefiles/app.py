from __future__ import annotations

import logging

from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import (
    Application, ApplicationBuilder, CallbackQueryHandler,
    CommandHandler, ContextTypes, MessageHandler, filters,
)

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles import handlers as h

logger = logging.getLogger("telefiles")

# Commands shown to every user (default scope).
PUBLIC_COMMANDS = [
    BotCommand("start", "Open the share picker / browse"),
    BotCommand("cd", "Same as /start — browse shares"),
    BotCommand("upload", "Upload a file into the current folder"),
    BotCommand("refresh", "Reload the current folder"),
    BotCommand("zip", "Download the current folder as a .zip"),
]

# Full list shown only in the admin's chat (chat-scoped). Must cover every
# registered command handler so autocomplete stays in sync with the bot.
ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand("pair", "Authorize a user (opens the user picker)"),
    BotCommand("listusers", "List paired users"),
    BotCommand("revoke", "Remove a user: /revoke <user_id>"),
]


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Handler error", exc_info=context.error)


async def _register_commands(app: Application) -> None:
    """Publish the command menu on startup: public commands by default, plus the
    admin-only commands scoped to the admin's chat. Failure is non-fatal."""
    state = app.bot_data["state"]
    try:
        await app.bot.set_my_commands(PUBLIC_COMMANDS)
        await app.bot.set_my_commands(
            ADMIN_COMMANDS,
            scope=BotCommandScopeChat(chat_id=state.config.admin_id),
        )
    except Exception:
        logger.warning("Failed to register bot commands", exc_info=True)


def build_application(config: Config) -> Application:
    auth = Auth(config.data_dir / "allowlist.json", config.admin_id)
    state = h.BotState(config=config, auth=auth)

    app = ApplicationBuilder().token(config.token).post_init(_register_commands).build()
    app.bot_data["state"] = state

    app.add_handler(CommandHandler("start", h.cmd_start))
    app.add_handler(CommandHandler("cd", h.cmd_start))
    app.add_handler(CommandHandler("pair", h.cmd_pair))
    app.add_handler(CommandHandler("upload", h.cmd_upload))
    app.add_handler(CommandHandler("refresh", h.cmd_refresh))
    app.add_handler(CommandHandler("zip", h.cmd_zip))
    app.add_handler(CommandHandler("listusers", h.cmd_listusers))
    app.add_handler(CommandHandler("revoke", h.cmd_revoke))
    app.add_handler(CallbackQueryHandler(h.on_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.USERS_SHARED, h.on_users_shared))
    app.add_handler(MessageHandler(filters.Document.ALL, h.on_document))
    app.add_error_handler(_on_error)

    return app
