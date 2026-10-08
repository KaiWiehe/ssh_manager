"""Shared actions for the main menu and explicitly scoped context menus."""
from __future__ import annotations
import tkinter as tk


def populate_actions_menu(app, actions_menu, sessions=None):
    from . import ui
    self = app
    sessions = list(sessions) if sessions is not None else None
    def targets():
        return list(sessions) if sessions is not None else self._tree.get_selected_sessions()
    def _acc(action_id):
        manager = getattr(app, "_shortcut_manager", None)
        return manager.current_mapping().get(action_id, "") if manager else ""
    if sessions is not None:
        actions_menu.add_command(label=f"Ziele aus diesem Kontext: {len(sessions)}", state="disabled")
    actions_menu.add_command(label="Auswahl verbinden", accelerator=_acc("connect_selected"), command=lambda: ui.connect_sessions_callback(self, targets()))
    actions_menu.add_command(label="Hosts prüfen", command=lambda: check_context_hosts(self, sessions))
    from .diagnosis import open_diagnosis
    actions_menu.add_command(label="Verbindung diagnostizieren…", command=lambda: open_diagnosis(self, sessions))
    from .operation_results import show_last_results
    actions_menu.add_command(label="Letzte Sammelergebnisse…", command=lambda: show_last_results(self))
    actions_menu.add_command(label="Server neu starten…", command=lambda: ui.restart_servers_callback(self, targets()))
    actions_menu.add_command(label="Tunnel öffnen", command=lambda: ui.open_tunnel_callback(self, targets()[0] if sessions is not None and len(targets()) == 1 else None))
    actions_menu.add_command(label="Remote-Befehl ausführen", command=lambda: ui.run_remote_command_callback(self, targets()))
    actions_menu.add_command(label="Lokales Skript ausführen…", command=lambda: ui.run_remote_command_callback(self, targets(), "local_script"))
    actions_menu.add_command(label="Serverskript ausführen…", command=lambda: ui.run_remote_command_callback(self, targets(), "remote_script"))
    from .runbook_library import open_runbook_library
    actions_menu.add_command(label="Runbook-Bibliothek…", command=lambda: open_runbook_library(self))
    from . import services
    from .services import ACTION_LABELS
    for action, label in ACTION_LABELS.items():
        actions_menu.add_command(label=label + "…", command=lambda a=action: services.run_service_action(self, targets(), a))
    actions_menu.add_command(label="Datei hochladen…", command=lambda: ui.upload_file_callback(self, sessions))
    actions_menu.add_command(label="Dateien verteilen…", command=lambda: ui.deploy_certificate_files_callback(self, targets()))
    actions_menu.add_command(label="Zertifikate ersetzen…", command=lambda: ui.replace_certificates_callback(self, targets()))
    actions_menu.add_separator()
    actions_menu.add_command(label="DNS/IP auflösen…", command=lambda: ui.open_dns_lookup_dialog_callback(self))
    actions_menu.add_command(label="DNS/IP für Auswahl auflösen…", command=lambda: ui.resolve_dns_for_sessions_callback(self, targets()))
    actions_menu.add_command(
        label="DNS/IP für Auswahl auflösen… (DNS-Auswahl)",
        command=lambda: ui.resolve_dns_for_sessions_with_server_callback(self, targets()),
    )
    actions_menu.add_separator()
    actions_menu.add_command(
        label="Angezeigte Verbindungen als Markdown kopieren",
        command=lambda: ui.copy_visible_sessions_as_markdown_callback(self),
    )
    actions_menu.add_command(
        label="Angezeigte Verbindungen als CSV exportieren…",
        command=lambda: ui.export_visible_sessions_callback(self, "csv"),
    )
    actions_menu.add_command(
        label="Angezeigte Verbindungen als Excel exportieren…",
        command=lambda: ui.export_visible_sessions_callback(self, "xlsx"),
    )
    from .action_availability import configure_action_availability

    actions_menu.add_separator()
    actions_menu.add_command(label="SSH Key übertragen", command=lambda: ui.deploy_ssh_key_callback(self, targets()))
    actions_menu.add_command(label="SSH Key entfernen", command=lambda: ui.remove_ssh_key_callback(self, targets()))
    from .dialogs_selection import review_selection
    from .details import toggle_session_details
    from .session_filters import SessionFiltersDialog, apply_session_filters
    actions_menu.add_command(label="Häkchen-Auswahl prüfen…", command=lambda: review_selection(app))
    actions_menu.add_command(label="Häkchen-Auswahl leeren", command=lambda: app._tree.set_all_checked(False))
    actions_menu.add_command(label="Verbindungsdetails ein-/ausblenden", command=lambda: toggle_session_details(app))
    actions_menu.add_command(label="Filter / Ansichten…", command=lambda: SessionFiltersDialog(app))
    actions_menu.add_command(label="Filter löschen", command=lambda: apply_session_filters(app, {}, ""))
    add_connection_menu(app, actions_menu, sessions)
    add_app_tools(app, actions_menu)
    configure_action_availability(self, actions_menu, sessions=sessions)


