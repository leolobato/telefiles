from __future__ import annotations

from pathlib import Path

from telefiles.storage import load_allowlist, save_allowlist


class Auth:
    def __init__(self, allowlist_path: Path, admin_id: int) -> None:
        self._path = allowlist_path
        self._admin_id = admin_id
        self._allow = load_allowlist(allowlist_path)

    def is_admin(self, user_id: int) -> bool:
        return user_id == self._admin_id

    def is_paired(self, user_id: int) -> bool:
        # The admin is always authorized — no need to be added explicitly.
        return self.is_admin(user_id) or str(user_id) in self._allow

    def add_user(self, user_id: int, label: str) -> bool:
        key = str(user_id)
        if self.is_admin(user_id) or key in self._allow:
            return False
        self._allow[key] = label or ""
        save_allowlist(self._path, self._allow)
        return True

    def revoke(self, user_id: int) -> bool:
        if str(user_id) not in self._allow:
            return False
        del self._allow[str(user_id)]
        save_allowlist(self._path, self._allow)
        return True

    def users(self) -> dict[str, str]:
        return dict(self._allow)
