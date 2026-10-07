"""Help search and isolated Windows/Tk integration (no user data or SSH)."""
from unittest.mock import Mock
import tkinter as tk

import pytest

from ssh_manager_app.help import TOPICS, open_help, search_topics, topic_body
from ssh_manager_app.shortcuts import default_shortcuts, merge_with_defaults


def test_search_matches_full_text_and_multiple_words():
    mapping = default_shortcuts()
    assert search_topics("", mapping) == list(TOPICS)
    assert [topic.id for topic in search_topics("WHITELIST reguläre", mapping)] == ["server"]
    assert search_topics("unbekanntes-hilfethema-xyz", mapping) == []


def test_search_and_table_use_current_shortcuts_including_disabled_actions():
    mapping = default_shortcuts()
    mapping.update(connect="F6", open_help="")
    keys = next(topic for topic in TOPICS if topic.id == "keys")
    body = topic_body(keys, mapping)
    assert "Verbinden: F6  (Standard: Return)" in body
    assert "Hilfe öffnen: Nicht belegt  (Standard: F1)" in body
    assert [topic.id for topic in search_topics("F6", mapping)] == ["keys"]
    assert merge_with_defaults({"connect": "F6"})["open_help"] == "F1"


@pytest.fixture
def app(monkeypatch):
    import ssh_manager
    from ssh_manager_app import actions_app, actions_ui

    for name in ("load_app_sessions", "load_filezilla_config_sessions", "load_ssh_config_sessions"):
        monkeypatch.setattr(ssh_manager, name, lambda: [])
    monkeypatch.setattr(ssh_manager.RegistryReader, "load_sessions", lambda self: [])
    from ssh_manager_app.models import default_settings
    monkeypatch.setattr(ssh_manager, "load_settings", default_settings)
    monkeypatch.setattr(ssh_manager, "load_notes", lambda: {})
    monkeypatch.setattr(ssh_manager, "load_ui_state", lambda: (set(), {}, {}))
    monkeypatch.setattr(actions_ui, "persist_ui_state", lambda app: None)
    monkeypatch.setattr(actions_app, "persist_ui_state", lambda app: None)
    try:
        root = ssh_manager.SSHManagerApp()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    errors = []
    root.report_callback_exception = lambda *error: errors.append(error)
    root.geometry("750x550+30+30")
    root.update()
    yield root
    root.destroy()
    assert errors == []


def test_help_reuses_window_refreshes_shortcuts_and_reopens(app):
    open_help(app)
    app.update()
    window = app._help_window
    assert app.grab_current() is None
    assert window.winfo_viewable()
    window.query.set("Tastenkürzel")
    mapping = app._shortcut_manager.current_mapping()
    mapping["connect"] = "F6"
    app._shortcut_manager.apply_bindings(mapping)
    open_help(app)
    app.update()
    assert app._help_window is window
    assert window.query.get() == "Tastenkürzel"
    assert "Verbinden: F6" in window.text.get("1.0", "end")
    window.query.set("unbekanntes-hilfethema-xyz")
    app.update()
    assert not window.topics.get_children()
    assert "Keine Treffer" in window.text.get("1.0", "end")
    window.query.set("")
    assert len(window.topics.get_children()) == len(TOPICS)
    window.search_entry.focus_force()
    app.update()
    window.search_entry.event_generate("<Escape>")
    app.update()
    assert app._help_window is None
    open_help(app)
    app.update()
    assert app._help_window is not window


def test_custom_help_shortcut_updates_menu_and_opens_window(app):
    from ssh_manager_app.ui import reapply_shortcut_bindings
    app.settings.keyboard_shortcuts["open_help"] = "F6"
    reapply_shortcut_bindings(app)
    assert app._help_menu.entrycget(0, "accelerator") == "F6"
    app._tree._tv.focus_force()
    app.update()
    app._tree._tv.event_generate("<F6>")
    app.update()
    assert app._help_window is not None


def test_help_blocks_main_actions_from_every_help_widget(app):
    calls = []
    for action in app._shortcut_manager.actions():
        if action.id != "open_help":
            action.callback = lambda id=action.id: calls.append(id)
    app._tree._tv.focus_force()
    app.update()
    app._tree._tv.event_generate("<F1>")
    app.update()
    window = app._help_window
    assert window is not None
    for widget in (window.search_entry, window.topics, window.text):
        widget.focus_force()
        app.update()
        for binding in ("<Return>", "<Control-Return>", "<Delete>", "<F2>", "<F5>",
                        "<Control-a>", "<Control-d>", "<Control-i>", "<Control-n>", "<Control-f>"):
            widget.event_generate(binding)
            app.update()
    assert calls == []
    app._tree._tv.focus_force()
    app.update()
    app._tree._tv.event_generate("<Control-a>")
    app.update()
    assert calls == ["select_all"]


