import pytest
from telegram import InlineKeyboardMarkup
from telefiles.shares import Shares
from telefiles.navigation import Location, parse_cb, CB_HOME, CB_UP
from telefiles.keyboards import build_share_picker, build_browser


@pytest.fixture
def shares(tmp_path):
    root = tmp_path / "share"
    (root / "dir1").mkdir(parents=True)
    (root / "f.txt").write_text("x")
    return Shares({"S": str(root)})


def _all_buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def test_share_picker_lists_shares(shares):
    markup = build_share_picker(shares)
    labels = [b.text for b in _all_buttons(markup)]
    assert any("S" in t for t in labels)


def test_browser_at_root_has_no_up_button(shares):
    text, markup, dirs, files = build_browser(shares, Location("S", ""), page=0)
    datas = [b.callback_data for b in _all_buttons(markup)]
    assert CB_UP not in datas
    assert CB_HOME in datas
    assert dirs == ["dir1"] and files == ["f.txt"]


def test_browser_in_subdir_has_up_button(shares, tmp_path):
    (tmp_path / "share" / "dir1" / "inner").mkdir()
    text, markup, dirs, files = build_browser(shares, Location("S", "dir1"), page=0)
    datas = [b.callback_data for b in _all_buttons(markup)]
    assert CB_UP in datas
