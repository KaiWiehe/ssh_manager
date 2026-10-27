"""Real Tk checks with entirely synthetic connections and isolated persistence."""
from copy import deepcopy
import csv
import io
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ssh_manager_app.dialogs_restart import ServerRestartProgressDialog
from ssh_manager_app.dialogs_restart_templates import RestartTemplatesDialog, RestartPreview, ServicePicker
from ssh_manager_app.models import Session, default_settings
from ssh_manager_app.restart_templates import resolve_targets, validate_template
from ssh_manager_app.themes import palette_for_theme
from ssh_manager_app.ui import _apply_palette_styles


@pytest.fixture
def app(monkeypatch):
    root = tk.Tk()
    root.geometry("1200x850+20+20")
    root.settings = default_settings()
    root._initial_toolbar_search_texts = {}
    root._app_sessions = [Session("one", "NBB-TEST-01", [], "one.example", "admin", source="app"),
                          Session("two", "NBB-TEST-02", [], "two.example", "", source="app"),
                          Session("three", "NBB-TEST-03", [], "three.example", "postgres", source="app")]
    root._winscp_sessions = root._ssh_config_sessions = root._filezilla_sessions = []
    root._session_user_overrides = {}
    root._search_var, root._search_history, root._tree = tk.StringVar(), [], MagicMock()
    ttk.Style(root).theme_use("clam")
    _apply_palette_styles(root, palette_for_theme("default"))
    monkeypatch.setattr("ssh_manager_app.actions_ui.persist_ui_state", lambda _: None)
    monkeypatch.setattr("ssh_manager_app.dialogs_restart_templates.messagebox.showwarning", lambda *a, **k: None)
    monkeypatch.setattr("ssh_manager_app.dialogs_restart_templates.messagebox.showerror", lambda *a, **k: pytest.fail(str(a)))
    root.update()
    yield root
    root.destroy()


def screenshot(window, name):
    directory = os.environ.get("SSH_RESTART_PREVIEW_DIR")
    if not directory:
        return
    from PIL import ImageGrab
    window.update()
    window.lift()
    window.update()
    ImageGrab.grab(window=window.winfo_id()).save(Path(directory) / name)


def test_actual_editor_save_copy_users_service_controls_and_preview(app, monkeypatch):
    window = RestartTemplatesDialog(app, app._app_sessions)
    app.update()
    assert len(window.rows) == 3
    window.quick.set("deploy")
    window.fill_users()
    assert [user.get() for user, _ in window.rows] == ["admin", "deploy", "postgres"]
    checks = window.rows[0][1]
    checks.new.set("wildfly")
    checks.add_new()
    checks.add("legacy.service", "inactive")
    window.name.set("Neubrandenburg Testfarm")
    assert window.save()
    saved = deepcopy(app._initial_toolbar_search_texts["restart_templates"])
    assert saved["items"][0]["targets"][0]["checks"][1]["expected"] == "inactive"
    screenshot(window, "restart-editor.png")
    # The selected design permits removing a service directly in its server row.
    checks.remove(checks.fields[1])
    assert len(checks.values()) == 1
    class Choice:
        def __init__(self, *a):
            self.result = ("new", "Neubrandenburg Kopie")
    monkeypatch.setattr("ssh_manager_app.dialogs_restart_templates.SaveTemplateChoice", Choice)
    monkeypatch.setattr(window, "wait_window", lambda _: None)
    assert window.save()
    assert len(window.library["items"]) == 2
    assert window.library["items"][0] == saved["items"][0]
    assert window.library["items"][1]["name"] == "Neubrandenburg Kopie"
    item = validate_template(window.template, runnable=True)
    targets = resolve_targets(item, app._app_sessions)
    preview = RestartPreview(window, item, targets)
    app.update()
    preview.password.set("temporary")
    preview.accept()
    assert preview.result == "temporary" and not preview.password.get()
    window.destroy()


