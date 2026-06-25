from telefiles.files import sanitize_filename, unique_path


def test_sanitize_strips_path_components():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/a/b/c.txt") == "c.txt"
    assert sanitize_filename("plain.txt") == "plain.txt"


def test_sanitize_empty_falls_back():
    assert sanitize_filename("") == "file"
    assert sanitize_filename("/") == "file"


def test_sanitize_strips_windows_backslash_components():
    # Backslash-separated paths from Windows clients must not survive as path
    # components on a POSIX host (directory-escape control).
    assert sanitize_filename("a\\b\\c.txt") == "c.txt"
    assert sanitize_filename("\\") == "file"


def test_sanitize_strips_unsafe_characters():
    assert sanitize_filename("bad<name>.txt") == "badname.txt"
    assert sanitize_filename('a"b|c?.txt') == "abc.txt"


def test_unique_path_no_collision(tmp_path):
    assert unique_path(tmp_path, "a.txt") == tmp_path / "a.txt"


def test_unique_path_with_collision(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert unique_path(tmp_path, "a.txt") == tmp_path / "a (1).txt"
    (tmp_path / "a (1).txt").write_text("x")
    assert unique_path(tmp_path, "a.txt") == tmp_path / "a (2).txt"


def test_unique_path_no_extension(tmp_path):
    (tmp_path / "README").write_text("x")
    assert unique_path(tmp_path, "README") == tmp_path / "README (1)"
