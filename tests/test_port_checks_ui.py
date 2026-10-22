"""Real Windows/Tk controls; synthetic sessions, no real SSH or app writes."""
from copy import deepcopy
import csv
import io
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock

import pytest

from ssh_manager_app import dialogs_port_check as ui, port_checks as pc
from ssh_manager_app.models import Session, default_settings
from ssh_manager_app.themes import palette_for_theme
from ssh_manager_app.ui import _apply_palette_styles


@pytest.fixture
def app(monkeypatch):
    root = tk.Tk()
    root.geometry("1200x950+20+20")
    root.settings = default_settings()
    root._initial_toolbar_search_texts = {}
    root._app_sessions = [Session("a", "APP-01", ["Apps"], "app-01.example", "ops", source="app"),
                          Session("b", "APP-02", ["Apps"], "app-02.example", source="app"),
                          Session("db", "DB-01", ["Databases"], "192.0.2.20", port=2222, source="app")]
    root._winscp_sessions = root._ssh_config_sessions = root._filezilla_sessions = []
    root._session_user_overrides = {}
    root._search_var, root._search_history, root._tree = tk.StringVar(), [], MagicMock()
    root._tree.get_selected_sessions.return_value = root._app_sessions[:2]
    root.errors = []
    root.report_callback_exception = lambda *args: root.errors.append(args)
    ttk.Style(root).theme_use("clam")
    _apply_palette_styles(root, palette_for_theme("modern_light"))
    monkeypatch.setattr("ssh_manager_app.actions_ui.persist_ui_state", lambda _: None)
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *_, **__: True)
    monkeypatch.setattr(ui.messagebox, "showwarning", lambda *a, **k: pytest.fail(str(a)))
    monkeypatch.setattr(ui.messagebox, "showerror", lambda *a, **k: pytest.fail(str(a)))
    root.update()
    yield root
    assert not root.errors
    root.destroy()


def until(app, predicate):
    deadline = time.monotonic() + 4
    while not predicate() and time.monotonic() < deadline:
        app.update()
        time.sleep(.005)
    assert predicate()
    app.update()


def set_targets(window):
    window.fields[0][1].set("192.0.2.10")
    window.add_target("192.0.2.20", 5432)


def test_picker_search_all_sources_port_and_checks_unchanged(app):
    window = ui.open_port_checks(app)
    set_targets(window)
    window.fields[0][2].set("8443")
    before = deepcopy(app._tree.get_selected_sessions())
    picker = window.pick_destination(window.fields[0][1])
    picker.query.set("databases")
    app.update()
    assert len(picker.tree.get_children()) == 1
    picker.tree.selection_set(picker.tree.get_children())
    picker.choose()
    until(app, lambda: not picker.winfo_exists())
    assert window.fields[0][1].get() == "192.0.2.20"
    assert window.fields[0][2].get() == "8443"
    assert app._tree.get_selected_sessions() == before
    assert window.grab_current() is None
    window.destroy()


def test_named_templates_save_load_overwrite_delete_and_no_run(app):
    window = ui.PortCheckDialog(app, app._app_sessions[:2])
    set_targets(window)
    window.name.set("Web und DB")
    window.save_template()
    assert app._initial_toolbar_search_texts[pc.STATE_KEY]["items"][0]["targets"] == [["192.0.2.10", 443], ["192.0.2.20", 5432]]
    window.remove_target(window.fields[1])
    window.load_template()
    assert len(window.fields) == 2 and window.job is None
    window.fields[0][2].set("8443")
    window.save_template()
    assert len(window.library["items"]) == 1
    assert window.library["items"][0]["targets"][0][1] == 8443
    window.delete_template()
    assert window.library["items"] == []
    assert len(window.fields) == 2
    window.destroy()


def test_multiple_modeless_windows_preserve_each_others_templates(app):
    first = ui.open_port_checks(app)
    second = ui.open_port_checks(app)
    set_targets(first)
    set_targets(second)
    first.name.set("First")
    first.save_template()
    second.name.set("Second")
    second.save_template()
    assert {i["name"] for i in app._initial_toolbar_search_texts[pc.STATE_KEY]["items"]} == {"First", "Second"}
    first.name.set("Second")
    first.load_template()
    assert len(first.fields) == 2
    second.name.set("First")
    second.delete_template()
    first.name.set("Third")
    first.save_template()
    assert {i["name"] for i in app._initial_toolbar_search_texts[pc.STATE_KEY]["items"]} == {"Second", "Third"}
    first.destroy()
    second.destroy()


