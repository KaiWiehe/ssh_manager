"""File browser checks use temporary files only; no native dialogs or user data."""
import tkinter as tk
import time

import pytest

from ssh_manager_app import file_picker


def loaded(root, picker):
    deadline = time.monotonic() + 5
    while picker._loading and time.monotonic() < deadline:
        root.update()
        time.sleep(0.001)
    assert not picker._loading


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    window.withdraw()
    yield window
    window.destroy()


def test_filters_include_extensionless_all_files_and_multiple_patterns():
    assert file_picker._matches("README", ("*.*",))
    assert file_picker._matches("RUN.PY", file_picker._patterns("*.sh *.bash *.py"))
    assert not file_picker._matches("private.txt", ("*.json",))


def test_open_browser_keeps_root_usable_during_wait(root, tmp_path):
    existing = tmp_path / "source.json"
    existing.write_text("{}")
    handled = []
    button = tk.Button(root, command=lambda: handled.append("root callback"))

    def select():
        picker = next(child for child in root.winfo_children() if isinstance(child, file_picker.FilePicker))
        assert picker.grab_current() is None
        assert not picker.transient()
        assert not picker.attributes("-topmost")
        button.invoke()
        picker.name_text.set(existing.name)
        picker._accept()

    root.after(20, select)
    result = file_picker.askopenfilename(parent=root, initialdir=tmp_path)
    assert result == str(existing)
    assert handled == ["root callback"]


def test_open_rejects_missing_file_and_navigates_directory(root, tmp_path):
    subdir = tmp_path / "folder"
    subdir.mkdir()
    picker = file_picker.FilePicker(root, initialdir=tmp_path)
    picker.name_text.set("missing.txt")
    picker._accept()
    assert picker.winfo_exists()
    assert "vorhandene" in picker.status_text.get()
    picker.name_text.set("folder")
    picker._accept()
    assert picker._directory == subdir
    picker.destroy()


def test_filter_retains_directories_and_allows_manual_other_extension(root, tmp_path):
    (tmp_path / "folder").mkdir()
    (tmp_path / "data.json").write_text("{}")
    text = tmp_path / "data.txt"
    text.write_text("text")
    picker = file_picker.FilePicker(root, initialdir=tmp_path, filetypes=[("JSON", "*.json")])
    loaded(root, picker)
    assert {path.name for path in picker._paths.values()} == {"folder", "data.json"}
    picker.name_text.set(text.name)
    picker._accept()
    assert picker.result == str(text)


def test_multiple_selection_preserves_spaces_and_braces(root, tmp_path):
    names = ["one two.txt", "brace{three}.txt"]
    for name in names:
        (tmp_path / name).write_text("test")
    picker = file_picker.FilePicker(root, initialdir=tmp_path, multiple=True)
    loaded(root, picker)
    picker.tree.selection_set(picker.tree.get_children())
    picker._selected()
    picker._accept()
    assert set(picker.result) == {str(tmp_path / name) for name in names}


def test_save_extension_and_overwrite_confirmation(root, tmp_path):
    target = tmp_path / "backup.json"
    target.write_text("original")
    picker = file_picker.FilePicker(root, initialdir=tmp_path, save=True, defaultextension=".json")
    picker.name_text.set("backup")
    picker._accept()
    assert picker.winfo_exists()
    assert picker.accept_button.cget("text") == "Überschreiben"
    # Changing the name invalidates the confirmation for the previous target.
    picker.name_text.set("other")
    assert picker._overwrite_path is None
    picker.name_text.set("backup")
    picker._accept()
    assert picker.winfo_exists()
    picker._accept()
    assert picker.result == str(target)
    assert target.read_text() == "original"


def test_save_missing_parent_rejected_and_explicit_extension_preserved(root, tmp_path):
    picker = file_picker.FilePicker(root, initialdir=tmp_path, save=True, defaultextension=".json")
    picker.name_text.set("missing/name")
    picker._accept()
    assert picker.winfo_exists()
    assert "Zielordner" in picker.status_text.get()
    picker.name_text.set("explicit.txt")
    picker._accept()
    assert picker.result == str(tmp_path / "explicit.txt")
    assert not (tmp_path / "explicit.txt").exists()


def test_picker_survives_origin_window_close_and_cancel(root, tmp_path):
    source = tk.Toplevel(root)
    picker = file_picker.FilePicker(source, initialdir=tmp_path)
    source.destroy()
    assert picker.winfo_exists()
    picker.destroy()
    assert picker.result == ""
    multiple = file_picker.FilePicker(root, initialdir=tmp_path, multiple=True)
    multiple.destroy()
    assert multiple.result == ()


def test_slow_old_directory_listing_cannot_replace_newer_navigation(root, tmp_path, monkeypatch):
    jobs = []
    monkeypatch.setattr(file_picker, "run_worker", lambda owner, work, success, failure: jobs.append((work, success, failure)))
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "old.txt").write_text("old")
    (second / "new.txt").write_text("new")
    picker = file_picker.FilePicker(root, initialdir=first)
    assert picker._loading
    picker._navigate(second)
    jobs[1][1](jobs[1][0]())
    jobs[0][1](jobs[0][0]())
    assert not picker._loading
    assert {path.name for path in picker._paths.values()} == {"new.txt"}
    assert picker.path_text.get() == str(second)
    picker.destroy()


def test_waiting_file_request_cancels_when_origin_is_closed(root, tmp_path):
    source = tk.Toplevel(root)
    root.after(20, source.destroy)
    assert file_picker.askopenfilenames(parent=source, initialdir=tmp_path) == ()
    assert not any(isinstance(child, file_picker.FilePicker) for child in root.winfo_children())


def test_closing_entire_application_cancels_file_request():
    root = tk.Tk()
    root.withdraw()
    root.after(20, root.destroy)
    assert file_picker.askopenfilename(parent=root) == ""
