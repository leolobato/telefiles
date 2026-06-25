import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.navigation import Location
from telefiles.handlers import BotState, cmd_upload, on_document


def build_state(tmp_path):
    (tmp_path / "share").mkdir()
    shares = Shares({"S": str(tmp_path / "share")})
    cfg = Config(token="T", admin_id=1, data_dir=tmp_path, shares=shares)
    auth = Auth(tmp_path / "allow.json", admin_id=1)
    auth.add_user(42, "u")
    return BotState(config=cfg, auth=auth)


def make_update(user_id, document=None):
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    msg.document = document
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
async def test_upload_requires_share_selected(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location()  # picker
    update, msg = make_update(42)
    await cmd_upload(update, make_ctx(state))
    assert 42 not in state.awaiting_upload


@pytest.mark.asyncio
async def test_upload_sets_awaiting(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "")
    update, msg = make_update(42)
    await cmd_upload(update, make_ctx(state))
    assert 42 in state.awaiting_upload


@pytest.mark.asyncio
async def test_document_saved_to_current_dir(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "")
    state.awaiting_upload.add(42)

    tg_file = MagicMock()
    async def fake_download(custom_path):
        Path(custom_path).write_text("data")
    tg_file.download_to_drive = AsyncMock(side_effect=fake_download)

    document = MagicMock()
    document.file_name = "../evil.txt"
    document.file_size = 10
    document.get_file = AsyncMock(return_value=tg_file)

    update, msg = make_update(42, document=document)
    await on_document(update, make_ctx(state))

    saved = tmp_path / "share" / "evil.txt"
    assert saved.exists()
    assert 42 not in state.awaiting_upload


@pytest.mark.asyncio
async def test_document_rejected_when_too_large(tmp_path):
    state = build_state(tmp_path)
    state.locations[42] = Location("S", "")
    state.awaiting_upload.add(42)
    document = MagicMock()
    document.file_name = "big.bin"
    document.file_size = 999 * 1024 * 1024
    update, msg = make_update(42, document=document)
    await on_document(update, make_ctx(state))
    assert not (tmp_path / "share" / "big.bin").exists()
