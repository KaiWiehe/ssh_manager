import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ssh_manager_app.diagnosis import ConnectionDiagnosisDialog, diagnose_many, open_diagnosis
from ssh_manager_app.models import AppSettings, Session
from ssh_manager_app.storage import load_ui_state


@pytest.fixture
def app():
    root = tk.Tk()
    root.withdraw()
    root.settings = AppSettings()
    root._initial_toolbar_search_texts = {"command_palette": {"width": 700}}
    root._search_var = tk.StringVar(value="unchanged")
    root._search_history = ["unchanged"]
    root._tree = SimpleNamespace(get_open_folders=lambda: {"keep"}, get_session_colors=lambda: {})
    yield root
    root.destroy()


def target(name):
    return Session(name, name, [], name + ".invalid", "")


def test_ports_saved_without_start_and_restored_for_other_host_and_restart(app, tmp_path):
    with patch("ssh_manager_app.storage._STATE_FILE", tmp_path / "ui_state.json"):
        dialog = ConnectionDiagnosisDialog(app, [target("first")])
        dialog.ports.set("80,443,8000-8002")
        dialog.destroy()  # Flush pending debounce even on immediate closing.
        folders, colors, state = load_ui_state()
        assert folders == {"keep"}
        assert state["main"] == "unchanged"
        assert state["command_palette"] == {"width": 700}
        assert state["diagnosis_ports"] == "80,443,8000-8002"
        app._initial_toolbar_search_texts = state
        other = ConnectionDiagnosisDialog(app, [target("second")])
        assert other.ports.get() == "80,443,8000-8002"
        other.ports.set("")
        other.destroy()
        assert load_ui_state()[2]["diagnosis_ports"] == ""


def test_invalid_edit_does_not_replace_last_valid_saved_ports(app, tmp_path):
    app._initial_toolbar_search_texts["diagnosis_ports"] = "443"
    with patch("ssh_manager_app.storage._STATE_FILE", tmp_path / "ui_state.json"), patch("ssh_manager_app.actions_ui.persist_ui_state") as save:
        dialog = ConnectionDiagnosisDialog(app, [target("first")])
        dialog.ports.set("1-65535")
        dialog.destroy()
    save.assert_not_called()
    assert app._initial_toolbar_search_texts["diagnosis_ports"] == "443"


def test_quick_select_uses_configured_names_and_updates_fallback(app):
    app.settings.quick_users = ["one", "two"]
    dialog = ConnectionDiagnosisDialog(app, [target("first")])
    buttons = []
    def collect(widget):
        if widget.winfo_class() == "TButton" and widget.cget("text") in ("one", "two"):
            buttons.append(widget)
        for child in widget.winfo_children():
            collect(child)
    collect(dialog)
    assert [button.cget("text") for button in buttons] == ["one", "two"]
    buttons[1].invoke()
    assert dialog.user.get() == "two"
    dialog.destroy()


def test_fallback_used_only_when_no_fixed_user():
    a, b = target("a"), target("b")
    b.username = "fixed"
    with patch("ssh_manager_app.diagnosis.diagnose_session", return_value=[]) as diagnose:
        diagnose_many([a, b], "fallback", True)
    assert {(call.args[0].key, call.args[1]) for call in diagnose.call_args_list} == {("a", "fallback"), ("b", "fixed")}


def test_context_diagnosis_does_not_read_checkbox_selection(app):
    with patch("ssh_manager_app.diagnosis.ConnectionDiagnosisDialog") as dialog:
        open_diagnosis(app, [target("clicked")])
    assert dialog.call_args.args[1][0].key == "clicked"
