from __future__ import annotations

import functools
from dataclasses import dataclass, field

from telegram import Update
from telegram.ext import ContextTypes

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.keyboards import build_share_picker
from telefiles.navigation import Location


@dataclass
class BotState:
    config: Config
    auth: Auth
    locations: dict[int, Location] = field(default_factory=dict)
    awaiting_upload: set[int] = field(default_factory=set)


def _state(context: ContextTypes.DEFAULT_TYPE) -> BotState:
    return context.bot_data["state"]


def require_auth(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = _state(context)
        user_id = update.effective_user.id
        if not state.auth.is_paired(user_id):
            await update.effective_message.reply_text("⛔ Not authorized.")
            return
        return await handler(update, context)
    return wrapper


def require_admin(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        state = _state(context)
        if not state.auth.is_admin(update.effective_user.id):
            await update.effective_message.reply_text("⛔ Admin only.")
            return
        return await handler(update, context)
    return wrapper


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    user_id = update.effective_user.id
    if not state.auth.is_paired(user_id):
        await update.effective_message.reply_text(
            "👋 You are not paired. Send /pair <code> to get access."
        )
        return
    state.locations[user_id] = Location()
    await update.effective_message.reply_text(
        "📂 Choose a share:", reply_markup=build_share_picker(state.config.shares)
    )


async def cmd_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    user = update.effective_user
    if not context.args:
        await update.effective_message.reply_text("Usage: /pair <code>")
        return
    if state.auth.try_pair(user.id, user.username or "", context.args[0]):
        await update.effective_message.reply_text("✅ Paired! Send /start to begin.")
    else:
        await update.effective_message.reply_text("❌ Invalid or expired code.")


@require_admin
async def cmd_newcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    code = state.auth.new_code()
    await update.effective_message.reply_text(f"🔑 New pairing code: `{code}`", parse_mode="Markdown")


@require_admin
async def cmd_listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    users = state.auth.users()
    if not users:
        await update.effective_message.reply_text("No paired users.")
        return
    lines = [f"• `{uid}` — {name or '(no username)'}" for uid, name in users.items()]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


@require_admin
async def cmd_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    if not context.args:
        await update.effective_message.reply_text("Usage: /revoke <user_id>")
        return
    try:
        target = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("user_id must be a number.")
        return
    if state.auth.revoke(target):
        await update.effective_message.reply_text(f"✅ Revoked {target}.")
    else:
        await update.effective_message.reply_text("User not found.")