def test_ui_live_grouping_copy_full_values_filter_retry_and_modeless(app, monkeypatch):
    calls, release = [], threading.Event()
    long = "Full detail\n" + "x" * 1200 + "\tend"
    def probe(source, destination, *_):
        calls.append((source.key, destination))
        release.wait(2)
        return pc.ProbeResult("timeout" if destination[1] == 5432 else "open", long, destination[0])
    monkeypatch.setattr(ui, "PortCheckJob", lambda *a, **k: pc.PortCheckJob(*a, **k, probe=probe))
    window = ui.open_port_checks(app)
    set_targets(window)
    window.start()
    app.update()
    assert window.grab_current() is None
    assert not window.transient()
    # Main app and its current selection remain usable while a run is active.
    app._tree.get_selected_sessions.return_value = [app._app_sessions[2]]
    button_calls = []
    button = ttk.Button(app, text="Other action", command=lambda: button_calls.append(True))
    button.pack()
    button.invoke()
    assert button_calls == [True]
    assert list(window.run_sources) == ["a", "b"]
    release.set()
    until(app, lambda: window.job is None)
    assert len(calls) == 4 and len(window.results.get_children()) == 2
    assert all(len(window.results.get_children(group)) == 2 for group in window.results.get_children())
    window.results.focus("r1")
    window.results.selection_set("r1")
    window.results.item("g0", open=False)
    window.render_results()
    assert window.results.focus() == "r1" and window.results.selection() == ("r1",)
    assert not window.results.item("g0", "open")
    window.filter.set("Nicht erreichbar")
    window.render_results()
    assert window.results.get_children() == ("g1",)
    window.tools.copy("all")
    copied = list(csv.reader(io.StringIO(app.clipboard_get()), delimiter="\t"))
    assert len(copied) == 5 and copied[1][-1] == long
    window.tools.copy("errors")
    assert len(list(csv.reader(io.StringIO(app.clipboard_get()), delimiter="\t"))) == 3
    window.results.selection_set("g1")
    window.tools.show_selection()
    assert long in window.tools.text.get("1.0", "end")
    assert len(window.tools.snapshot("selection")[1]) == 2
    window.retry()
    until(app, lambda: window.job is None)
    assert len(calls) == 6 and all(t[1][1] == 5432 for t in calls[4:])
    assert window.grab_current() is None
    window.destroy()


def test_close_cancels_without_tk_calls_in_worker(app, monkeypatch):
    stopped, entered = threading.Event(), threading.Event()
    def probe(source, destination, user, timeout, cancel):
        entered.set()
        cancel.wait(2)
        stopped.set()
        return pc.ProbeResult("cancelled", "cancelled")
    monkeypatch.setattr(ui, "PortCheckJob", lambda *a, **k: pc.PortCheckJob(*a, **k, probe=probe))
    window = ui.open_port_checks(app)
    set_targets(window)
    window.start()
    assert entered.wait(1)
    window.destroy()
    assert stopped.wait(1)
    app.update()


@pytest.mark.parametrize("theme", ["modern_light", "dark_neutral", "midnight"])
def test_render_target_groups_and_themes(app, monkeypatch, theme):
    _apply_palette_styles(app, palette_for_theme(theme))
    window = ui.open_port_checks(app)
    set_targets(window)
    window.destinations = tuple(window.destinations_from_fields())
    window.run_sources = {s.key: s for s in window.sources}
    window.values = {(s.key, destination): pc.ProbeResult("open" if i == 0 else "timeout", "Test details", destination[0], "2026-10-22T15:30:00+02:00")
                     for s in window.sources for i, destination in enumerate(window.destinations)}
    window.render_results()
    window.status.set("Beispiel · 4/4 abgeschlossen · 2 nicht erreichbar")
    app.update()
    assert window.results.winfo_height() > 100
    assert window.tools.text.winfo_height() > 30
    assert window.start_button.winfo_ismapped()
    directory = os.environ.get("SSH_PORT_CHECK_PREVIEW_DIR")
    if directory:
        from PIL import ImageGrab
        Path(directory).mkdir(parents=True, exist_ok=True)
        window.lift()
        window.update()
        ImageGrab.grab(window=window.winfo_id()).save(Path(directory) / f"port-check-{theme}.png")
    window.destroy()
