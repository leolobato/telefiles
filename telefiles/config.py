from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from telefiles.shares import Shares, ShareError


class ConfigError(Exception):
    pass


@dataclass
class Config:
    token: str
    admin_id: int
    data_dir: Path
    shares: Shares


def _parse_shares_env(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in value.split(","):
        pair = pair.strip()
        if not pair:
            continue
        name, sep, path = pair.partition(":")
        if not sep or not name.strip() or not path.strip():
            raise ConfigError(f"invalid SHARES entry: {pair!r}")
        out[name.strip()] = path.strip()
    return out


def load_config(env: dict[str, str], config_path: Path | None) -> Config:
    token = env.get("BOT_TOKEN")
    if not token:
        raise ConfigError("BOT_TOKEN is required")

    admin_raw = env.get("ADMIN_ID")
    if not admin_raw:
        raise ConfigError("ADMIN_ID is required")
    try:
        admin_id = int(admin_raw)
    except ValueError:
        raise ConfigError(f"ADMIN_ID must be an integer, got {admin_raw!r}")

    data_dir = Path(env.get("DATA_DIR", "./data"))

    shares_map: dict[str, str] = {}
    if config_path is not None and config_path.exists():
        loaded = yaml.safe_load(config_path.read_text()) or {}
        shares_map = dict((loaded.get("shares") or {}))
    elif env.get("SHARES"):
        shares_map = _parse_shares_env(env["SHARES"])

    if not shares_map:
        raise ConfigError("no shares configured (config.yaml or SHARES env)")

    try:
        shares = Shares(shares_map)
    except ShareError as exc:
        raise ConfigError(str(exc))

    return Config(token=token, admin_id=admin_id, data_dir=data_dir, shares=shares)
