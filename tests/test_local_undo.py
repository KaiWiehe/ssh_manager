from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch, Mock
import pytest

from ssh_manager_app.models import Session
from ssh_manager_app.local_undo import local_undo, snapshot, undo_last
from ssh_manager_app import storage


def app_state():
    session = Session("app:id", "Web", ["Old"], "host", "ops", source="app")
    tree = SimpleNamespace(_session_colors={session.key: "#112233"}, refresh=Mock())
    tree.get_session_colors = lambda: dict(tree._session_colors)
    tree.get_open_folders = lambda: {"Old"}
    tree.set_session_color = lambda key, value: tree._session_colors.pop(key, None)
    return SimpleNamespace(_app_sessions=[session], _notes={session.key: "note"}, _favorite_sessions={session.key: True}, _session_user_overrides={session.key: "override"}, _recent_sessions=[session.key], _tree=tree, _undo_stack=[], _undo_depth=0, _local_undo_enabled=True)


@pytest.mark.parametrize("operation", ["move", "rename", "delete", "color"])
def test_undo_restores_local_data_and_metadata_without_touching_later_recent(operation):
    app = app_state()
    original = snapshot(app)

    @local_undo("Test")
    def change(app):
        if operation == "move":
            app._app_sessions[0].folder_path = ["New"]
        elif operation == "rename":
            app._app_sessions[0].display_name = "New"
        elif operation == "color":
            app._tree._session_colors["app:id"] = "#ffffff"
        else:
            from ssh_manager_app.local_undo import cleanup_session_metadata
            app._app_sessions.clear()
            cleanup_session_metadata(app, {"app:id"})

    with patch("ssh_manager_app.actions_ui.persist_ui_state"):
        change(app)
    assert len(app._undo_stack) == 1
    app._recent_sessions.insert(0, "unrelated")
    with patch.object(storage, "save_local_undo_state") as save, patch("ssh_manager_app.actions_ui.current_ui_state", return_value=({"Old"}, {}, {})), patch("ssh_manager_app.actions_ui.build_visible_sessions", side_effect=lambda app: app._app_sessions), patch("ssh_manager_app.dialogs_toast.ToastNotification"):
        undo_last(app)
    restored = snapshot(app)
    assert restored["sessions"] == original["sessions"]
    assert restored["notes"] == original["notes"]
    assert restored["colors"] == original["colors"]
    assert restored["favorites"] == original["favorites"]
    assert restored["overrides"] == original["overrides"]
    assert "unrelated" in app._recent_sessions
    assert not app._undo_stack
    assert save.call_args.args[1] == original["notes"]


def test_cancel_does_not_record_and_nested_actions_make_one_step():
    app = app_state()
    @local_undo("inner")
    def inner(app):
        app._notes["app:id"] = "changed"
    @local_undo("outer")
    def outer(app):
        inner(app)
    with patch("ssh_manager_app.actions_ui.persist_ui_state"):
        local_undo("cancel")(lambda app: None)(app)
        assert not app._undo_stack
        outer(app)
    assert len(app._undo_stack) == 1
    assert app._undo_stack[0][0] == "outer"


def test_failed_undo_keeps_memory_and_history(tmp_path, monkeypatch):
    app = app_state()
    before = snapshot(app)
    app._app_sessions[0].display_name = "Changed"
    app._undo_stack.append(("Rename", before, snapshot(app)))
    monkeypatch.setattr(storage, "_APP_SESSIONS_FILE", tmp_path / "app_sessions.json")
    with patch.object(storage, "save_local_undo_state", side_effect=OSError), patch("ssh_manager_app.actions_ui.current_ui_state", return_value=(set(), {}, {})), patch("ssh_manager_app.local_undo.messagebox.showerror"):
        undo_last(app)
    assert app._app_sessions[0].display_name == "Changed"
    assert len(app._undo_stack) == 1


def test_undo_journal_finishes_all_three_stores_after_interruption(tmp_path, monkeypatch):
    for name, filename in (("_APP_SESSIONS_FILE", "app_sessions.json"), ("_NOTES_FILE", "notes.json"), ("_STATE_FILE", "ui_state.json")):
        monkeypatch.setattr(storage, name, tmp_path / filename)
    monkeypatch.setattr(storage, "_blocked_paths", set())
    app = app_state()
    writer = storage._atomic_write_json
    def interrupted(path, payload):
        if path == storage._NOTES_FILE:
            raise OSError("simulated interruption")
        return writer(path, payload)
    with patch.object(storage, "_atomic_write_json", side_effect=interrupted), pytest.raises(OSError):
        storage.save_local_undo_state(app._app_sessions, app._notes, {"Old"}, app._tree._session_colors, {"favorite_sessions": app._favorite_sessions})
    expanded, colors, toolbar = storage.load_ui_state()
    assert expanded == {"Old"}
    assert colors == app._tree._session_colors
    assert toolbar["favorite_sessions"] == app._favorite_sessions
    assert storage.load_notes() == app._notes
    assert storage.load_app_sessions()[0].display_name == "Web"
    assert not (tmp_path / "session-notes-pending.json").exists()
