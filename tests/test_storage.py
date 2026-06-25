from telefiles.storage import load_allowlist, save_allowlist


def test_load_missing_returns_empty(tmp_path):
    assert load_allowlist(tmp_path / "nope.json") == {}


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "sub" / "allow.json"
    data = {"123": "alice", "456": "bob"}
    save_allowlist(p, data)
    assert p.exists()
    assert load_allowlist(p) == data


def test_save_overwrites_atomically(tmp_path):
    p = tmp_path / "allow.json"
    save_allowlist(p, {"1": "a"})
    save_allowlist(p, {"2": "b"})
    assert load_allowlist(p) == {"2": "b"}
    # no leftover temp files
    assert [f.name for f in tmp_path.iterdir()] == ["allow.json"]
