import pytest
from telefiles.auth import Auth


@pytest.fixture
def auth(tmp_path):
    return Auth(tmp_path / "allow.json", admin_id=999)


def test_admin_recognized(auth):
    assert auth.is_admin(999)
    assert not auth.is_admin(1)


def test_admin_is_implicitly_paired(auth):
    assert auth.is_paired(999)
    assert "999" not in auth.users()
    assert not auth.is_paired(1)


def test_add_user_adds_and_persists(auth, tmp_path):
    assert auth.add_user(42, "@alice") is True
    assert auth.is_paired(42)
    assert auth.users()["42"] == "@alice"
    reloaded = Auth(tmp_path / "allow.json", admin_id=999)
    assert reloaded.is_paired(42)


def test_add_user_duplicate_returns_false(auth):
    assert auth.add_user(42, "@alice") is True
    assert auth.add_user(42, "@alice") is False


def test_add_user_admin_returns_false(auth):
    assert auth.add_user(999, "@boss") is False
    assert "999" not in auth.users()


def test_revoke(auth):
    auth.add_user(42, "@alice")
    assert auth.revoke(42) is True
    assert not auth.is_paired(42)
    assert auth.revoke(42) is False
