import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import telefiles.handlers as h
from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.navigation import Location, cb_share, cb_dir, cb_file, CB_HOME
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


@pytest.mark.asyncio
async def test_file_on_page1_maps_to_correct_entry(tmp_path):
    """Bug guard: tapping f|0 on page 1 must send the 21st file, not the 1st."""
    share_root = tmp_path / "share2"
    share_root.mkdir()
    # Create 25 files with no subdirs so files start at index 0 of the page slice
    names = [f"f{i:02d}.txt" for i in range(25)]
    for n in names:
        (share_root / n).write_text("x")

    shares = Shares({"S2": str(share_root)})
    cfg = Config(token="T", admin_id=1, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow2.json", admin_id=1)
    auth.try_pair(42, "u", auth.pairing_code)
    state = BotState(config=cfg, auth=auth)

    # Page 1 (0-indexed), file index 0 on that page = the 21st file in sorted order
    sorted_names = sorted(names, key=str.lower)
    expected_name = sorted_names[20]  # index 20 = first file on page 1

    state.locations[42] = Location("S2", "", page=1)
    update, q = make_cb_update(42, cb_file(0))
    await on_callback(update, make_ctx(state))

    q.message.reply_document.assert_awaited_once()
    _, kwargs = q.message.reply_document.call_args
    assert kwargs["filename"] == expected_name


@pytest.mark.asyncio
async def test_oversized_file_refused(tmp_path):
    """Files over MAX_SEND_BYTES must be refused with a reply_text, not sent."""
    share_root = tmp_path / "share"
    share_root.mkdir(parents=True, exist_ok=True)
    big_file = share_root / "big.bin"
    big_file.write_bytes(b"x" * 10)  # small bytes; we shrink the limit instead

    shares = Shares({"S": str(share_root)})
    cfg = Config(token="T", admin_id=1, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=1)
    auth.try_pair(42, "u", auth.pairing_code)
    state = BotState(config=cfg, auth=auth)
    state.locations[42] = Location("S", "", page=0)

    update, q = make_cb_update(42, cb_file(0))
    q.message.reply_text = AsyncMock()

    original = h.MAX_SEND_BYTES
    try:
        h.MAX_SEND_BYTES = 5  # file is 10 bytes, so it will be refused
        await on_callback(update, make_ctx(state))
    finally:
        h.MAX_SEND_BYTES = original

    q.message.reply_document.assert_not_awaited()
    q.message.reply_text.assert_awaited()


@pytest.mark.asyncio
async def test_unauthorized_callback_denied(tmp_path):
    """A non-paired user's callback must be rejected at the auth gate."""
    state = build_state(tmp_path)
    # user 999 is not paired
    update, q = make_cb_update(999, cb_share("S"))
    await on_callback(update, make_ctx(state))

    q.answer.assert_awaited()
    q.edit_message_text.assert_awaited()
    # The user must not have been navigated into a share
    assert 999 not in state.locations or state.locations.get(999, Location()).share is None