def test_actual_results_copy_five_errors_text_selection_and_hover_all_themes(app):
    sessions = [(Session(str(i), f"NBB-TEST-{i:02}", [], f"test-{i}.example"), "admin") for i in range(8)]
    for theme in ("default", "dark_neutral", "midnight"):
        _apply_palette_styles(app, palette_for_theme(theme))
        window = ServerRestartProgressDialog(app, sessions, "")
        app.update()
        for i, (session, _) in enumerate(sessions):
            window.update_host(session.key, "online" if i < 3 else "timeout" if i == 7 else "error",
                               f"Details für {session.display_name}\n" + "Langtext " * 120)
        window._table_tools.copy("errors")
        copied = list(csv.reader(io.StringIO(window.clipboard_get()), delimiter="\t"))
        assert len(copied) == 6 and copied[0] == ["Server", "Benutzer", "Status", "Details"]
        assert len(copied[1][3]) > 900
        window._table_tools.copy("all")
        assert len(list(csv.reader(io.StringIO(window.clipboard_get()), delimiter="\t"))) == 9
        ids = window._tree.get_children()
        window._tree.selection_set(ids[3:5])
        window._table_tools.show_selection()
        window._table_tools.copy("selection")
        assert len(list(csv.reader(io.StringIO(window.clipboard_get()), delimiter="\t"))) == 3
        text = window._table_tools.text
        text.tag_add("sel", "1.0", "1.6")
        assert text.get("sel.first", "sel.last") == "Server"
        box = window._tree.bbox(ids[0])
        assert box
        assert window._tree.bind("<Motion>")
        window._table_tools.hover(SimpleNamespace(y=box[1]+5))
        assert "row_hover" in window._tree.item(ids[0], "tags")
        assert window._tree.selection() == ids[3:5]
        window._table_tools.hover()
        assert "row_hover" not in window._tree.item(ids[0], "tags")
        window.finish()
        if theme == "default":
            screenshot(window, "restart-results.png")
        window.destroy()


def test_per_host_browser_merges_multi_selection_and_keeps_existing_state(app, monkeypatch):
    def worker(owner, work, on_success, on_error):
        on_success([("service", "a.service"), ("service", "b.service"), ("service", "c.service")])
    monkeypatch.setattr("ssh_manager_app.dialogs_restart_templates.run_worker", worker)
    selected = []
    picker = ServicePicker(app, app._app_sessions[0], "admin", lambda names: selected.extend(names))
    picker.list.selection_set(0, 1)
    picker.query.set("b.")
    picker.accept()
    assert selected == ["a.service", "b.service"]


def test_execution_pause_keeps_monitoring_active_and_stop_skips_pending(app, monkeypatch):
    import threading
    from ssh_manager_app.actions_restart import RestartResult
    from ssh_manager_app.actions_restart_templates import run_template
    from ssh_manager_app.restart_templates import new_template
    release = threading.Event()
    started = []
    final = {}
    item = new_template(app._app_sessions)
    item["max_parallel"] = 2
    for target in item["targets"]:
        target["user"] = "admin"
    def monitor(session, *args, **kwargs):
        started.append(session.key)
        if session.key == "one":
            return RestartResult("error", "simulated error")
        assert release.wait(3)
        return RestartResult("online", "simulated success")
    monkeypatch.setattr("ssh_manager_app.actions_restart_templates.monitor_template_restart", monitor)
    def observe():
        for window in app.winfo_children():
            if isinstance(window, ServerRestartProgressDialog):
                if window._finished:
                    final.update(window._states)
                    window.destroy()
                    return
                for frame in window.winfo_children():
                    if str(frame.grid_info().get("row")) == "3" and frame.winfo_ismapped():
                        assert started == ["one", "two"]
                        assert window._states["three"] == "pending"
                        release.set()
                        # Decide to stop only the still waiting rest, not the active second host.
                        for buttons in frame.winfo_children():
                            for button in buttons.winfo_children():
                                if isinstance(button, ttk.Button) and button.cget("text") == "Wartende Neustarts stoppen":
                                    button.invoke()
        app.after(25, observe)
    app.after(25, observe)
    watchdog = app.after(5000, lambda: [w.destroy() for w in app.winfo_children() if isinstance(w, ServerRestartProgressDialog)])
    progress = run_template(app, item, resolve_targets(item, app._app_sessions), "")
    assert progress.winfo_exists() and app.grab_current() is None
    app.wait_window(progress)
    app.after_cancel(watchdog)
    assert final == {"one": "error", "two": "online", "three": "not_started"}


