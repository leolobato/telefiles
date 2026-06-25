from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import BotCommandScopeChat
from telegram.ext import CommandHandler

from telefiles.auth import Auth
from telefiles.config import Config
from telefiles.handlers import BotState
from telefiles.shares import Shares
from telefiles.app import (
    build_application, _register_commands, PUBLIC_COMMANDS, ADMIN_COMMANDS,
)


def test_build_application_registers_handlers(tmp_path):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="123:abc", admin_id=1, data_dir=tmp_path, shares=shares)
    app = build_application(cfg)
    # state is wired
    assert "state" in app.bot_data
    assert app.bot_data["state"].config is cfg
    # at least one handler group registered
    assert app.handlers
    total = sum(len(hs) for hs in app.handlers.values())
    assert total >= 9


def test_post_init_registers_commands(tmp_path):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="123:abc", admin_id=1, data_dir=tmp_path, shares=shares)
    app = build_application(cfg)
    assert app.post_init is _register_commands


def test_command_lists_cover_every_registered_command(tmp_path):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="123:abc", admin_id=1, data_dir=tmp_path, shares=shares)
    app = build_application(cfg)
    registered = set()
    for hs in app.handlers.values():
        for handler in hs:
            if isinstance(handler, CommandHandler):
                registered |= set(handler.commands)
    described = {c.command for c in ADMIN_COMMANDS}
    assert registered == described


@pytest.mark.asyncio
async def test_register_commands_sets_default_and_admin_scope(tmp_path):
    shares = Shares({"S": str(tmp_path)})
    cfg = Config(token="t", admin_id=4242, data_dir=tmp_path, shares=shares)
    app = MagicMock()
    app.bot.set_my_commands = AsyncMock()
    app.bot_data = {"state": BotState(config=cfg, auth=Auth(tmp_path / "a.json", 4242))}

    await _register_commands(app)

    calls = app.bot.set_my_commands.await_args_list
    assert len(calls) == 2
    # default scope: public commands, no scope kwarg
    assert calls[0].args[0] == PUBLIC_COMMANDS
    assert "scope" not in calls[0].kwargs
    # admin scope: full list, scoped to the admin's chat
    assert calls[1].args[0] == ADMIN_COMMANDS
    scope = calls[1].kwargs["scope"]
    assert isinstance(scope, BotCommandScopeChat)
    assert scope.chat_id == 4242
