import csv
from pathlib import Path

from ssh_manager_app.exports import write_csv_export
from ssh_manager_app.models import Session
import pytest
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import Mock
from ssh_manager_app.certificate_paths import certificate_paths, confirm_broad_certificate_paths


def test_csv_safe_covers_folder_and_cells_and_raw_preserves_data(tmp_path):
    session = Session("s", "=HYPERLINK(\"bad\")", [], "host")
    for safe in (True, False):
        target = tmp_path / f"{safe}.csv"
        write_csv_export(target, [("@folder", [session])], ["display_name", "notes"], lambda _: " \t+bad", excel_safe=safe)
        with target.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, delimiter=";"))
        assert rows[0] == [("'" if safe else "") + "@folder"]
        assert rows[2] == [("'" if safe else "") + session.display_name, ("'" if safe else "") + " \t+bad"]


@pytest.mark.parametrize("path", ["etc/ssl", "/etc/../root", "/etc/ssl\x00", "/etc/ssl\t", "/etc\r/ssl"])
def test_certificate_paths_reject_unsafe_inputs(path):
    with pytest.raises(ValueError):
        certificate_paths([path])


def test_paths_normalized_broad_paths_require_confirmation():
    assert certificate_paths([" /etc//ssl/./private/ ", "/etc/ssl/private"]) == ["/etc/ssl/private"]
    with patch("ssh_manager_app.certificate_paths.messagebox.askyesno", return_value=False) as ask:
        assert confirm_broad_certificate_paths(None, ["/etc/ssl/private"])
        ask.assert_not_called()
        assert not confirm_broad_certificate_paths(None, ["/etc"], search=True)
        assert "Suche" in ask.call_args.args[1]


def test_folder_rename_cancel_keeps_all_paths_and_confirm_merges():
    from ssh_manager_app.actions_sessions import rename_folder
    first = Session("s1", "a", ["Prod", "Old", "Sub"], "a", source="app")
    second = Session("s2", "b", ["Prod", "New", "Deep"], "b", source="app")
    app = SimpleNamespace(_app_sessions=[first, second], _sessions=[first, second])
    with patch("ssh_manager_app.actions_sessions.simpledialog.askstring", return_value="New"), \
         patch("ssh_manager_app.actions_sessions.messagebox.askyesno", return_value=False) as ask, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions"):
        rename_folder(app, "Prod/Old")
        assert first.folder_path == ["Prod", "Old", "Sub"]
        save.assert_not_called()
        ask.return_value = True
        rename_folder(app, "Prod/Old")
        assert first.folder_path == ["Prod", "New", "Sub"]
        assert second.folder_path == ["Prod", "New", "Deep"]


@pytest.mark.parametrize("name", ["New/Sub", "..", "A\tB"])
def test_folder_rename_rejects_invalid_names(name):
    from ssh_manager_app.actions_sessions import rename_folder
    app = SimpleNamespace(_app_sessions=[], _sessions=[])
    with patch("ssh_manager_app.actions_sessions.simpledialog.askstring", return_value=name), \
         patch("ssh_manager_app.actions_sessions.messagebox.showwarning") as warning, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save:
        rename_folder(app, "Old")
    warning.assert_called_once()
    save.assert_not_called()


