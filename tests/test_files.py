import zipfile

from telefiles.files import build_zip, sanitize_filename, unique_path


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


def test_build_zip_preserves_recursive_structure(tmp_path):
    root = tmp_path / "folder"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("aaa")
    (root / "sub" / "b.txt").write_text("bbb")
    dest = tmp_path / "out.zip"

    count = build_zip(root, dest)

    assert count == 2
    with zipfile.ZipFile(dest) as zf:
        assert sorted(zf.namelist()) == ["a.txt", "sub/b.txt"]
        assert zf.read("sub/b.txt") == b"bbb"


def test_build_zip_excludes_escaping_symlinks(tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("top secret")
    root = tmp_path / "folder"
    root.mkdir()
    (root / "ok.txt").write_text("ok")
    (root / "leak.txt").symlink_to(outside)  # symlink pointing out of the jail
    dest = tmp_path / "out.zip"

    count = build_zip(root, dest)

    assert count == 1
    with zipfile.ZipFile(dest) as zf:
        assert zf.namelist() == ["ok.txt"]


def test_build_zip_does_not_follow_symlinked_dirs(tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "deep.txt").write_text("nope")
    root = tmp_path / "folder"
    root.mkdir()
    (root / "here.txt").write_text("yes")
    (root / "linkdir").symlink_to(outside, target_is_directory=True)
    dest = tmp_path / "out.zip"

    count = build_zip(root, dest)

    assert count == 1
    with zipfile.ZipFile(dest) as zf:
        assert zf.namelist() == ["here.txt"]


def test_build_zip_empty_folder(tmp_path):
    root = tmp_path / "folder"
    root.mkdir()
    dest = tmp_path / "out.zip"

    assert build_zip(root, dest) == 0
