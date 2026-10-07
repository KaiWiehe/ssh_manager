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


def test_runbook_editor_returns_spec_without_user_or_remote_execution(root):
    dialog = RemoteCommandDialog(root, 0, run_mode="command", editing=True)
    dialog._user_var.set("")
    dialog._command_text.insert("1.0", "uptime")
    dialog._on_ok()
    assert dialog.result[1]["command"] == "uptime"


def test_runbook_library_search_pin_and_delete_preserve_specs(root):
    from ssh_manager_app.runbook_library import RunbookLibraryDialog
    root._initial_toolbar_search_texts = {"remote_command_favorites": [
        {"name": "Uptime", "mode": "command", "command": "uptime", "note": "Status"},
        {"name": "Script", "mode": "remote_script", "path": "/opt/run.sh"},
    ]}
    library = RunbookLibraryDialog(root)
    library.list.selection_set("1")
    with patch("ssh_manager_app.actions_ui.persist_ui_state") as persist:
        library.pin()
        assert root._initial_toolbar_search_texts["remote_command_favorites"][1]["pinned"] is True
        assert root._initial_toolbar_search_texts["remote_command_favorites"][1]["path"] == "/opt/run.sh"
        persist.assert_called_once_with(root)
    library.query.set("Status")
    assert library.list.get_children() == ("0",)
    library.list.selection_set("0")
    with patch("ssh_manager_app.runbook_library.messagebox.askyesno", return_value=False):
        library.delete()
    assert len(library.items) == 2
    library.destroy()


def test_parameter_forms_edit_definitions_and_clear_ephemeral_values(root):
    from ssh_manager_app.runbook_parameters import ParameterDefinitionsDialog, RunbookParametersDialog
    editor = ParameterDefinitionsDialog(root, [])
    editor.fields["name"].set("SERVICE")
    editor.fields["label"].set("Dienst")
    editor.fields["type"].set("choice")
    editor.fields["choices"].set("web.service|db.service")
    editor.store(False)
    editor.confirm()
    inputs = RunbookParametersDialog(root, editor.result)
    inputs.variables["SERVICE"].set("web.service")
    inputs.confirm()
    assert inputs.result == {"SERVICE": "web.service"}
    assert inputs.variables["SERVICE"].get() == ""


def test_simple_upload_requires_one_file_and_one_directory(root, tmp_path):
    from ssh_manager_app.dialogs_certificates import CertificateDeployDialog
    from ssh_manager_app.models import default_settings
    root.settings = default_settings()
    source = tmp_path / "file.txt"
    source.write_text("test")
    dialog = CertificateDeployDialog(root, 1, simple=True)
    dialog._files = [str(source)]
    dialog._target_dirs_text.insert("1.0", "/home/ops/uploads\n/home/ops/other")
    with patch("ssh_manager_app.dialogs_certificates.messagebox.showwarning") as warn:
        dialog._on_ok()
    assert dialog.result is None
    warn.assert_called_once()
    dialog._target_dirs_text.delete("1.0", "end")
    dialog._target_dirs_text.insert("1.0", "/home/ops/uploads")
    dialog._on_ok()
    assert dialog.result["simple_upload"] is True
    assert not dialog.result["post_command"]
    assert not dialog.result["sudo_password"]
