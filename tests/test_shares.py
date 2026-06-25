import os
import pytest
from telefiles.shares import Shares, ShareError


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "share"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "file.txt").write_text("hi")
    return root


def test_names_sorted():
    s = Shares({"Zed": "/z", "Apple": "/a"})
    assert s.names() == ["Apple", "Zed"]


def test_resolve_root_and_subpath(tree):
    s = Shares({"S": str(tree)})
    assert s.resolve("S") == tree.resolve()
    assert s.resolve("S", "sub/file.txt") == (tree / "sub" / "file.txt").resolve()


def test_unknown_share_raises(tree):
    s = Shares({"S": str(tree)})
    with pytest.raises(ShareError):
        s.resolve("Nope")


def test_dotdot_escape_blocked(tree):
    s = Shares({"S": str(tree)})
    with pytest.raises(ShareError):
        s.resolve("S", "../secret")


def test_absolute_relpath_blocked(tree):
    s = Shares({"S": str(tree)})
    with pytest.raises(ShareError):
        s.resolve("S", "/etc/passwd")


def test_symlink_escape_blocked(tree, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    link = tree / "link"
    os.symlink(outside, link)
    s = Shares({"S": str(tree)})
    with pytest.raises(ShareError):
        s.resolve("S", "link/secret.txt")


def test_empty_share_name_rejected():
    with pytest.raises(ShareError):
        Shares({"": "/x"})
