import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ssh_manager_app.dialogs_remote import RemoteCommandDialog


@pytest.fixture
def root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    root.withdraw()
    yield root
    root.destroy()


@pytest.mark.parametrize("mode", ["command", "local_script", "remote_script"])
def test_remote_task_only_exposes_relevant_inputs(root, mode):
    dialog = RemoteCommandDialog(root, 2, run_mode=mode)
    root.update()
    assert dialog._run_mode.get() == mode
    assert bool(dialog._command_text.frame.winfo_manager()) == (mode == "command")
    assert not dialog._before_text.frame.winfo_manager()
    assert not dialog._after_text.frame.winfo_manager()
    if mode != "command":
        dialog._advanced_flow.set(True)
        dialog._update_help()
        assert dialog._before_text.frame.winfo_manager() == "grid"
        assert dialog._after_text.frame.winfo_manager() == "grid"
    dialog._on_cancel()


def test_saved_script_cannot_silently_switch_command_task(root):
    dialog = RemoteCommandDialog(root, 1, run_mode="command")
    with patch("ssh_manager_app.dialogs_remote.messagebox.showinfo") as info:
        dialog._apply_spec({"mode": "remote_script", "path": "/tmp/run.sh", "interpreter": "bash"})
    assert dialog._run_mode.get() == "command"
    info.assert_called_once()
    dialog._on_cancel()


@pytest.mark.parametrize("checked, expected", [([], "focus"), (["one"], "one"), (["one", "two"], None)])
def test_single_action_target_does_not_fall_back_from_multiple_checks(checked, expected):
    from ssh_manager_app.selection import single_action_target
    tree = SimpleNamespace(get_selected_sessions=lambda: checked, get_single_context_session=lambda: "focus")
    assert single_action_target(tree) == expected


def test_selection_survives_repeated_search_and_can_remove_hidden_host(root):
    from ssh_manager_app.tree import SessionTree
    from ssh_manager_app.models import Session
    from ssh_manager_app.dialogs_selection import SelectionReviewDialog
    sessions = [Session("a", "Alpha", [], "a.test"), Session("b", "Beta", [], "b.test")]
    image = tk.PhotoImage(master=root, width=2, height=2)
    counts = []
    tree = SessionTree(root, sessions, image, image, counts.append)
    tree.pack(fill="both", expand=True)
    root.deiconify()
    root.update()
    root._tree = tree
    tree.set_all_checked(True)
    tree.filter("Alpha")
    assert {s.key for s in tree.get_selected_sessions()} == {"a", "b"}
    assert tree.hidden_selected_keys() == {"b"}
    tree.filter("Beta")
    assert counts[-1] == 2
    assert tree.hidden_selected_keys() == {"a"}
    dialog = SelectionReviewDialog(root)
    assert len(dialog.list.get_children()) == 2
    tree.remove_from_selection("a")
    tree.filter("")
    assert [s.key for s in tree.get_selected_sessions()] == ["b"]
    tree.set_all_checked(False)
    assert counts[-1] == 0
    dialog.destroy()
    tree.destroy()


def test_session_details_explain_override_and_alias_without_writes():
    from ssh_manager_app.details import session_detail_text
    from ssh_manager_app.models import Session
    imported = Session("w", "Web", [], "web.test", "ops", source="winscp")
    text = session_detail_text(imported, {"w": "ops"}, "default")
    assert "App-Override" in text
    assert "Host und Port werden aus der Quelle gelesen" in text
    alias = Session("a", "alias", [], "host", source="ssh_alias")
    text = session_detail_text(alias, {}, "default")
    assert "SSH-Alias: alias" in text
    assert "kein Benutzerdialog" in text
