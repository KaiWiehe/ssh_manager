from types import SimpleNamespace
from unittest.mock import patch, Mock

from ssh_manager_app import storage
from ssh_manager_app.source_status import STATUSES, reload_source
from ssh_manager_app.models import Session


def test_missing_empty_and_malformed_sources_are_distinct(tmp_path, monkeypatch):
    source = tmp_path / "config"
    monkeypatch.setattr(storage, "_SSH_CONFIG_FILE", source)
    assert storage.load_ssh_config_sessions() == []
    assert STATUSES["ssh_config"]["state"] == "missing"
    source.write_text("# intentionally empty", encoding="utf-8")
    assert storage.load_ssh_config_sessions() == []
    assert STATUSES["ssh_config"]["state"] == "empty"
    source.write_bytes(b"\xff")
    assert storage.load_ssh_config_sessions() == []
    assert STATUSES["ssh_config"]["state"] == "error"
    storage.take_load_warnings()
    source.write_text("Host valid\n HostName host.test\n", encoding="utf-8")
    assert len(storage.load_ssh_config_sessions()) == 1
    assert STATUSES["ssh_config"]["state"] == "loaded"
    assert STATUSES["ssh_config"]["count"] == 1
    assert STATUSES["ssh_config"]["duration_ms"] >= 0


def test_targeted_reload_preserves_old_data_on_bad_read(tmp_path, monkeypatch):
    source = tmp_path / "config"
    source.write_bytes(b"\xff")
    monkeypatch.setattr(storage, "_SSH_CONFIG_FILE", source)
    original = [Session("old", "old", [], "host")]
    app = SimpleNamespace(_ssh_config_sessions=original, _tree=Mock())
    assert not reload_source(app, "ssh_config")
    assert app._ssh_config_sessions is original
    app._tree.refresh.assert_not_called()
    storage.take_load_warnings()


def test_targeted_reload_never_loads_other_sources(tmp_path, monkeypatch):
    source = tmp_path / "config"
    source.write_text("Host valid\n HostName host.test\n")
    monkeypatch.setattr(storage, "_SSH_CONFIG_FILE", source)
    app = SimpleNamespace(_ssh_config_sessions=[], _tree=Mock())
    with patch("ssh_manager_app.actions_ui.build_visible_sessions", side_effect=lambda app: app._ssh_config_sessions), patch.object(storage, "load_filezilla_config_sessions") as filezilla, patch.object(storage, "load_app_sessions") as own:
        assert reload_source(app, "ssh_config")
    filezilla.assert_not_called()
    own.assert_not_called()
    assert app._ssh_config_sessions[0].hostname == "host.test"


def test_copy_external_preserves_source_and_copies_notes():
    from ssh_manager_app.actions_sessions import copy_external_session
    original = Session("winscp", "Original", [], "host", "ops")
    copied = Session("app:new", "Kopie", [], "host", "ops", source="app")
    dialog = SimpleNamespace(result=copied, note_result="Notiz", title=Mock())
    app = SimpleNamespace(_app_sessions=[], _notes={original.key: "Notiz"}, settings=SimpleNamespace(quick_users=["ops"]), wait_window=Mock())
    with patch("ssh_manager_app.actions_sessions.messagebox.askyesno", return_value=True), patch("ssh_manager_app.actions_sessions.SessionEditDialog", return_value=dialog), patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=[]), patch("ssh_manager_app.actions_sessions.save_sessions_and_notes") as save, patch("ssh_manager_app.actions_sessions.rebuild_sessions"):
        copy_external_session(app, original)
    assert original.source == "winscp"
    assert app._notes == {"winscp": "Notiz", "app:new": "Notiz"}
    save.assert_called_once_with([copied], app._notes)
