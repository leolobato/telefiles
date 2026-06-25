from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telefiles.navigation import (
    Location, list_entries, paginate,
    cb_share, cb_dir, cb_file, cb_page, CB_UP, CB_HOME,
)
from telefiles.shares import Shares


def build_share_picker(shares: Shares) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📂 {name}", callback_data=cb_share(name))]
            for name in shares.names()]
    return InlineKeyboardMarkup(rows or [[InlineKeyboardButton("(no shares)", callback_data=CB_HOME)]])


def build_browser(shares: Shares, loc: Location, page: int):
    dirs, files = list_entries(shares, loc)
    entries = [("d", d) for d in dirs] + [("f", f) for f in files]
    page_entries, page, total_pages = paginate(entries, page)

    page_dirs = [name for kind, name in page_entries if kind == "d"]
    page_files = [name for kind, name in page_entries if kind == "f"]

    rows: list[list[InlineKeyboardButton]] = []
    for idx, (kind, name) in enumerate(page_entries):
        if kind == "d":
            rows.append([InlineKeyboardButton(f"📁 {name}", callback_data=cb_dir(idx))])
        else:
            rows.append([InlineKeyboardButton(f"📄 {name}", callback_data=cb_file(idx))])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=cb_page(page - 1)))
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=cb_page(page)))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=cb_page(page + 1)))
        rows.append(nav)

    bottom = []
    if loc.relpath:
        bottom.append(InlineKeyboardButton("⬆️ ..", callback_data=CB_UP))
    bottom.append(InlineKeyboardButton("🏠 Shares", callback_data=CB_HOME))
    rows.append(bottom)

    display = loc.share if not loc.relpath else f"{loc.share}/{loc.relpath}"
    header = f"📂 {display}"
    return header, InlineKeyboardMarkup(rows), page_dirs, page_files
