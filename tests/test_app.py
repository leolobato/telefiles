from pathlib import Path
from telefiles.config import Config
from telefiles.shares import Shares
from telefiles.app import build_application


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
