from __future__ import annotations

import secrets
from pathlib import Path

from telefiles.storage import load_allowlist, save_allowlist


def _generate_code() -> str:
    return secrets.token_hex(4)  # 8 hex chars


class Auth:
    def __init__(self, allowlist_path: Path, admin_id: int) -> None:
        self._path = allowlist_path
        self._admin_id = admin_id
        self._allow = load_allowlist(allowlist_path)
        self._code = _generate_code()

    @property
    def pairing_code(self) -> str:
        return self._code

    def new_code(self) -> str:
        self._code = _generate_code()
        return self._code

    def is_admin(self, user_id: int) -> bool:
        return user_id == self._admin_id

    def is_paired(self, user_id: int) -> bool:
        # The admin is always authorized — no need to /pair themselves.
        return self.is_admin(user_id) or str(user_id) in self._allow

    def try_pair(self, user_id: int, username: str, code: str) -> bool:
        if not secrets.compare_digest(code, self._code):
            return False
        self._allow[str(user_id)] = username or ""
        save_allowlist(self._path, self._allow)
        self.new_code()
        return True

    def revoke(self, user_id: int) -> bool:
        if str(user_id) not in self._allow:
            return False
        del self._allow[str(user_id)]
        save_allowlist(self._path, self._allow)
        return True

    def users(self) -> dict[str, str]:
        return dict(self._allow)
