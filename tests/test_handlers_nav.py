import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.navigation import Location, cb_share, cb_dir, CB_HOME
from telefiles.handlers import BotState, on_callback


def build_state(tmp_path):
    (tmp_path / "share" / "sub").mkdir(parents=True)
    (tmp_path / "share" / "sub" / "f.txt").write_text("hello")
    shares = Shares({"S": str(tmp_path / "share")})
    cfg = Config(token="T", admin_id=1, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=1)
    auth.try_pair(42, "u", auth.pairing_code)
    return BotState(config=cfg, auth=auth)


def make_cb_update(user_id, data):
    q = MagicMock()
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message = MagicMock()
    q.message.reply_document = AsyncMock()
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query = q
    return update, q


def make_ctx(state):
    ctx = MagicMock()
    ctx.bot_data = {"state": state}
    return ctx


@pytest.mark.asyncio
async def test_enter_share_renders_browser(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location()
    update, q = make_cb_update(42, cb_share("S"))
    await on_callback(update, make_ctx(state))
    q.answer.assert_awaited()
    q.edit_message_text.assert_awaited()
    assert state.locations[42].share == "S"


@pytest.mark.asyncio
async def test_home_returns_to_picker(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "sub")
    update, q = make_cb_update(42, CB_HOME)
    await on_callback(update, make_ctx(state))
    assert state.locations[42].share is None