def check_context_hosts(app, sessions):
    if sessions is None:
        app._tree.check_selected_hosts(timeout=app.settings.host_check_timeout_seconds)
    else:
        keys = {session.key for session in sessions}
        pairs = [(iid, session) for iid, session in app._tree._item_to_session.items() if session.key in keys]
        app._tree.check_hosts(pairs, timeout=app.settings.host_check_timeout_seconds)


def copy_menu(source, destination):
    """Give cloned entries their own callbacks; Tcl commands belong to one menu."""
    destination._source_menu = source
    end = source.index("end")
    if end is None:
        return
    for index in range(end + 1):
        kind = source.type(index)
        if kind == "separator":
            destination.add_separator()
        elif kind == "command":
            options = {key: source.entrycget(index, key) for key in ("label", "state", "accelerator")}
            command = source.entrycget(index, "command")
            if command:
                # Menu.delete deletes its entries' Tcl commands, even when they
                # were registered by another menu. Never share that ownership.
                options["command"] = lambda cmd=command: source.tk.call("eval", cmd)
            destination.add_command(**options)
        elif kind == "cascade":
            child = tk.Menu(destination, tearoff=False)
            copy_menu(source.nametowidget(source.entrycget(index, "menu")), child)
            destination.add_cascade(label=source.entrycget(index, "label"), menu=child)


def add_app_tools(app, menu):
    tools = tk.Menu(menu, tearoff=False)
    def refresh():
        for child in list(tools.winfo_children()):
            child.destroy()
        tools.delete(0, "end")
        for label, source in app.__dict__.get("_app_menu_sources", {}).items():
            child = tk.Menu(tools, tearoff=False)
            copy_menu(source, child)
            tools.add_cascade(label=label, menu=child)
    tools.configure(postcommand=refresh)
    refresh()
    menu.add_cascade(label="App-Werkzeuge", menu=tools)


def add_connection_menu(app, menu, sessions):
    local = tk.Menu(menu, tearoff=False)
    context_item = app._tree._tv.focus() if sessions is not None and hasattr(app, "_tree") else ""
    def refresh():
        for child in list(local.winfo_children()):
            child.destroy()
        old = local.__dict__.pop("_owned_source", None)
        local.delete(0, "end")
        if old is not None:
            old.destroy()
        tree = getattr(app, "_tree", None)
        if tree is None:
            return
        item = context_item if sessions is not None else tree._tv.focus()
        if sessions is not None and len(sessions) == 1:
            item = next((iid for iid, value in tree._item_to_session.items() if value.key == sessions[0].key), "")
        elif sessions is not None:
            # Folder context focus is the clicked folder; never pick another host.
            if item not in tree._item_to_folder_key:
                item = ""
        if item in tree._item_to_folder_key:
            source = tree._show_folder_menu(item, return_menu=True)
        elif item in tree._item_to_session:
            source = tree._show_session_menu(item, return_menu=True)
        else:
            local.add_command(label="Zuerst Verbindung oder Ordner fokussieren", state="disabled")
            return
        local._owned_source = source
        copy_menu(source, local)
    local.configure(postcommand=refresh)
    menu.add_cascade(label="Verbindung / Ordner verwalten", menu=local)
