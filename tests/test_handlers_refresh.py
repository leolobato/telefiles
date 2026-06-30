import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram import InlineKeyboardMarkup

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.navigation import Location
from telefiles.handlers import BotState, cmd_refresh


def build_state(tmp_path):
    (tmp_path / "share").mkdir()
    shares = Shares({"S": str(tmp_path / "share")})
    cfg = Config(token="T", admin_id=1, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=1)
    auth.add_user(42, "u")
    return BotState(config=cfg, auth=auth)


def make_update(user_id):
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_message = msg
    return update, msg


def make_ctx(state):
    ctx = MagicMock()
    ctx.bot_data = {"state": state}
    ctx.args = []
    return ctx


def button_labels(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


@pytest.mark.asyncio
async def test_refresh_lists_current_folder(tmp_path):
    state = build_state(tmp_path)
    (tmp_path / "share" / "a.txt").write_text("x")
    (tmp_path / "share" / "sub").mkdir()
    state.locations[42] = Location("S", "")

    update, msg = make_update(42)
    await cmd_refresh(update, make_ctx(state))

    msg.reply_text.assert_awaited_once()
    markup = msg.reply_text.await_args.kwargs["reply_markup"]
    labels = button_labels(markup)
    assert any("a.txt" in label for label in labels)
    assert any("sub" in label for label in labels)


@pytest.mark.asyncio
async def test_refresh_at_picker_resends_share_picker(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location()  # picker, no share entered

    update, msg = make_update(42)
    await cmd_refresh(update, make_ctx(state))

    msg.reply_text.assert_awaited_once()
    markup = msg.reply_text.await_args.kwargs["reply_markup"]
    assert any("S" in label for label in button_labels(markup))


@pytest.mark.asyncio
async def test_refresh_reflects_file_added_after_entering(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "")
    # File lands on disk after the user is already in the folder.
    (tmp_path / "share" / "late.txt").write_text("x")

    update, msg = make_update(42)
    await cmd_refresh(update, make_ctx(state))

    markup = msg.reply_text.await_args.kwargs["reply_markup"]
    assert any("late.txt" in label for label in button_labels(markup))
