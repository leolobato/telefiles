from __future__ import annotations

import functools
from dataclasses import dataclass, field

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.keyboards import build_browser, build_share_picker
from telefiles.navigation import Location, parse_cb, CB_UP, CB_HOME
from telefiles.shares import ShareError


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


MAX_SEND_BYTES = 50 * 1024 * 1024


def _loc(state: BotState, user_id: int) -> Location:
    return state.locations.setdefault(user_id, Location())


async def _render_browser(query, state: BotState, loc: Location, page: int = 0):
    header, markup, page_dirs, page_files = build_browser(state.config.shares, loc, page)
    await query.edit_message_text(header, reply_markup=markup)
    return page_dirs, page_files


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = _state(context)
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if not state.auth.is_paired(user_id):
        await query.edit_message_text("⛔ Not authorized.")
        return

    kind, value = parse_cb(query.data)
    loc = _loc(state, user_id)

    try:
        if kind == "home":
            state.locations[user_id] = Location()
            await query.edit_message_text(
                "📂 Choose a share:",
                reply_markup=build_share_picker(state.config.shares),
            )
            return

        if kind == "s":
            loc = Location(value, "")
            state.locations[user_id] = loc
            await _render_browser(query, state, loc)
            return

        if kind == "up":
            parent = "/".join(loc.relpath.split("/")[:-1]) if loc.relpath else ""
            loc = Location(loc.share, parent)
            state.locations[user_id] = loc
            await _render_browser(query, state, loc)
            return

        if kind == "p":
            await _render_browser(query, state, loc, page=int(value))
            return

        if kind in ("d", "f"):
            # recompute the page the buttons were drawn from to map index -> name
            page_dirs, page_files = await _render_browser(query, state, loc)
            entries = page_dirs + page_files
            index = int(value)
            if index >= len(entries):
                return
            name = entries[index]
            if kind == "d":
                child = f"{loc.relpath}/{name}".strip("/")
                loc = Location(loc.share, child)
                state.locations[user_id] = loc
                await _render_browser(query, state, loc)
            else:
                await _send_file(query, state, loc, name)
            return
    except ShareError:
        await query.edit_message_text("⚠️ Invalid path.")


async def _send_file(query, state: BotState, loc: Location, name: str):
    path = state.config.shares.resolve(loc.share, f"{loc.relpath}/{name}".strip("/"))
    if not path.is_file():
        await query.message.reply_text("⚠️ Not a file.")
        return
    if path.stat().st_size > MAX_SEND_BYTES:
        await query.message.reply_text("⚠️ File too large for Telegram (max 50 MB).")
        return
    try:
        with path.open("rb") as fh:
            await query.message.reply_document(document=fh, filename=name)
    except TelegramError:
        await query.message.reply_text("⚠️ Failed to send file.")