def test_ambiguous_connection_is_visible_and_cannot_be_browsed(app, monkeypatch):
    app._app_sessions.append(Session("one", "Other host", [], "other.example", source="app"))
    window = RestartTemplatesDialog(app, app._app_sessions[:3])
    labels = []
    def walk(parent):
        for child in parent.winfo_children():
            if isinstance(child, ttk.Label):
                labels.append(child.cget("text"))
            walk(child)
    walk(window)
    assert any("mehrdeutig" in text for text in labels)
    picker = MagicMock()
    monkeypatch.setattr("ssh_manager_app.dialogs_restart_templates.ServicePicker", picker)
    window.browse(0)
    picker.assert_not_called()
    window.destroy()


def test_results_and_template_manager_leave_main_window_usable(app):
    main_tree = ttk.Treeview(app, selectmode="extended")
    main_tree.pack(fill="both", expand=True)
    for session in app._app_sessions:
        main_tree.insert("", "end", iid=session.key, text=session.display_name)
    performed = []
    action = ttk.Button(app, text="Aktion auf Auswahl", command=lambda: performed.append(main_tree.selection()))
    action.pack()
    manager = RestartTemplatesDialog(app, [])
    progress = ServerRestartProgressDialog(app, [(s, "admin") for s in app._app_sessions], "")
    app.update()
    assert app.grab_current() is None
    assert not str(manager.transient()) and not str(progress.transient())
    progress.update_host("one", "error", "Service fehlgeschlagen")
    progress._tree.selection_set(progress._rows["one"])
    # The main selection and another action are independent of the result rows.
    main_tree.selection_set("one")
    action.invoke()
    assert performed == [("one",)]
    assert progress.winfo_exists() and manager.winfo_exists()
    assert progress._tree.selection() == (progress._rows["one"],)
    progress.finish()
    main_tree.selection_set("two", "three")
    action.invoke()
    assert performed[-1] == ("two", "three")
    assert app.grab_current() is None
    progress.destroy()
    manager.destroy()


def test_direct_restart_returns_without_waiting_for_results(app, monkeypatch):
    from ssh_manager_app.actions_restart import RestartResult, restart_servers
    dialogs_waited = []
    original_wait = app.wait_window
    def wait(window):
        dialogs_waited.append(window)
        original_wait(window)
    monkeypatch.setattr(app, "wait_window", wait)
    def input_dialog(parent, targets):
        window = tk.Toplevel(parent)
        window.result = {"sudo_password": "", "service": "", "timeout_seconds": 300, "max_parallel": 1}
        window.after_idle(window.destroy)
        return window
    monkeypatch.setattr("ssh_manager_app.actions_restart.ServerRestartDialog", input_dialog)
    monkeypatch.setattr("ssh_manager_app.actions_restart.resolve_users_for_sessions", lambda _, sessions, mode: [(s, "admin") for s in sessions])
    monkeypatch.setattr("ssh_manager_app.actions_restart.monitor_server_restart", lambda *a, **k: RestartResult("online", "simulated"))
    progress = restart_servers(app, app._app_sessions)
    assert len(dialogs_waited) == 1
    assert progress.winfo_exists() and app.grab_current() is None
    progress.cancel_event.set()
    # Closing only this independent result window leaves the app available.
    progress.destroy()


def test_modeless_manager_creates_from_current_main_selection(app):
    manager = RestartTemplatesDialog(app, [])
    app._tree.get_selected_sessions.return_value = [app._app_sessions[1]]
    manager.create()
    assert [t["key"] for t in manager.template["targets"]] == ["two"]
    manager.destroy()


