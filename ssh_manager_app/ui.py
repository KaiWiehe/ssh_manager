from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .dialogs_settings_misc import SettingsView
from .tree import SessionTree


TOOLBAR_BUTTON_ORDER = [
    "show_select_all",
    "show_deselect_all",
    "show_expand_all",
    "show_collapse_all",
    "show_add_connection",
    "show_reload",
    "show_open_tunnel",
    "show_check_hosts",
]


def layout_toolbar_buttons(app) -> None:
    col = 2
    for key in TOOLBAR_BUTTON_ORDER:
        btn = app._toolbar_buttons[key]
        btn.grid_forget()
        if getattr(app.settings.toolbar, key):
            padx = (8, 2) if key == "show_add_connection" else (2, 2)
            if key == "show_check_hosts":
                padx = (2, 0)
            btn.grid(row=0, column=col, padx=padx)
            col += 1


def persist_ui_state_callback(app) -> None:
    from .actions_ui import persist_ui_state

    persist_ui_state(app)


def connect_selected_sessions_callback(app) -> None:
    from .actions_remote import connect_sessions

    connect_sessions(app, app._tree.get_selected_sessions())


def quick_connect_session_callback(app, session) -> None:
    from .actions_remote import quick_connect_session

    quick_connect_session(app, session)


def reload_sessions_callback(app) -> None:
    from .actions_ui import reload_sessions

    reload_sessions(app)


def edit_session_note_callback(app, session) -> None:
    from .actions_notes import edit_session_note

    edit_session_note(app, session)


def export_settings_dialog_callback(app) -> None:
    from .actions_app import export_settings_dialog

    export_settings_dialog(app)


def import_settings_dialog_callback(app) -> None:
    from .actions_app import import_settings_dialog

    import_settings_dialog(app)


def show_settings_view_callback(app) -> None:
    from .actions_ui import show_settings_view

    show_settings_view(app)


def show_main_view_callback(app) -> None:
    from .actions_ui import show_main_view

    show_main_view(app)


def edit_session_callback(app, session) -> None:
    from .actions_sessions import edit_session

    edit_session(app, session)


def delete_session_callback(app, session) -> None:
    from .actions_sessions import delete_session

    delete_session(app, session)


def delete_folder_callback(app, sessions, folder_key) -> None:
    from .actions_sessions import delete_folder

    delete_folder(app, sessions, folder_key)


def rename_folder_callback(app, folder_key) -> None:
    from .actions_sessions import rename_folder

    rename_folder(app, folder_key)


def duplicate_ssh_alias_callback(app, session) -> None:
    from .actions_sessions import duplicate_ssh_alias

    duplicate_ssh_alias(app, session)


def inspect_ssh_config_callback(app, session) -> None:
    from .actions_open import inspect_ssh_config

    inspect_ssh_config(app, session)


def duplicate_app_session_callback(app, session) -> None:
    from .actions_sessions import duplicate_app_session

    duplicate_app_session(app, session)


def move_session_callback(app, session) -> None:
    from .actions_sessions import move_session

    move_session(app, session)


def move_sessions_callback(app, sessions) -> None:
    from .actions_sessions import move_sessions

    move_sessions(app, sessions)


def open_ssh_config_in_vscode_callback(app) -> None:
    from .actions_open import open_ssh_config_in_vscode

    open_ssh_config_in_vscode(app)


def open_in_winscp_callback(app, sessions) -> None:
    from .actions_open import open_in_winscp

    open_in_winscp(app, sessions)


def deploy_ssh_key_callback(app, sessions) -> None:
    from .actions_remote import deploy_ssh_key

    deploy_ssh_key(app, sessions)


def remove_ssh_key_callback(app, sessions) -> None:
    from .actions_remote import remove_ssh_key

    remove_ssh_key(app, sessions)


def open_tunnel_callback(app, session=None) -> None:
    from .actions_remote import open_tunnel

    open_tunnel(app, session=session)


def run_remote_command_callback(app, sessions) -> None:
    from .actions_remote import run_remote_command

    run_remote_command(app, sessions)


