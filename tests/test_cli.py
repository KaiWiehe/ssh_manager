from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from ssh_manager_app import storage
from ssh_manager_app.cli_search import SearchFilters, entry_details, fuzzy_score, safe_text, tree_rows
from ssh_manager_app.models import Session, default_settings
from ssh_manager_app.session_catalog import Catalog, CatalogEntry, effective_session


def entry(key="one", name="web-01", folder=("Firma", "Produktion"), source="app", **kwargs):
    return CatalogEntry(Session(key, name, list(folder), "192.0.2.10", source=source), "deploy", **kwargs)


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    for attr, filename in [("_STATE_FILE", "ui_state.json"), ("_APP_SESSIONS_FILE", "app_sessions.json"),
                           ("_NOTES_FILE", "notes.json"), ("_SETTINGS_FILE", "settings.json"),
                           ("_SSH_CONFIG_FILE", "config")]:
        monkeypatch.setattr(storage, attr, tmp_path / filename)
    return tmp_path


def test_fuzzy_multiple_fields_and_preserved_ancestors():
    one = entry(note="Ubuntu Datenbank")
    other = entry("two", "mail", ("Firma", "Test"))
    rows = tree_rows([other, one], "prd wb1 ubnt", SearchFilters())
    assert [row.label for row in rows] == ["Firma", "Produktion", "web-01"]
    assert rows[-1].entry.identity == one.identity
    assert fuzzy_score("xyz", "web-01") is None


def test_folder_filter_uses_segments_not_string_prefix():
    entries = [entry(folder=("Prod",)), entry("two", folder=("Production",))]
    rows = tree_rows(entries, "", SearchFilters(folder=("Prod",)))
    assert [r.entry.session.key for r in rows if r.entry] == ["one"]


def test_combined_filters_alias_source_and_no_virtual_duplicates():
    entries = [entry(favorite=True, recent=True), entry("two", source="ssh_alias", favorite=True),
               entry("three", source="winscp", favorite=True)]
    rows = tree_rows(entries, "", SearchFilters(sources={"app"}, view="favorites"))
    assert [r.entry.session.key for r in rows if r.entry] == ["one", "two"]
    rows = tree_rows(entries, "", SearchFilters(sources={"app"}, view="recent"))
    assert [r.entry.session.key for r in rows if r.entry] == ["one"]


def test_query_reveals_collapsed_ancestors_and_duplicate_names_keep_ids():
    rows = tree_rows([entry(), entry("two", folder=("Firma", "Test"))], "web", SearchFilters(), {("Firma",)})
    assert {r.entry.identity for r in rows if r.entry} == {("app", "one"), ("app", "two")}
    assert all(r.expanded for r in rows)
    assert len(tree_rows([entry()], "", SearchFilters(), {("Firma",)})) == 1


def test_safe_terminal_data_and_full_multiline_notes():
    note = "erste\nzweite\tText\x1b[31mRot\x1b[0m\x1b]0;Titel\x07"
    details = entry_details(entry(note=note))
    assert "erste\nzweite    TextRot" in details
    assert "\x1b" not in details and "\x07" not in details
    assert safe_text("a\nb\r\x00c") == "a b c"
    alias = entry(source="ssh_alias")
    assert "aus SSH-Konfiguration" in entry_details(alias)
    assert "Host: 192.0.2.10" not in entry_details(alias)


def test_user_import_settings_and_override_share_gui_rules():
    settings = default_settings()
    settings.import_settings.winscp_include_username = False
    s = replace(entry(source="winscp").session, username="imported")
    assert effective_session(s, settings, {}).username == ""
    assert effective_session(s, settings, {s.key: "fixed"}).username == "fixed"


def test_catalog_reads_hidden_sources_aliases_and_metadata(isolated_storage, monkeypatch):
    from ssh_manager_app import core, session_catalog, source_status
    settings = default_settings()
    settings.source_visibility.show_app_connections = False
    monkeypatch.setattr(storage, "load_settings", lambda: settings)
    monkeypatch.setattr(storage, "load_ui_state", lambda: (set(), {}, {"favorite_sessions": {"one": False}, "recent_sessions": ["one"]}))
    monkeypatch.setattr(storage, "load_notes", lambda: {"one": "volle Notiz"})
    monkeypatch.setattr(core.RegistryReader, "load_sessions", lambda _: [])
    monkeypatch.setattr(storage, "load_ssh_config_sessions", lambda: [entry("alias", source="ssh_config").session])
    monkeypatch.setattr(storage, "load_filezilla_config_sessions", lambda: [])
    monkeypatch.setattr(storage, "load_app_sessions", lambda: [entry().session])
    catalog = session_catalog.load_catalog()
    assert len(catalog.entries) == 2
    normal = next(e for e in catalog.entries if e.session.key == "one")
    assert normal.favorite and normal.recent and normal.note == "volle Notiz"
    assert normal.user == settings.default_user
    assert next(e for e in catalog.entries if e.session.is_ssh_config_session).user == ""