def test_password_fill_save_reopen_modes_and_reorder(app):
    from ssh_manager_app.restart_passwords import unseal
    window = RestartTemplatesDialog(app, app._app_sessions)
    window.quick.set("admin")
    window.fill_users()
    window.password_per_connection.set(True)
    window.toggle_password_mode()
    window.password_fields[0].set("exception")
    window.password_fields[2].set(" ")  # A space is a real password, never an empty field.
    window.common_password.set("shared")
    window.fill_passwords()
    assert [v.get() for v in window.password_fields] == ["exception", "shared", " "]
    window.password_fields[2].set("")
    assert window.save()
    saved = deepcopy(window.template)
    assert window.collect() == saved  # Randomized encryption must not create false edits.
    assert "exception" not in str(app._initial_toolbar_search_texts)
    old_fields = list(window.password_fields)
    old_common = window.common_password
    window.load(saved)
    assert old_common.get() == "" and all(not v.get() for v in old_fields)
    assert [v.get() for v in window.password_fields] == ["exception", "shared", ""]
    window.password_per_connection.set(False)
    window.toggle_password_mode()
    assert all(not w.winfo_manager() for w in window.password_widgets)
    assert window.common_password.get() == "shared"
    window.password_per_connection.set(True)
    window.toggle_password_mode()
    assert [v.get() for v in window.password_fields] == ["exception", "shared", ""]
    window.move(0, 1)
    assert [t["key"] for t in window.template["targets"]] == ["two", "one", "three"]
    assert [v.get() for v in window.password_fields] == ["shared", "exception", ""]
    assert unseal(window.collect()["targets"][1]["password_protected"]) == "exception"
    for theme in ("default", "dark_neutral", "midnight"):
        _apply_palette_styles(app, palette_for_theme(theme))
        app.update()
        assert all(w.winfo_ismapped() for w in window.password_widgets)
        screenshot(window, f"restart-passwords-{theme}.png")
    variable = window.common_password
    fields = list(window.password_fields)
    window.destroy()
    assert variable.get() == "" and all(not v.get() for v in fields)


def test_unreadable_password_preserved_until_explicit_edit(app):
    from ssh_manager_app.restart_templates import new_template
    from ssh_manager_app.restart_passwords import unseal
    item = new_template(app._app_sessions)
    item["password_per_connection"] = True
    item["targets"][0]["password_protected"] = "dpapi-user-v1:YWJj"
    window = RestartTemplatesDialog(app, [])
    window.load(item)
    window.common_password.set("shared")
    window.fill_passwords()
    assert window.password_fields[0].get() == ""
    assert window.collect()["targets"][0]["password_protected"] == "dpapi-user-v1:YWJj"
    window.password_fields[0].set("replacement")
    assert unseal(window.collect()["targets"][0]["password_protected"]) == "replacement"
    window.destroy()


def test_password_assignment_reaches_each_restart_worker(app, monkeypatch):
    from ssh_manager_app.actions_restart import RestartResult
    from ssh_manager_app.actions_restart_templates import run_template
    from ssh_manager_app.restart_templates import new_template
    from ssh_manager_app.restart_passwords import seal
    item = new_template(app._app_sessions)
    item["password_per_connection"] = True
    expected = {"one": "exception", "two": "shared", "three": ""}
    for target in item["targets"]:
        target.update(user="admin", password_protected=seal(expected[target["key"]]))
    seen = {}
    def monitor(session, user, password, *args, **kwargs):
        seen[session.key] = password
        return RestartResult("online", "simulated")
    monkeypatch.setattr("ssh_manager_app.actions_restart_templates.monitor_template_restart", monitor)
    progress = run_template(app, item, resolve_targets(item, app._app_sessions)[::-1], "ignored")
    def finish():
        if progress._finished:
            progress.destroy()
        else:
            app.after(20, finish)
    app.after(20, finish)
    watchdog = app.after(5000, progress.destroy)
    app.wait_window(progress)
    app.after_cancel(watchdog)
    assert seen == expected


def test_replace_connection_removes_previous_password(app, monkeypatch):
    window = RestartTemplatesDialog(app, app._app_sessions[:1])
    window.password_fields[0].set("old-host-secret")
    monkeypatch.setattr(window, "pick", lambda: [app._app_sessions[1]])
    window.replace_target(0)
    assert window.template["targets"][0]["key"] == "two"
    assert window.password_fields[0].get() == ""
    window.destroy()
