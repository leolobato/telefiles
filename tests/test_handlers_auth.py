import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.handlers import (
    BotState, cmd_pair, on_users_shared, require_auth,
)


def make_state(tmp_path, admin_id=999):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="T", admin_id=admin_id, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=admin_id)
    return BotState(config=cfg, auth=auth)


def make_update(user_id):
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "u"
    update.effective_message = msg
    return update, msg


def make_context(state, args=None):
    ctx = MagicMock()
    ctx.bot_data = {"state": state}
    ctx.args = args or []
    return ctx


@pytest.mark.asyncio
async def test_require_auth_blocks_unpaired(tmp_path):
    state = make_state(tmp_path)
    called = {"yes": False}

    @require_auth
    async def handler(update, context):
        called["yes"] = True

    update, msg = make_update(42)
    ctx = make_context(state)
    await handler(update, ctx)
    assert called["yes"] is False
    msg.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_pair_denied_for_non_admin(tmp_path):
    state = make_state(tmp_path, admin_id=999)
    update, msg = make_update(42)  # not the admin
    await cmd_pair(update, make_context(state))
    msg.reply_text.assert_awaited()
    # the denial carries no request-users keyboard
    _, kwargs = msg.reply_text.call_args
    assert kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_pair_shows_user_picker_for_admin(tmp_path):
    state = make_state(tmp_path, admin_id=999)
    update, msg = make_update(999)
    await cmd_pair(update, make_context(state))
    msg.reply_text.assert_awaited()
    _, kwargs = msg.reply_text.call_args
    markup = kwargs["reply_markup"]
    button = markup.keyboard[0][0]
    assert button.request_users is not None
    assert button.request_users.user_is_bot is False


@pytest.mark.asyncio
async def test_users_shared_adds_users_for_admin(tmp_path):
    state = make_state(tmp_path, admin_id=999)
    update, msg = make_update(999)  # admin
    update.effective_message.users_shared = SimpleNamespace(
        users=[SimpleNamespace(user_id=42, username="alice", first_name="Al", last_name=None)]
    )
    await on_users_shared(update, make_context(state))
    assert state.auth.is_paired(42)
    assert state.auth.users()["42"] == "@alice"
    msg.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_users_shared_denied_for_non_admin(tmp_path):
    state = make_state(tmp_path, admin_id=999)
    update, msg = make_update(42)  # non-admin, not paired
    update.effective_message.users_shared = SimpleNamespace(
        users=[SimpleNamespace(user_id=7, username="x", first_name="X", last_name=None)]
    )
    await on_users_shared(update, make_context(state))
    assert not state.auth.is_paired(7)  # not added
