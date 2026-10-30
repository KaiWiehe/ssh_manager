"""Reentry regressions for independent windows and local changes."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch
import tkinter as tk

import pytest

from ssh_manager_app.local_undo import local_undo, reverted_snapshot, snapshot, undo_last
from ssh_manager_app.models import Session
from ssh_manager_app.window_policy import AppWindow, single_pending, wait_for_window
from ssh_manager_app.actions_sessions import _capture_targets, _targets_unchanged, edit_session


def state():
    tree = SimpleNamespace(get_session_colors=lambda: {})
    session = Session("app:id", "Web", ["Old"], "host", "ops", source="app")
    return SimpleNamespace(_local_undo_enabled=True, _undo_depth=0, _undo_stack=[],
        _app_sessions=[session], _notes={}, _favorite_sessions={},
        _session_user_overrides={}, _recent_sessions=[], _tree=tree)


@pytest.mark.parametrize("cancel_outer", [False, True])
def test_real_tk_wait_separates_main_window_undo_from_pending_action(cancel_outer):
    root = tk.Tk()
    root.withdraw()
    app = state()
    @local_undo("independent")
    def independent(app):
        app._notes["other"] = "independent"
    @local_undo("pending")
    def pending(app):
        dialog = AppWindow(root)
        root.after(1, lambda: (independent(app), dialog.destroy()))
        root.wait_window(dialog)
        if not cancel_outer:
            app._notes["outer"] = "pending"
    try:
        with patch("ssh_manager_app.actions_ui.persist_ui_state"):
            root.after(0, lambda: (pending(app), root.quit()))
            root.mainloop()
        assert [item[0] for item in app._undo_stack] == (["independent"] if cancel_outer else ["independent", "pending"])
        if not cancel_outer:
            _, before, after = app._undo_stack[-1]
            restored = reverted_snapshot(snapshot(app), before, after)
            assert restored["notes"] == {"other": "independent"}
    finally:
        root.destroy()


def test_direct_nested_batch_is_still_one_step():
    app = state()
    @local_undo("inner")
    def inner(app):
        app._notes["inner"] = "value"
    @local_undo("batch")
    def batch(app):
        inner(app)
        app._notes["outer"] = "value"
    with patch("ssh_manager_app.actions_ui.persist_ui_state"):
        batch(app)
    assert [entry[0] for entry in app._undo_stack] == ["batch"]


def test_single_pending_is_scoped_to_action_and_resource_and_cleans_on_error():
    owner = SimpleNamespace()
    calls = []
    @single_pending
    def action(owner, resource):
        calls.append(resource)
        if resource == "first":
            action(owner, resource="first")
            action(owner, "second")
        if resource == "error":
            raise ValueError()
    action(owner, "first")
    assert calls == ["first", "second"]
    for _ in range(2):
        with pytest.raises(ValueError):
            action(owner, "error")
    assert owner._pending_actions == set()


def test_conflicts_check_only_the_selected_resources():
    app = state()
    captured = _capture_targets(app, app._app_sessions)
    app._notes["other"] = "unrelated"
    assert _targets_unchanged(app, captured)
    app._notes["app:id"] = "newer"
    with patch("ssh_manager_app.actions_sessions.messagebox.showwarning") as warning:
        assert not _targets_unchanged(app, captured)
    warning.assert_called_once()


def test_edit_session_does_not_resurrect_removed_target_or_overwrite_its_note():
    app = state()
    app._local_undo_enabled = False
    app.settings = SimpleNamespace(quick_users=[])
    session = app._app_sessions[0]
    dialog = SimpleNamespace(result=replace(session, display_name="Changed"), note_result="stale")
    def other_delete(_dialog):
        app._app_sessions.clear()
        app._notes[session.key] = "newer"
    app.wait_window = other_delete
    with patch("ssh_manager_app.actions_sessions.SessionEditDialog", return_value=dialog), patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=[]), patch("ssh_manager_app.actions_sessions.messagebox.showwarning"), patch("ssh_manager_app.actions_sessions.save_sessions_and_notes") as save:
        edit_session(app, session)
    assert not app._app_sessions
    assert app._notes[session.key] == "newer"
    save.assert_not_called()


def test_owner_close_during_wait_cancels_safely():
    root = tk.Tk()
    root.withdraw()
    dialog = AppWindow(root)
    root.after(1, root.destroy)
    assert not wait_for_window(root, dialog)


def test_undo_while_another_dialog_is_pending_does_not_create_a_new_delta():
    root = tk.Tk()
    root.withdraw()
    app = state()
    app._tree.refresh = Mock()
    @local_undo("note")
    def change(app):
        app._notes["other"] = "value"
    @local_undo("pending cancel")
    def pending(app):
        dialog = AppWindow(root)
        root.after(1, lambda: (undo_last(app), dialog.destroy()))
        root.wait_window(dialog)
    try:
        with patch("ssh_manager_app.actions_ui.persist_ui_state"), patch("ssh_manager_app.storage.save_local_undo_state"), patch("ssh_manager_app.actions_ui.current_ui_state", return_value=(set(), {}, {})), patch("ssh_manager_app.actions_ui.build_visible_sessions", return_value=[]), patch("ssh_manager_app.dialogs_toast.ToastNotification"):
            change(app)
            root.after(0, lambda: (pending(app), root.quit()))
            root.mainloop()
        assert app._notes == {}
        assert app._undo_stack == []
    finally:
        root.destroy()


def test_confirmation_is_independent_and_repeated_question_cancels_second_call():
    from ssh_manager_app.window_policy import AnswerDialog, messagebox
    root = tk.Tk()
    root.withdraw()
    repeated = []
    def answer():
        dialog = next(child for child in root.winfo_children() if isinstance(child, AnswerDialog))
        assert dialog.transient() == ""
        assert dialog.grab_current() is None
        assert not dialog.attributes("-topmost")
        repeated.append(messagebox.askyesno("Question", "Continue?", parent=root))
        dialog.choose(True)
    try:
        root.after(1, answer)
        assert messagebox.askyesno("Question", "Continue?", parent=root) is True
        assert repeated == [False]
    finally:
        root.destroy()


def test_confirmation_cancels_when_owner_is_closed():
    from ssh_manager_app.window_policy import messagebox
    root = tk.Tk()
    root.withdraw()
    root.after(1, root.destroy)
    assert messagebox.askyesno("Question", "Continue?", parent=root) is False