def open_via_jumphost_callback(app, session) -> None:
    from .actions_remote import open_via_jumphost

    open_via_jumphost(app, session)


def add_session_callback(app, folder_preset="") -> None:
    from .actions_sessions import add_session

    add_session(app, folder_preset=folder_preset)


def open_appdata_jsons_in_vscode_callback(app) -> None:
    from .actions_sessions import open_appdata_jsons_in_vscode

    open_appdata_jsons_in_vscode(app)


def close_app_callback(app) -> None:
    from .actions_app import close_app

    close_app(app)


def show_search_history_menu_callback(app) -> None:
    from .actions_app import show_search_history_menu

    show_search_history_menu(app)


def on_search_changed_callback(app) -> None:
    from .actions_ui import on_search_changed

    on_search_changed(app)


def preview_toolbar_visibility_callback(app, toolbar_settings) -> None:
    from .actions_ui import preview_toolbar_visibility

    preview_toolbar_visibility(app, toolbar_settings)


def preview_source_visibility_callback(app, source_visibility) -> None:
    from .actions_ui import preview_source_visibility

    preview_source_visibility(app, source_visibility)


def reset_settings_callback(app) -> None:
    from .actions_ui import reset_settings

    reset_settings(app)


def reset_session_colors_callback(app) -> None:
    from .actions_ui import reset_session_colors

    reset_session_colors(app)


def reset_view_state_callback(app) -> None:
    from .actions_ui import reset_view_state

    reset_view_state(app)


def invert_selection_callback(app) -> None:
    from .actions_ui import invert_selection

    invert_selection(app)


def on_selection_changed_callback(app, count: int) -> None:
    from .actions_ui import on_selection_changed

    on_selection_changed(app, count)


def select_all_callback(app) -> None:
    from .actions_ui import select_all

    select_all(app)


def deselect_all_callback(app) -> None:
    from .actions_ui import deselect_all

    deselect_all(app)


def expand_all_callback(app) -> None:
    from .actions_ui import expand_all

    expand_all(app)


def collapse_all_callback(app) -> None:
    from .actions_ui import collapse_all

    collapse_all(app)


def configure_app_styles(app: tk.Tk) -> None:
    style = ttk.Style(app)
    style.theme_use("clam")
    style.configure("Toast.TFrame", background="#333333", relief="flat")
    style.configure("Toast.TLabel", background="#333333", foreground="#f5f5f5")
    style.configure("SettingsRoot.TFrame", background="#dcd7cf")
    style.configure("SettingsNav.TFrame", background="#d3cdc4")
    style.configure("SettingsContent.TFrame", background="#ebe7df")
    style.configure("SettingsPanel.TFrame", background="#f6f2eb")
    style.configure("SettingsActions.TFrame", background="#ebe7df")
    style.configure("SettingsTitle.TLabel", background="#ebe7df", font=("Segoe UI", 17, "bold"))
    style.configure("SettingsSubtitle.TLabel", background="#ebe7df", foreground="#5f5a52")
    style.configure("SettingsNavTitle.TLabel", background="#d3cdc4", font=("Segoe UI", 10, "bold"))
    style.configure("SettingsSectionTitle.TLabel", background="#f6f2eb", font=("Segoe UI", 13, "bold"))
    style.configure("SettingsHint.TLabel", background="#f6f2eb", foreground="#6b655c")
    style.configure("SettingsValue.TLabel", background="#f6f2eb")
    style.configure("SettingsNav.TButton", padding=(14, 10), anchor="w")


