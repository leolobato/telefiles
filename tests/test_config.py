import pytest
from telefiles.config import load_config, ConfigError


def test_load_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("shares:\n  Docs: /srv/docs\n  Photos: /mnt/photos\n")
    env = {"BOT_TOKEN": "T", "ADMIN_ID": "555", "DATA_DIR": str(tmp_path / "data")}
    cfg = load_config(env, cfg_file)
    assert cfg.token == "T"
    assert cfg.admin_id == 555
    assert cfg.data_dir == tmp_path / "data"
    assert cfg.shares.names() == ["Docs", "Photos"]


def test_load_shares_from_env(tmp_path):
    env = {
        "BOT_TOKEN": "T",
        "ADMIN_ID": "5",
        "SHARES": "A:/a,B:/b",
        "DATA_DIR": str(tmp_path),
    }
    cfg = load_config(env, None)
    assert cfg.shares.names() == ["A", "B"]


def test_missing_token_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config({"ADMIN_ID": "5", "SHARES": "A:/a"}, None)


def test_bad_admin_id_raises():
    with pytest.raises(ConfigError):
        load_config({"BOT_TOKEN": "T", "ADMIN_ID": "notnum", "SHARES": "A:/a"}, None)


def test_no_shares_raises():
    with pytest.raises(ConfigError):
        load_config({"BOT_TOKEN": "T", "ADMIN_ID": "5"}, None)