def test_stale_gui_saves_preserve_cli_recent_and_other_metadata(isolated_storage):
    storage.save_ui_state({"Firma"}, {}, {"recent_sessions": ["old"], "favorite_sessions": {"old": True}})
    expanded, colors, toolbar = storage.load_ui_state()
    storage.record_recent_sessions(["cli"])
    toolbar["main"] = "changed"
    storage.save_ui_state(expanded, colors, toolbar)
    storage.record_recent_sessions(["cli2"])
    storage.save_ui_state(expanded, colors, toolbar)  # another ordinary stale GUI save
    data = json.loads(storage._STATE_FILE.read_text())
    assert data["recent_sessions"] == ["cli2", "cli", "old"]
    assert data["expanded_folders"] == ["Firma"]
    assert data["favorite_sessions"] == {"old": True}
    assert data["toolbar_search_texts"]["main"] == "changed"


def test_gui_recent_action_updates_shared_list(isolated_storage):
    storage.save_ui_state(set(), {}, {"recent_sessions": ["old"]})
    storage.load_ui_state()
    storage.record_recent_sessions(["cli"])
    recent = storage.record_recent_sessions(["gui"])
    storage.save_ui_state(set(), {}, {"recent_sessions": recent})
    assert json.loads(storage._STATE_FILE.read_text())["recent_sessions"] == ["gui", "cli", "old"]


def test_full_stale_gui_history_delete_and_undo_keep_new_cli_start(isolated_storage):
    old = [f"a{i}" for i in range(10)]
    storage.save_ui_state(set(), {}, {"recent_sessions": old})
    storage.load_ui_state()
    storage.record_recent_sessions(["cli-new"])
    storage.save_ui_state(set(), {}, {"recent_sessions": old[:-1]})
    assert json.loads(storage._STATE_FILE.read_text())["recent_sessions"][0] == "cli-new"
    storage.save_local_undo_state([], {}, set(), {}, {"recent_sessions": [old[-1], *old[:-1]]})
    assert json.loads(storage._STATE_FILE.read_text())["recent_sessions"][0] == "cli-new"


def test_stale_gui_delete_keeps_restarted_existing_cli_entry_first(isolated_storage):
    storage.save_ui_state(set(), {}, {"recent_sessions": ["a", "b", "c"]})
    storage.load_ui_state()
    storage.record_recent_sessions(["b"])
    storage.save_ui_state(set(), {}, {"recent_sessions": ["a", "b"]})
    assert json.loads(storage._STATE_FILE.read_text())["recent_sessions"] == ["b", "a"]


def test_user_prompt_escape_aborts(monkeypatch):
    from ssh_manager_app.cli import prompt_user
    from prompt_toolkit.shortcuts import PromptSession
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    import threading
    with create_pipe_input() as pipe:
        session = PromptSession(input=pipe, output=DummyOutput())
        monkeypatch.setattr("prompt_toolkit.shortcuts.prompt", session.prompt)
        timer = threading.Timer(0.1, lambda: pipe.send_text("\x1b"))
        timer.start()
        try:
            with pytest.raises(KeyboardInterrupt):
                prompt_user(["deploy"])
        finally:
            timer.join()