def build_main_ui(self) -> None:
    """Erstellt alle UI-Elemente."""
    self.columnconfigure(0, weight=1)
    self.rowconfigure(0, weight=1)

    menubar = tk.Menu(self)
    self.config(menu=menubar)

    file_menu = tk.Menu(menubar, tearoff=False)
    file_menu.add_command(label="Neue Verbindung", command=lambda: add_session_callback(self))
    file_menu.add_command(label="Neu laden", command=lambda: reload_sessions_callback(self))
    file_menu.add_separator()
    file_menu.add_command(label="Einstellungen", command=lambda: show_settings_view_callback(self))
    file_menu.add_command(label="JSONs in VS Code öffnen", command=lambda: open_appdata_jsons_in_vscode_callback(self))
    file_menu.add_separator()
    file_menu.add_command(label="Beenden", command=lambda: close_app_callback(self))
    menubar.add_cascade(label="Datei", menu=file_menu)

    selection_menu = tk.Menu(menubar, tearoff=False)
    selection_menu.add_command(label="Alle auswählen", command=lambda: select_all_callback(self))
    selection_menu.add_command(label="Alle abwählen", command=lambda: deselect_all_callback(self))
    selection_menu.add_command(label="Auswahl umkehren", command=lambda: invert_selection_callback(self))
    menubar.add_cascade(label="Auswahl", menu=selection_menu)

    view_menu = tk.Menu(menubar, tearoff=False)
    view_menu.add_command(label="Ausklappen", command=lambda: expand_all_callback(self))
    view_menu.add_command(label="Einklappen", command=lambda: collapse_all_callback(self))
    view_menu.add_separator()
    view_menu.add_command(label="Farben zurücksetzen", command=lambda: reset_session_colors_callback(self))
    view_menu.add_command(label="Ansicht auf Startzustand zurücksetzen", command=lambda: reset_view_state_callback(self))
    menubar.add_cascade(label="Ansicht", menu=view_menu)

    actions_menu = tk.Menu(menubar, tearoff=False)
    actions_menu.add_command(label="Verbinden", command=lambda: connect_selected_sessions_callback(self))
    actions_menu.add_command(label="Hosts prüfen", command=lambda: self._tree.check_selected_hosts(timeout=self.settings.host_check_timeout_seconds))
    actions_menu.add_command(label="Tunnel öffnen", command=lambda: open_tunnel_callback(self))
    actions_menu.add_command(label="Remote-Befehl ausführen", command=lambda: run_remote_command_callback(self, self._tree.get_selected_sessions()))
    menubar.add_cascade(label="Aktionen", menu=actions_menu)

    settings_menu = tk.Menu(menubar, tearoff=False)
    settings_menu.add_command(label="Einstellungen öffnen", command=lambda: show_settings_view_callback(self))
    settings_menu.add_command(label="Einstellungen exportieren…", command=lambda: export_settings_dialog_callback(self))
    settings_menu.add_command(label="Einstellungen importieren…", command=lambda: import_settings_dialog_callback(self))
    settings_menu.add_separator()
    settings_menu.add_command(label="Einstellungen zurücksetzen", command=lambda: reset_settings_callback(self))
    menubar.add_cascade(label="Einstellungen", menu=settings_menu)

    self._main_frame = ttk.Frame(self)
    self._main_frame.grid(row=0, column=0, sticky="nsew")
    self._main_frame.columnconfigure(0, weight=1)
    self._main_frame.rowconfigure(1, weight=1)

    toolbar = ttk.Frame(self._main_frame, padding=(8, 6))
    toolbar.grid(row=0, column=0, sticky="ew")
    toolbar.columnconfigure(1, weight=1)

    ttk.Label(toolbar, text="Suche:").grid(row=0, column=0, padx=(0, 4))
    search_wrap = ttk.Frame(toolbar)
    search_wrap.grid(row=0, column=1, sticky="ew", padx=(0, 8))
    search_wrap.columnconfigure(0, weight=1)
    self._search_var = tk.StringVar(value=self._initial_toolbar_search_texts.get("main", ""))
    self._search_history = list(self._initial_toolbar_search_texts.get("search_history", []))
    self._search_entry = ttk.Entry(search_wrap, textvariable=self._search_var)
    self._search_entry.grid(row=0, column=0, sticky="ew")
    self._search_history_btn = ttk.Button(search_wrap, text="▾", width=2, command=lambda: show_search_history_menu_callback(self))
    self._search_history_btn.grid(row=0, column=1, padx=(2, 0))

    self._toolbar_buttons["show_select_all"] = ttk.Button(toolbar, text="Alle auswählen", command=lambda: select_all_callback(self))
    self._toolbar_buttons["show_deselect_all"] = ttk.Button(toolbar, text="Alle abwählen", command=lambda: deselect_all_callback(self))
    self._toolbar_buttons["show_expand_all"] = ttk.Button(toolbar, text="Ausklappen", command=lambda: expand_all_callback(self))
    self._toolbar_buttons["show_collapse_all"] = ttk.Button(toolbar, text="Einklappen", command=lambda: collapse_all_callback(self))
    self._toolbar_buttons["show_add_connection"] = ttk.Button(toolbar, text="+ Verbindung", command=lambda: add_session_callback(self))
    self._toolbar_buttons["show_reload"] = ttk.Button(toolbar, text="Neu laden", command=lambda: reload_sessions_callback(self))
    self._toolbar_buttons["show_open_tunnel"] = ttk.Button(toolbar, text="Tunnel öffnen…", command=lambda: open_tunnel_callback(self))
    self._toolbar_buttons["show_check_hosts"] = ttk.Button(toolbar, text="Hosts prüfen", command=lambda: self._tree.check_selected_hosts(timeout=self.settings.host_check_timeout_seconds))
    layout_toolbar_buttons(self)

    self._tree = SessionTree(
        self._main_frame,
        sessions=self._sessions,
        img_unchecked=self._img_unchecked,
        img_checked=self._img_checked,
        on_selection_changed=lambda count: on_selection_changed_callback(self, count),
        initial_open_folders=self._initial_open_folders,
        initial_session_colors=self._initial_session_colors,
        on_quick_connect=lambda session: quick_connect_session_callback(self, session),
        on_edit_session=lambda session: edit_session_callback(self, session),
        on_delete_session=lambda session: delete_session_callback(self, session),
        on_delete_folder=lambda sessions, folder_key: delete_folder_callback(self, sessions, folder_key),
        on_rename_folder=lambda folder_key: rename_folder_callback(self, folder_key),
        on_add_session_in_folder=lambda folder_key: add_session_callback(self, folder_key),
        on_duplicate_ssh_alias=lambda session: duplicate_ssh_alias_callback(self, session),
        on_inspect_ssh_config=lambda session: inspect_ssh_config_callback(self, session),
        on_duplicate_app_session=lambda session: duplicate_app_session_callback(self, session),
        on_move_session=lambda session: move_session_callback(self, session),
        on_move_sessions=lambda sessions: move_sessions_callback(self, sessions),
        on_open_ssh_config_in_vscode=lambda: open_ssh_config_in_vscode_callback(self),
        on_deploy_ssh_key=lambda sessions: deploy_ssh_key_callback(self, sessions),
        on_remove_ssh_key=lambda sessions: remove_ssh_key_callback(self, sessions),
        on_open_tunnel=lambda session=None: open_tunnel_callback(self, session),
        on_open_in_winscp=lambda sessions: open_in_winscp_callback(self, sessions),
        on_run_remote_command=lambda sessions: run_remote_command_callback(self, sessions),
        on_open_via_jumphost=lambda session: open_via_jumphost_callback(self, session),
        on_ui_state_changed=lambda: persist_ui_state_callback(self),
        notes_getter=lambda key: self._notes.get(key, ""),
        on_edit_note=lambda session: edit_session_note_callback(self, session),
        toolbar_settings=self.settings.toolbar,
    )
    self._tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))

    self._notes_info_var = tk.StringVar(value="Notizinfo: Zeige den Mauszeiger auf Name oder Notiz, oder nutze Rechtsklick → Notiz bearbeiten…")
    notes_info = ttk.Label(self._main_frame, textvariable=self._notes_info_var, anchor="w", relief="sunken", padding=(8, 4))
    notes_info.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 0))

    bottom = ttk.Frame(self._main_frame, padding=(8, 6))
    bottom.grid(row=3, column=0, sticky="ew")
    bottom.columnconfigure(0, weight=1)

    self._connect_btn = ttk.Button(
        bottom,
        text="Verbinden",
        command=lambda: connect_selected_sessions_callback(self),
        state=tk.DISABLED,
    )
    self._connect_btn.grid(row=0, column=0)

    self._search_history_after_id = None
    self._search_var.trace_add("write", lambda *_: on_search_changed_callback(self))

    self._settings_view = SettingsView(self, self)

