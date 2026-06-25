import types
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.handlers import BotState, cmd_pair, cmd_start, require_auth


def make_state(tmp_path, admin_id=999):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="T", admin_id=admin_id, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=admin_id)
    return BotState(config=cfg, auth=auth)


def make_update(user_id, args_text=None):
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
async def test_pair_with_correct_code(tmp_path):
    state = make_state(tmp_path)
    code = state.auth.pairing_code
    update, msg = make_update(42)
    ctx = make_context(state, args=[code])
    await cmd_pair(update, ctx)
    assert state.auth.is_paired(42)
    msg.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_pair_with_wrong_code(tmp_path):
    state = make_state(tmp_path)
    update, msg = make_update(42)
    ctx = make_context(state, args=["bad"])
    await cmd_pair(update, ctx)
    assert not state.auth.is_paired(42)
    msg.reply_text.assert_awaited()


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
async def test_admin_command_denied_for_non_admin(tmp_path):
    from telefiles.handlers import cmd_newcode
    state = make_state(tmp_path, admin_id=999)
    # pair a non-admin user (id 42 != admin 999)
    state.auth.try_pair(42, "alice", state.auth.pairing_code)
    code_before = state.auth.pairing_code
    update, msg = make_update(42)
    ctx = make_context(state)
    await cmd_newcode(update, ctx)
    # body did not run: code unchanged, and a denial was sent
    assert state.auth.pairing_code == code_before
    msg.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_admin_command_allowed_for_admin(tmp_path):
    from telefiles.handlers import cmd_newcode
    state = make_state(tmp_path, admin_id=999)
    code_before = state.auth.pairing_code
    update, msg = make_update(999)
    ctx = make_context(state)
    await cmd_newcode(update, ctx)
    # admin rotates the code
    assert state.auth.pairing_code != code_before
    msg.reply_text.assert_awaited()