def test_recent_processes_do_not_lose_entries(isolated_storage):
    # Independent processes actually contend on the same Windows file lock.
    script = """import sys
from pathlib import Path
from ssh_manager_app import storage
storage._STATE_FILE = Path(sys.argv[1])
storage._APP_SESSIONS_FILE = storage._STATE_FILE.with_name('app_sessions.json')
storage.record_recent_sessions([sys.argv[2]])
"""
    processes = [subprocess.Popen([sys.executable, "-c", script, str(storage._STATE_FILE), f"cli-{i}"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(6)]
    for process in processes:
        _, error = process.communicate(timeout=20)
        assert process.returncode == 0, error.decode()
    assert set(json.loads(storage._STATE_FILE.read_text())["recent_sessions"]) == {f"cli-{i}" for i in range(6)}


def test_recent_refuses_corrupt_state(isolated_storage):
    storage._STATE_FILE.write_text("corrupt", encoding="utf-8")
    with pytest.raises(ValueError):
        storage.record_recent_sessions(["new"])
    assert storage._STATE_FILE.read_text() == "corrupt"


def test_gui_can_save_after_recovering_corrupt_state(isolated_storage):
    storage._STATE_FILE.write_text("broken", encoding="utf-8")
    expanded, colors, toolbar = storage.load_ui_state()
    storage.save_ui_state(expanded, colors, toolbar)
    assert json.loads(storage._STATE_FILE.read_text())["expanded_folders"] == []
    assert list(isolated_storage.glob("ui_state.json.corrupt-*"))


def test_launch_inherits_handles_returns_exit_and_records_after_spawn(monkeypatch):
    from ssh_manager_app import cli_launch
    events = []
    child = Mock()
    child.wait.return_value = 17
    def spawn(args):
        events.append(("spawn", args))
        return child
    monkeypatch.setattr(cli_launch.shutil, "which", lambda _: "C:/OpenSSH/ssh.exe")
    monkeypatch.setattr(cli_launch.subprocess, "Popen", spawn)
    monkeypatch.setattr(storage, "record_recent_sessions", lambda keys: events.append(("recent", keys)))
    assert cli_launch.launch(entry()) == (17, None)
    assert events == [("spawn", ["C:/OpenSSH/ssh.exe", "--", "deploy@192.0.2.10"]), ("recent", ["one"])]


def test_failed_spawn_does_not_record_recent(monkeypatch):
    from ssh_manager_app import cli_launch
    monkeypatch.setattr(cli_launch.shutil, "which", lambda _: "ssh")
    monkeypatch.setattr(cli_launch.subprocess, "Popen", Mock(side_effect=OSError("missing")))
    recent = Mock()
    monkeypatch.setattr(storage, "record_recent_sessions", recent)
    with pytest.raises(OSError):
        cli_launch.launch(entry())
    recent.assert_not_called()


def test_msys_client_uses_constant_exec_and_separate_arguments(tmp_path, monkeypatch):
    from ssh_manager_app import cli_launch
    import os
    if os.name != "nt":
        pytest.skip("Windows MSYS foreground job setup")
    folder = tmp_path / "Git with spaces"
    folder.mkdir()
    client = folder / "ssh.exe"
    (folder / "msys-2.0.dll").touch()
    (folder / "bash.exe").touch()
    monkeypatch.setattr(cli_launch.shutil, "which", lambda _: str(client))
    child = Mock()
    child.wait.return_value = 0
    spawn = Mock(return_value=child)
    monkeypatch.setattr(cli_launch.subprocess, "Popen", spawn)
    monkeypatch.setattr(storage, "record_recent_sessions", lambda _: [])
    cli_launch.launch(entry())
    assert spawn.call_args.args[0] == [str(folder / "bash.exe"), "--noprofile", "--norc", "-c",
                                      'exec "$@"', "sshm", str(client), "--", "deploy@192.0.2.10"]


def test_recent_error_does_not_interrupt_ssh(monkeypatch):
    from ssh_manager_app import cli_launch
    monkeypatch.setattr(cli_launch.shutil, "which", lambda _: "ssh")
    child = Mock()
    child.wait.return_value = 0
    monkeypatch.setattr(cli_launch.subprocess, "Popen", Mock(return_value=child))
    monkeypatch.setattr(storage, "record_recent_sessions", Mock(side_effect=OSError("locked")))
    code, warning = cli_launch.launch(entry())
    assert code == 0 and "nicht gespeichert" in warning
    child.wait.assert_called_once()


def test_noninteractive_cli_fails_without_loading_gui_or_sources():
    result = subprocess.run([sys.executable, "sshm.py"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 2 and "interaktives Terminal" in result.stderr
    result = subprocess.run([sys.executable, "sshm.py", "--help"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and "query" in result.stdout


def test_ui_keystrokes_select_exact_id_after_search():
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    from ssh_manager_app.cli_ui import SessionPicker
    async def run():
        with create_pipe_input() as pipe:
            picker = SessionPicker(Catalog([entry(), entry("two", "db-02")], default_settings(), {}, []),
                                   input=pipe, output=DummyOutput())
            asyncio.get_running_loop().call_later(0.1, pipe.send_text, "wb1\x1b[B\x1b[B\r")
            result = await asyncio.wait_for(picker.app.run_async(), timeout=5)
            assert result.identity == ("app", "one")
    asyncio.run(run())


def test_ui_escape_cancels_and_filters_preserve_original_path():
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput
    from ssh_manager_app.cli_ui import SessionPicker
    async def run():
        with create_pipe_input() as pipe:
            picker = SessionPicker(Catalog([entry(favorite=True), entry("two")], default_settings(), {}, []),
                                   input=pipe, output=DummyOutput())
            picker.open_filters()
            picker.view_choices.current_value = "favorites"
            picker.apply_filters()
            assert [r.label for r in picker.rows] == ["Firma", "Produktion", "web-01"]
            asyncio.get_running_loop().call_later(0.1, pipe.send_text, "\x03")
            assert await asyncio.wait_for(picker.app.run_async(), timeout=5) is None
    asyncio.run(run())
