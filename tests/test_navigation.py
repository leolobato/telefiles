import pytest
from telefiles.shares import Shares
from telefiles.navigation import (
    Location, list_entries, paginate, PAGE_SIZE,
    cb_share, cb_dir, cb_file, cb_page, parse_cb, CB_UP, CB_HOME,
)


@pytest.fixture
def shares(tmp_path):
    root = tmp_path / "share"
    (root / "beta").mkdir(parents=True)
    (root / "Alpha").mkdir()
    (root / "z.txt").write_text("z")
    (root / "a.txt").write_text("a")
    return Shares({"S": str(root)})


def test_list_entries_sorted_dirs_then_files(shares):
    dirs, files = list_entries(shares, Location("S", ""))
    assert dirs == ["Alpha", "beta"]
    assert files == ["a.txt", "z.txt"]


def test_paginate_clamps_and_counts():
    items = list(range(45))
    page_items, page, total = paginate(items, page=0, page_size=20)
    assert page_items == list(range(20))
    assert (page, total) == (0, 3)
    page_items, page, total = paginate(items, page=99, page_size=20)
    assert page == 2 and page_items == list(range(40, 45))


def test_paginate_empty_has_one_page():
    page_items, page, total = paginate([], page=0)
    assert page_items == [] and page == 0 and total == 1


def test_callback_roundtrip():
    assert parse_cb(cb_share("Docs")) == ("s", "Docs")
    assert parse_cb(cb_dir(3)) == ("d", "3")
    assert parse_cb(cb_file(7)) == ("f", "7")
    assert parse_cb(cb_page(2)) == ("p", "2")
    assert parse_cb(CB_UP) == ("up", "")
    assert parse_cb(CB_HOME) == ("home", "")


def test_list_entries_picker_raises_shareerror(shares):
    from telefiles.shares import ShareError
    with pytest.raises(ShareError):
        list_entries(shares, Location())