def test_menu_and_palette_open_help(app):
    menu = app.nametowidget(app.cget("menu"))
    help_index = next(index for index in range(menu.index("end") + 1)
                      if menu.type(index) == "cascade" and menu.entrycget(index, "label") == "Hilfe")
    help_menu = app.nametowidget(menu.entrycget(help_index, "menu"))
    assert help_menu.entrycget(0, "accelerator") == "F1"
    help_menu.invoke(0)
    app.update()
    assert app._help_window is not None
    app._help_window.close()
    from ssh_manager_app.actions_app import open_command_palette
    open_command_palette(app)
    app.update()
    palette = app._command_palette
    palette._entry.delete(0, "end")
    palette._entry.insert(0, "> Hilfe")
    palette._on_query_changed()
    assert palette._ranked[0][0].id == "act:help"
    palette._execute_selected()
    app.update()
    assert app.grab_current() is None
    assert app._help_window is not None


def test_shift_enter_activates_focused_row_with_default_binding(app):
    activate = Mock()
    app._tree.activate_focused = activate
    app._tree._tv.focus_force()
    app.update()
    app._tree._tv.event_generate("<Shift-Return>")
    app.update()
    activate.assert_called_once_with()


def test_search_empty_state_and_palette_no_results_are_visible(app):
    app._tree.filter("unbekanntes-security-test-thema")
    app.update()
    assert app._tree._empty_title.get() == "Keine Suchtreffer"
    assert not app._tree._empty_add_button.winfo_ismapped()
    app._tree.filter("")
    app.update()
    assert app._tree._empty_title.get() == "Keine Verbindungen vorhanden"
    from ssh_manager_app.actions_app import open_command_palette
    open_command_palette(app)
    app.update()
    palette = app._command_palette
    palette._entry.insert(0, "unbekanntes-security-test-thema")
    palette._on_query_changed()
    assert not palette._ranked
    assert "Keine Treffer" in palette._listbox.get(0)
    palette._close()


def test_details_panel_follows_focus_and_can_be_hidden(app):
    from ssh_manager_app.models import Session
    from ssh_manager_app.details import toggle_session_details
    session = Session("detail", "Details Test", [], "test.invalid", "ops", source="app")
    app._notes[session.key] = "Nur app-intern"
    app._tree.refresh([session])
    iid = next(iter(app._tree._item_to_session))
    app._tree._tv.focus(iid)
    app._tree._tv.selection_set(iid)
    toggle_session_details(app)
    app.update()
    assert app._details_panel.title.get() == "Details Test"
    assert "test.invalid" in app._details_panel.info.get()
    assert "Nur app-intern" in app._details_panel.note.get("1.0", "end")
    assert str(app._details_panel) in tuple(map(str, app._session_area.panes()))
    toggle_session_details(app)
    assert str(app._details_panel) not in tuple(map(str, app._session_area.panes()))


def test_named_filters_combine_criteria_without_overwriting_folder_state(app, monkeypatch):
    from ssh_manager_app.models import Session
    from ssh_manager_app.session_filters import SessionFiltersDialog, apply_session_filters
    monkeypatch.setattr("ssh_manager_app.actions_ui.persist_ui_state", lambda _: None)
    sessions = [Session("a", "Web", ["Prod"], "a.test", "ops", 2222, "app"),
                Session("b", "DB", ["Lab"], "b.test", "ops", 22, "app")]
    app._tree.refresh(sessions)
    app._tree._open_folders = {"Lab"}
    editor = SessionFiltersDialog(app)
    editor.name.set("Prod Ops")
    editor.fields["source"].set("Eigene Verbindungen")
    editor.fields["folder"].set("prod")
    editor.fields["username"].set("ops")
    editor.fields["port"].set("2222")
    editor.save()
    editor.fields["folder"].set("changed")
    editor.load()
    assert editor.fields["folder"].get() == "prod"
    editor.apply()
    assert {s.key for s in app._tree._item_to_session.values()} == {"a"}
    assert app._tree.get_open_folders() == {"Lab"}
    app._tree.refresh(sessions)
    assert {s.key for s in app._tree._item_to_session.values()} == {"a"}
    apply_session_filters(app, {}, "")
    assert len(app._tree._item_to_session) == 2
    assert app._tree.get_open_folders() == {"Lab"}
