import zipfile
import pytest
from unittest.mock import AsyncMock, MagicMock

from telefiles import handlers
from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.navigation import Location
from telefiles.handlers import BotState, cmd_zip


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
    msg.reply_document = AsyncMock()
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_message = msg
    return update, msg


def make_ctx(state):
    ctx = MagicMock()
    ctx.bot_data = {"state": state}
    ctx.args = []
    return ctx


@pytest.mark.asyncio
async def test_zip_requires_share_selected(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location()  # picker
    update, msg = make_update(42)
    await cmd_zip(update, make_ctx(state))
    msg.reply_document.assert_not_awaited()
    assert "share" in msg.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_zip_sends_archive_of_current_folder(tmp_path):
    state = build_state(tmp_path)
    (tmp_path / "share" / "a.txt").write_text("aaa")
    (tmp_path / "share" / "sub").mkdir()
    (tmp_path / "share" / "sub" / "b.txt").write_text("bbb")
    state.locations[42] = Location("S", "")

    sent = {}

    async def capture(document, filename):
        sent["filename"] = filename
        sent["names"] = zipfile.ZipFile(document).namelist()

    update, msg = make_update(42)
    msg.reply_document.side_effect = capture
    await cmd_zip(update, make_ctx(state))

    msg.reply_document.assert_awaited_once()
    assert sent["filename"] == "S.zip"
    assert sorted(sent["names"]) == ["a.txt", "sub/b.txt"]


@pytest.mark.asyncio
async def test_zip_uses_subfolder_name(tmp_path):
    state = build_state(tmp_path)
    (tmp_path / "share" / "docs").mkdir()
    (tmp_path / "share" / "docs" / "x.txt").write_text("x")
    state.locations[42] = Location("S", "docs")

    update, msg = make_update(42)
    await cmd_zip(update, make_ctx(state))

    assert msg.reply_document.await_args.kwargs["filename"] == "docs.zip"


@pytest.mark.asyncio
async def test_zip_empty_folder_is_reported(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "")
    update, msg = make_update(42)
    await cmd_zip(update, make_ctx(state))
    msg.reply_document.assert_not_awaited()
    assert "empty" in msg.reply_text.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_zip_refuses_when_over_size_cap(tmp_path, monkeypatch):
    state = build_state(tmp_path)
    (tmp_path / "share" / "a.txt").write_text("data")
    state.locations[42] = Location("S", "")
    monkeypatch.setattr(handlers, "MAX_SEND_BYTES", 1)

    update, msg = make_update(42)
    await cmd_zip(update, make_ctx(state))

    msg.reply_document.assert_not_awaited()
    assert "50 mb" in msg.reply_text.await_args.args[0].lower()
