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
    file_menu.add_command(label="Neue Verbindung", command=self._add_session)
    file_menu.add_command(label="Neu laden", command=self._reload_sessions)
    file_menu.add_separator()
    file_menu.add_command(label="Einstellungen", command=self.show_settings_view)
    file_menu.add_command(label="JSONs in VS Code öffnen", command=self._open_appdata_jsons_in_vscode)
    file_menu.add_separator()
    file_menu.add_command(label="Beenden", command=self._on_close)
    menubar.add_cascade(label="Datei", menu=file_menu)

    selection_menu = tk.Menu(menubar, tearoff=False)
    selection_menu.add_command(label="Alle auswählen", command=self._select_all)
    selection_menu.add_command(label="Alle abwählen", command=self._deselect_all)
    selection_menu.add_command(label="Auswahl umkehren", command=self._invert_selection)
    menubar.add_cascade(label="Auswahl", menu=selection_menu)

    view_menu = tk.Menu(menubar, tearoff=False)
    view_menu.add_command(label="Ausklappen", command=self._expand_all)
    view_menu.add_command(label="Einklappen", command=self._collapse_all)
    view_menu.add_separator()
    view_menu.add_command(label="Farben zurücksetzen", command=self._reset_session_colors)
    view_menu.add_command(label="Ansicht auf Startzustand zurücksetzen", command=self.reset_view_state)
    menubar.add_cascade(label="Ansicht", menu=view_menu)

    actions_menu = tk.Menu(menubar, tearoff=False)
    actions_menu.add_command(label="Verbinden", command=self._on_connect)
    actions_menu.add_command(label="Hosts prüfen", command=lambda: self._tree.check_selected_hosts(timeout=self.settings.host_check_timeout_seconds))
    actions_menu.add_command(label="Tunnel öffnen", command=self._open_tunnel)
    actions_menu.add_command(label="Remote-Befehl ausführen", command=lambda: self._run_remote_command(self._tree.get_selected_sessions()))
    menubar.add_cascade(label="Aktionen", menu=actions_menu)

    settings_menu = tk.Menu(menubar, tearoff=False)
    settings_menu.add_command(label="Einstellungen öffnen", command=self.show_settings_view)
    settings_menu.add_command(label="Einstellungen exportieren…", command=self._export_settings_dialog)
    settings_menu.add_command(label="Einstellungen importieren…", command=self._import_settings_dialog)
    settings_menu.add_separator()
    settings_menu.add_command(label="Einstellungen zurücksetzen", command=self.reset_settings)
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
    self._search_history_btn = ttk.Button(search_wrap, text="▾", width=2, command=self._show_search_history_menu)
    self._search_history_btn.grid(row=0, column=1, padx=(2, 0))

    self._toolbar_buttons["show_select_all"] = ttk.Button(toolbar, text="Alle auswählen", command=self._select_all)
    self._toolbar_buttons["show_deselect_all"] = ttk.Button(toolbar, text="Alle abwählen", command=self._deselect_all)
    self._toolbar_buttons["show_expand_all"] = ttk.Button(toolbar, text="Ausklappen", command=self._expand_all)
    self._toolbar_buttons["show_collapse_all"] = ttk.Button(toolbar, text="Einklappen", command=self._collapse_all)
    self._toolbar_buttons["show_add_connection"] = ttk.Button(toolbar, text="+ Verbindung", command=self._add_session)
    self._toolbar_buttons["show_reload"] = ttk.Button(toolbar, text="Neu laden", command=self._reload_sessions)
    self._toolbar_buttons["show_open_tunnel"] = ttk.Button(toolbar, text="Tunnel öffnen…", command=self._open_tunnel)
    self._toolbar_buttons["show_check_hosts"] = ttk.Button(toolbar, text="Hosts prüfen", command=lambda: self._tree.check_selected_hosts(timeout=self.settings.host_check_timeout_seconds))
    layout_toolbar_buttons(self)

    self._tree = SessionTree(
        self._main_frame,
        sessions=self._sessions,
        img_unchecked=self._img_unchecked,
        img_checked=self._img_checked,
        on_selection_changed=self._on_selection_changed,
        initial_open_folders=self._initial_open_folders,
        initial_session_colors=self._initial_session_colors,
        on_quick_connect=self._quick_connect_session,
        on_edit_session=self._edit_session,
        on_delete_session=self._delete_session,
        on_delete_folder=self._delete_folder,
        on_rename_folder=self._rename_folder,
        on_add_session_in_folder=self._add_session,
        on_duplicate_ssh_alias=self._duplicate_ssh_alias,
        on_inspect_ssh_config=self._inspect_ssh_config,
        on_duplicate_app_session=self._duplicate_app_session,
        on_move_session=self._move_session,
        on_move_sessions=self._move_sessions,
        on_open_ssh_config_in_vscode=self._open_ssh_config_in_vscode,
        on_deploy_ssh_key=self._deploy_ssh_key,
        on_remove_ssh_key=self._remove_ssh_key,
        on_open_tunnel=self._open_tunnel,
        on_open_in_winscp=self._open_in_winscp,
        on_run_remote_command=self._run_remote_command,
        on_open_via_jumphost=self._open_via_jumphost,
        on_ui_state_changed=self._persist_ui_state,
        notes_getter=lambda key: self._notes.get(key, ""),
        on_edit_note=self._edit_session_note,
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
        command=self._on_connect,
        state=tk.DISABLED,
    )
    self._connect_btn.grid(row=0, column=0)

    self._search_history_after_id = None
    self._search_var.trace_add("write", lambda *_: self._on_search_changed())

    self._settings_view = SettingsView(self, self)

