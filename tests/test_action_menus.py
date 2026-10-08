import tkinter as tk
from unittest.mock import patch

from test_help import app
from ssh_manager_app.action_menus import populate_actions_menu, copy_menu
from ssh_manager_app.models import Session


def entries(menu):
    end = menu.index("end")
    return [(i, menu.entrycget(i, "label")) for i in range(end + 1) if menu.type(i) != "separator"] if end is not None else []


def child(menu, label):
    index = next(i for i, text in entries(menu) if text == label)
    return menu.nametowidget(menu.entrycget(index, "menu"))


def invoke(menu, label):
    menu.invoke(next(i for i, text in entries(menu) if text == label))


def refresh(menu):
    command = menu.cget("postcommand")
    if command:
        menu.tk.call(command)


def setup_hosts(app):
    clicked = Session("a", "Clicked", ["Folder"], "a.invalid", "ops", source="app")
    other = Session("b", "Other", ["Elsewhere"], "b.invalid", "ops", source="app")
    app._tree.refresh([clicked, other])
    ids = {s.key: iid for iid, s in app._tree._item_to_session.items()}
    app._tree.set_all_checked(True)
    app._tree.remove_from_selection(clicked.key)
    app._tree._tv.focus(ids[clicked.key])
    return clicked, other, ids


def test_shared_context_menu_has_every_main_workflow_and_targets_clicked_host(app):
    clicked, other, _ = setup_hosts(app)
    main, context = tk.Menu(app, tearoff=False), tk.Menu(app, tearoff=False)
    populate_actions_menu(app, main)
    populate_actions_menu(app, context, [clicked])
    main_labels = {label for _, label in entries(main)}
    assert main_labels <= {label for _, label in entries(context)}
    refresh(context)
    with patch("ssh_manager_app.diagnosis.ConnectionDiagnosisDialog") as diagnose, patch("ssh_manager_app.ui.run_remote_command_callback") as run, patch("ssh_manager_app.services.run_service_action") as service:
        invoke(context, "Verbindung diagnostizieren…")
        invoke(context, "Serverskript ausführen…")
        invoke(context, "Dienststatus anzeigen…")
    assert diagnose.call_args.args[1] == [clicked]
    run.assert_called_once_with(app, [clicked], "remote_script")
    service.assert_called_once_with(app, [clicked], "status")
    assert app._tree.get_selected_sessions() == [other]


def test_top_actions_exposes_connection_operations_and_all_app_menus(app):
    clicked, _, _ = setup_hosts(app)
    menu = tk.Menu(app, tearoff=False)
    populate_actions_menu(app, menu)
    local = child(menu, "Verbindung / Ordner verwalten")
    refresh(local)
    labels = {label for _, label in entries(local)}
    assert {"Verwalten", "Kopieren", "Werkzeuge", "Darstellung", "Löschen"} <= labels
    assert not any(label.startswith("Alle Aktionen") for label in labels)  # No recursive menus.
    tools = child(menu, "App-Werkzeuge")
    refresh(tools)
    assert {label for _, label in entries(tools)} == set(app._app_menu_sources)
    for name, original in app._app_menu_sources.items():
        assert entries(child(tools, name)) == entries(original)


def test_native_contexts_expose_diagnosis_and_shared_actions_for_exact_scope(app):
    clicked, other, ids = setup_hosts(app)
    menus = []
    with patch.object(tk.Menu, "tk_popup", autospec=True, side_effect=lambda menu, *args: menus.append(menu)):
        app._tree._show_session_menu(ids[clicked.key], x_root=0, y_root=0)
    with patch("ssh_manager_app.diagnosis.ConnectionDiagnosisDialog") as diagnose:
        invoke(menus[0], "Verbindung diagnostizieren…")
    assert diagnose.call_args.args[1] == [clicked]
    assert "Alle Aktionen für diese Verbindung" in {label for _, label in entries(menus[0])}
    folder = next(iid for iid, name in app._tree._item_to_folder_key.items() if name == "Folder")
    app._tree._tv.focus(folder)
    with patch.object(tk.Menu, "tk_popup", autospec=True, side_effect=lambda menu, *args: menus.append(menu)):
        app._tree._show_folder_menu(folder, x_root=0, y_root=0)
    context = child(menus[-1], "Alle Aktionen für diesen Ordner")
    refresh(context)
    with patch("ssh_manager_app.services.run_service_action") as service:
        invoke(context, "Dienstlogs anzeigen…")
    service.assert_called_once_with(app, [clicked], "logs")
    assert app._tree.get_selected_sessions() == [other]


def test_empty_context_disables_target_actions_and_keeps_global_tools(app):
    menu = tk.Menu(app, tearoff=False)
    populate_actions_menu(app, menu, [])
    refresh(menu)
    assert any("Remote-Befehl" in label and "anhaken" in label for _, label in entries(menu))
    assert any(label == "App-Werkzeuge" for _, label in entries(menu))
    assert menu.entrycget(0, "state") == "disabled"


def test_cloned_callbacks_survive_reopening_app_tools(app):
    calls = []
    source = tk.Menu(app, tearoff=False)
    source.add_command(label="Test", command=lambda: calls.append("called"))
    app._app_menu_sources = {"Test": source}
    menu = tk.Menu(app, tearoff=False)
    populate_actions_menu(app, menu)
    tools = child(menu, "App-Werkzeuge")
    for _ in range(3):
        refresh(tools)
        invoke(child(tools, "Test"), "Test")
    assert calls == ["called"] * 3


def test_folder_multi_target_preserves_scope_and_disables_single_host_tools(app):
    a, b, _ = setup_hosts(app)
    b.folder_path = ["Folder", "Child"]
    app._tree.refresh([a, b])
    folder = next(iid for iid, name in app._tree._item_to_folder_key.items() if name == "Folder")
    app._tree._tv.focus(folder)
    menu = tk.Menu(app, tearoff=False)
    populate_actions_menu(app, menu, [a, b])
    refresh(menu)
    assert any(label.startswith("Datei hochladen… — genau einen Host") for _, label in entries(menu))
    assert any(label.startswith("Tunnel öffnen — genau einen Host") for _, label in entries(menu))
    with patch("ssh_manager_app.ui.restart_servers_callback") as restart:
        invoke(menu, "Server neu starten…")
    restart.assert_called_once_with(app, [a, b])
    app._tree._tv.focus(next(iid for iid, value in app._tree._item_to_session.items() if value.key == b.key))
    local = child(menu, "Verbindung / Ordner verwalten")
    refresh(local)
    with patch("ssh_manager_app.diagnosis.ConnectionDiagnosisDialog") as diagnose:
        invoke(local, "Verbindungen im Ordner diagnostizieren… (2)")
    assert {value.key for value in diagnose.call_args.args[1]} == {"a", "b"}