@pytest.mark.parametrize("cancel", [False, True])
def test_restart_limit_bounds_running_hosts_and_cancel_skips_waiting(cancel):
    import threading
    import time
    from ssh_manager_app.actions_restart import restart_servers, RestartResult
    from ssh_manager_app.models import AppSettings
    sessions = [Session(str(i), str(i), [], f"host{i}") for i in range(5)]
    users = [(session, "ops") for session in sessions]
    progress = Mock(cancel_event=threading.Event())
    progress.winfo_exists.return_value = True
    callbacks = []
    app = Mock(settings=AppSettings())
    app.after.side_effect = lambda _delay, callback: callbacks.append(callback)
    def wait(window):
        if window is progress:
            deadline = time.monotonic() + 3
            while not progress.finish.called and time.monotonic() < deadline:
                if callbacks:
                    callbacks.pop(0)()
                time.sleep(.005)
            assert progress.finish.called
    app.wait_window.side_effect = wait
    active = 0
    peak = 0
    called = []
    lock = threading.Lock()
    def monitor(session, *_args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            called.append(session.key)
        if cancel:
            progress.cancel_event.set()
        time.sleep(.03)
        with lock:
            active -= 1
        return RestartResult("online", "ready")
    with patch("ssh_manager_app.actions_restart.resolve_users_for_sessions", return_value=users), \
         patch("ssh_manager_app.actions_restart.ServerRestartDialog", return_value=Mock(result={"max_parallel": 1 if cancel else 2})), \
         patch("ssh_manager_app.actions_restart.ServerRestartProgressDialog", return_value=progress), \
         patch("ssh_manager_app.actions_restart.monitor_server_restart", side_effect=monitor):
        restart_servers(app, sessions)
    assert peak <= (1 if cancel else 2)
    assert len(called) == (1 if cancel else 5)
    assert progress.update_host.call_count == 5


def _filezilla_source(tmp_path, monkeypatch, payload):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    source = tmp_path / "FileZilla" / "sitemanager.xml"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(payload)
    return source


def test_filezilla_rejects_large_and_declaration_documents_unchanged(tmp_path, monkeypatch):
    from ssh_manager_app import storage
    monkeypatch.setattr(storage, "FILEZILLA_MAX_BYTES", 1000)
    for payload in (b"x" * 1001, b'<!DOCTYPE FileZilla3 [<!ENTITY x "host">]><FileZilla3/>',
                    '<!DOCTYPE FileZilla3><FileZilla3/>'.encode("utf-16")):
        source = _filezilla_source(tmp_path, monkeypatch, payload)
        assert storage.load_filezilla_config_sessions() == []
        assert storage.take_load_warnings()
        assert source.read_bytes() == payload


def test_filezilla_unique_stable_ids_and_metadata_migration_with_backup(tmp_path, monkeypatch):
    from ssh_manager_app import storage
    import json
    server = '<Server><Name>Prod</Name><Host>host</Host><User>{}</User><Protocol>1</Protocol></Server>'
    def xml(users):
        return ('<FileZilla3><Servers>' + ''.join(server.format(user) for user in users) + '</Servers></FileZilla3>').encode()
    source = _filezilla_source(tmp_path, monkeypatch, xml(["ops", "ops", "root"]))
    sessions = storage.load_filezilla_config_sessions()
    keys = [session.key for session in sessions]
    assert len(set(keys)) == 3
    source.write_bytes(xml(["other", "ops", "ops", "root"]))
    assert [session.key for session in storage.load_filezilla_config_sessions()][1:] == keys
    old = sessions[0].legacy_key
    notes = {old: "important", keys[1]: "independent", "other": "untouched"}
    colors = {old: "#123456"}
    toolbar = {"favorite_sessions": {old: True}, "recent_sessions": [old], "session_user_overrides": {old: "deploy"}}
    migrated = storage.migrate_filezilla_metadata(sessions, notes, colors, toolbar)
    assert old not in migrated[0]
    assert migrated[0][keys[1]] == "independent"
    assert migrated[0][keys[2]] == "important"
    assert set(migrated[1]) == set(keys)
    assert migrated[2]["recent_sessions"] == keys
    assert set(migrated[2]["favorite_sessions"]) == set(keys)
    assert storage.migrate_filezilla_metadata(sessions, *migrated) == migrated
    monkeypatch.setattr(storage, "_NOTES_FILE", tmp_path / "notes.json")
    monkeypatch.setattr(storage, "_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(storage, "_APPDATA_DIR", tmp_path, raising=False)
    monkeypatch.setattr(storage, "_recover_session_transaction", lambda: None)
    storage._NOTES_FILE.write_text(json.dumps({"notes": notes}))
    storage._STATE_FILE.write_text("{}")
    storage.save_filezilla_migration({"Folder"}, *migrated)
    assert storage.load_notes() == migrated[0]
    assert storage.load_ui_state() == ({"Folder"}, migrated[1], {**migrated[2], "search_history": []})
    assert json.loads((tmp_path / "notes.json.filezilla-v1.bak").read_text())["notes"] == notes
