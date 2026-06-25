import pytest
from telefiles.auth import Auth


@pytest.fixture
def auth(tmp_path):
    return Auth(tmp_path / "allow.json", admin_id=999)


def test_admin_recognized(auth):
    assert auth.is_admin(999)
    assert not auth.is_admin(1)


def test_admin_is_implicitly_paired(auth):
    # The admin is authorized without ever calling /pair (not in the allowlist).
    assert auth.is_paired(999)
    assert "999" not in auth.users()
    # a non-admin, non-paired user is still not authorized
    assert not auth.is_paired(1)


def test_pairing_adds_user_and_persists(auth, tmp_path):
    code = auth.pairing_code
    assert auth.try_pair(42, "alice", code) is True
    assert auth.is_paired(42)
    # persisted across reload
    reloaded = Auth(tmp_path / "allow.json", admin_id=999)
    assert reloaded.is_paired(42)


def test_wrong_code_rejected(auth):
    assert auth.try_pair(42, "alice", "wrong") is False
    assert not auth.is_paired(42)


def test_code_is_single_use(auth):
    code = auth.pairing_code
    assert auth.try_pair(1, "a", code) is True
    # same code no longer works for a second user
    assert auth.try_pair(2, "b", code) is False


def test_new_code_rotates(auth):
    first = auth.pairing_code
    second = auth.new_code()
    assert first != second
    assert auth.pairing_code == second


def test_revoke(auth):
    auth.try_pair(42, "alice", auth.pairing_code)
    assert auth.revoke(42) is True
    assert not auth.is_paired(42)
    assert auth.revoke(42) is False
