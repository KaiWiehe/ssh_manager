"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ssh_manager_app import (
    AppSettings,
    REGISTRY_PATH,
    ToolbarSettings,
    SourceVisibilitySettings,
    Session,
    WINDOW_MIN_SIZE,
    WINDOW_TITLE,
    default_settings,
    load_app_sessions,
    load_filezilla_config_sessions,
    load_notes,
    load_settings,
    load_ssh_config_sessions,
    load_ui_state,
    save_app_sessions,
    save_notes,
    save_settings,
    save_ui_state,
)
from ssh_manager_app.constants import _SSH_CONFIG_DEFAULT_FOLDER

from ssh_manager_app.core import (
    RegistryReader,
    TerminalLauncher,
    _create_checkbox_images,
)

from ssh_manager_app.ui import build_main_ui, configure_app_styles
from ssh_manager_app.actions_sessions import (
    add_session,
    edit_session,
    duplicate_app_session,
    move_session,
    move_sessions,
    delete_session,
    delete_folder,
    rename_folder,
    duplicate_ssh_alias,
    open_appdata_jsons_in_vscode,
)
from ssh_manager_app.actions_remote import (
    connect_sessions,
    deploy_ssh_key,
    quick_connect_session,
    remove_ssh_key,
    open_tunnel,
    open_via_jumphost,
    resolve_single_session_user,
    resolve_users_for_sessions,
    run_remote_command,
)
from ssh_manager_app.actions_open import (
    inspect_ssh_config,
    open_in_winscp,
    open_ssh_config_in_vscode,
)

from ssh_manager_app.dialogs import (
    MoveFolderDialog,
    SessionEditDialog,
    SettingsView,
    UserDialog,
)

class SSHManagerApp(tk.Tk):
    """Hauptfenster der SSH-Manager Applikation."""

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.minsize(*WINDOW_MIN_SIZE)
        self.geometry("750x550")

        configure_app_styles(self)

        # Registry laden
        try:
            reader = RegistryReader()
            winscp_sessions = reader.load_sessions()
        except OSError as e:
            messagebox.showerror(
                "Registry-Fehler",
                f"WinSCP-Sessions konnten nicht geladen werden:\n{e}\n\n"
                f"Pfad: HKCU\\{REGISTRY_PATH}"
            )
            winscp_sessions = []

        self.settings = load_settings()
        self._startup_settings = load_settings()
        self._winscp_sessions = winscp_sessions
        self._filezilla_sessions = load_filezilla_config_sessions()

        # App-eigene Sessions und SSH-Config-Sessions laden und mergen
        self._app_sessions: list[Session] = load_app_sessions()
        self._notes = load_notes()
        self._ssh_config_sessions = load_ssh_config_sessions()
        self._sessions = self._build_visible_sessions()

        # Checkbox-Images (nach Tk-Initialisierung erzeugen!)
        self._img_unchecked, self._img_checked = _create_checkbox_images(self)

        self._initial_open_folders, self._initial_session_colors, self._initial_toolbar_search_texts = load_ui_state()
        if self.settings.startup_expand_mode == "expanded":
            self._initial_open_folders = {s.folder_key for s in self._sessions if s.folder_key}
        elif self.settings.startup_expand_mode == "collapsed":
            self._initial_open_folders = set()
        self._toolbar_buttons: dict[str, ttk.Button] = {}
        self._terminal_launcher = TerminalLauncher
        self._main_frame: ttk.Frame | None = None
        self._settings_view: SettingsView | None = None
        build_main_ui(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _add_search_history_entry(self, value: str) -> None:
        query = value.strip()
        if len(query) < 2:
            return
        self._search_history = [item for item in self._search_history if item != query]
        self._search_history.insert(0, query)
        self._search_history = self._search_history[:10]
        self._persist_ui_state()

    def _apply_search_history_entry(self, value: str) -> None:
        self._search_var.set(value)
        self._search_entry.icursor("end")
        self._search_entry.focus_set()

    def _show_search_history_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)
        if self._search_history:
            for item in self._search_history:
                menu.add_command(label=item, command=lambda v=item: self._apply_search_history_entry(v))
            menu.add_separator()
            menu.add_command(label="Verlauf leeren", command=self._clear_search_history)
        else:
            menu.add_command(label="Kein Suchverlauf", state=tk.DISABLED)
        x = self._search_history_btn.winfo_rootx()
        y = self._search_history_btn.winfo_rooty() + self._search_history_btn.winfo_height()
        menu.tk_popup(x, y)

    def _clear_search_history(self) -> None:
        self._search_history = []
        self._persist_ui_state()

    def _build_visible_sessions(self) -> list[Session]:
        visible: list[Session] = []
        if self.settings.source_visibility.show_winscp:
            visible.extend(self._winscp_sessions)
        if self.settings.source_visibility.show_app_connections:
            visible.extend(self._app_sessions)
        if self.settings.source_visibility.show_ssh_config:
            visible.extend(self._ssh_config_sessions)
        if self.settings.source_visibility.show_filezilla_config:
            visible.extend(self._filezilla_sessions)
        return sorted(
            visible,
            key=lambda s: (0 if s.folder_key == _SSH_CONFIG_DEFAULT_FOLDER else 1, s.folder_key.lower(), s.display_name.lower()),
        )

    def _layout_toolbar_buttons(self) -> None:
        col = 2
        order = [
            "show_select_all",
            "show_deselect_all",
            "show_expand_all",
            "show_collapse_all",
            "show_add_connection",
            "show_reload",
            "show_open_tunnel",
            "show_check_hosts",
        ]
        for key in order:
            btn = self._toolbar_buttons[key]
            btn.grid_forget()
            if getattr(self.settings.toolbar, key):
                padx = (8, 2) if key == "show_add_connection" else (2, 2)
                if key == "show_check_hosts":
                    padx = (2, 0)
                btn.grid(row=0, column=col, padx=padx)
                col += 1

    def preview_toolbar_visibility(self, toolbar_settings: ToolbarSettings) -> None:
        self.settings.toolbar = toolbar_settings
        self._layout_toolbar_buttons()
        self._tree.update_toolbar_settings(toolbar_settings)

    def preview_source_visibility(self, source_visibility: SourceVisibilitySettings) -> None:
        self.settings.source_visibility = source_visibility
        self._sessions = self._build_visible_sessions()
        self._tree.refresh(self._sessions)
        self._persist_ui_state()

    def _edit_session_note(self, session: Session) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Notiz bearbeiten")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text=f"Notiz für {session.display_name}:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        note_text = tk.Text(frame, width=48, height=6)
        note_text.grid(row=1, column=0, sticky="ew")
        current = self._notes.get(session.key, "")
        if current:
            note_text.insert("1.0", current)
        note_text.focus_set()

        result = {"saved": False}

        def on_ok() -> None:
            note = note_text.get("1.0", "end").strip()
            if note:
                self._notes[session.key] = note
            else:
                self._notes.pop(session.key, None)
            save_notes(self._notes)
            result["saved"] = True
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=on_cancel, width=10).pack(side="left", padx=4)

        dialog.update_idletasks()
        pw = self.winfo_width()
        ph = self.winfo_height()
        px = self.winfo_x()
        py = self.winfo_y()
        w = dialog.winfo_reqwidth()
        h = dialog.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.bind("<Escape>", lambda _e: on_cancel())
        dialog.bind("<Control-Return>", lambda _e: on_ok())
        self.wait_window(dialog)
        if result["saved"]:
            self._tree.refresh(self._sessions)
            self._update_notes_info(session)
            self._persist_ui_state()

    def get_default_user(self) -> str:
        return self.settings.default_user

    def get_quick_users(self) -> list[str]:
        return list(self.settings.quick_users)

    def get_terminal_settings(self) -> WindowsTerminalSettings:
        return self.settings.windows_terminal

    def _export_settings_dialog(self) -> None:
        if self._settings_view is None:
            return
        self._settings_view._export_settings()

    def _import_settings_dialog(self) -> None:
        if self._settings_view is None:
            return
        self._settings_view._import_settings()

    def _persist_ui_state(self) -> None:
        save_ui_state(
            self._tree.get_open_folders(),
            self._tree.get_session_colors(),
            {
                "main": self._search_var.get(),
                "last_remote_command": self._initial_toolbar_search_texts.get("last_remote_command", ""),
                "search_history": list(self._search_history),
            },
        )

    def show_settings_view(self) -> None:
        if self._settings_view is None or self._main_frame is None:
            return
        self._settings_view.load_from_app()
        self._main_frame.grid_remove()
        self._settings_view.grid(row=0, column=0, sticky="nsew")

    def show_main_view(self) -> None:
        if self._settings_view is not None:
            self._settings_view.grid_remove()
        if self._main_frame is not None:
            self._main_frame.grid()
        self._layout_toolbar_buttons()

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        save_settings(settings)
        self._layout_toolbar_buttons()
        self._search_entry.focus_set()
        ToastNotification(self, "Einstellungen gespeichert")

    def reset_settings(self) -> None:
        self.apply_settings(default_settings())
        if self._settings_view is not None:
            self._settings_view.load_from_app()

    def _reset_session_colors(self) -> None:
        for session_key in list(self._tree.get_session_colors().keys()):
            self._tree.set_session_color(session_key, None)
        ToastNotification(self, "Farben zurückgesetzt")

    def reset_view_state(self) -> None:
        self._search_var.set("")
        self._tree.populate(self._sessions, open_folders=set(self._initial_open_folders))
        current_colors = set(self._tree.get_session_colors())
        startup_colors = dict(self._initial_session_colors)
        for session_key in current_colors | set(startup_colors):
            self._tree.set_session_color(session_key, startup_colors.get(session_key))
        ToastNotification(self, "Ansicht auf Startzustand zurückgesetzt")

    def _invert_selection(self) -> None:
        self._tree.invert_checked()

    def _update_notes_info(self, session: Session | None = None) -> None:
        if not hasattr(self, "_notes_info_var"):
            return
        if session is None:
            self._notes_info_var.set("Notizinfo: Zeige den Mauszeiger auf Name oder Notiz, oder nutze Rechtsklick → Notiz bearbeiten…")
            return
        note = self._notes.get(session.key, "").strip()
        if note:
            self._notes_info_var.set(f"Notiz für {session.display_name}: {note}")
        else:
            self._notes_info_var.set(f"Notiz für {session.display_name}: Keine Notiz hinterlegt")

    def _on_selection_changed(self, count: int) -> None:
        """Callback vom SessionTree – aktualisiert den Verbinden-Button."""
        if count > 0:
            self._connect_btn.config(
                text=f"Verbinden ({count} ausgewählt)",
                state=tk.NORMAL,
            )
        else:
            self._connect_btn.config(text="Verbinden", state=tk.DISABLED)

    def _on_search_changed(self) -> None:
        value = self._search_var.get()
        self._tree.filter(value)
        self._persist_ui_state()
        self.after_cancel(self._search_history_after_id) if getattr(self, '_search_history_after_id', None) else None
        query = value.strip()
        if len(query) >= 2:
            self._search_history_after_id = self.after(450, lambda q=query: self._add_search_history_entry(q))
        else:
            self._search_history_after_id = None

    def _select_all(self) -> None:
        self._tree.set_all_checked(True)

    def _deselect_all(self) -> None:
        self._tree.set_all_checked(False)

    def _expand_all(self) -> None:
        self._tree.expand_all()

    def _collapse_all(self) -> None:
        self._tree.collapse_all()

    def _on_connect(self) -> None:
        connect_sessions(self, self._tree.get_selected_sessions())

    def _resolve_single_session_user(self, session: Session, title: str = "Benutzername auswählen") -> str | None:
        return resolve_single_session_user(self, session, title=title)

    def _quick_connect_session(self, session: Session) -> None:
        quick_connect_session(self, session)

    def _get_all_folder_names(self) -> list[str]:
        """Gibt alle bekannten Ordnernamen aus allen Session-Quellen zurück."""
        folders = set()
        for s in self._sessions:
            if s.folder_key:
                folders.add(s.folder_key)
        return sorted(folders)

    def _get_ssh_aliases(self) -> list[str]:
        """Gibt alle SSH-Config-Aliases zurück (für Alias-Picker im Dialog)."""
        return sorted(s.display_name for s in self._sessions if s.source == "ssh_config")

    def _rebuild_sessions(self, *, reload_winscp: bool = False) -> None:
        """Merged alle Session-Quellen und aktualisiert den Baum."""
        self._ssh_config_sessions = load_ssh_config_sessions()
        self._filezilla_sessions = load_filezilla_config_sessions()
        if reload_winscp:
            try:
                self._winscp_sessions = RegistryReader().load_sessions()
            except OSError as e:
                messagebox.showerror(
                    "Registry-Fehler",
                    f"WinSCP-Sessions konnten nicht geladen werden:\n{e}\n\n"
                    f"Pfad: HKCU\\{REGISTRY_PATH}",
                    parent=self,
                )
                self._winscp_sessions = []
        self._sessions = self._build_visible_sessions()
        self._tree.refresh(self._sessions)

    def _reload_sessions(self) -> None:
        """Lädt WinSCP- und SSH-Config-Sessions erneut ein und aktualisiert die Ansicht."""
        self._rebuild_sessions(reload_winscp=True)
        ToastNotification(self, "Verbindungen neu geladen")

    def _add_session(self, folder_preset: str = "") -> None:
        add_session(self, folder_preset=folder_preset)

    def _edit_session(self, session: Session) -> None:
        edit_session(self, session)

    def _duplicate_app_session(self, session: Session) -> None:
        duplicate_app_session(self, session)

    def _move_session(self, session: Session) -> None:
        move_session(self, session)

    def _move_sessions(self, sessions: list[Session]) -> None:
        move_sessions(self, sessions)

    def _delete_session(self, session: Session) -> None:
        delete_session(self, session)

    def _delete_folder(self, sessions: list[Session], folder_key: str) -> None:
        delete_folder(self, sessions, folder_key)

    def _rename_folder(self, folder_key: str) -> None:
        rename_folder(self, folder_key)

    def _duplicate_ssh_alias(self, session: Session) -> None:
        duplicate_ssh_alias(self, session)

    def _inspect_ssh_config(self, session: Session) -> None:
        inspect_ssh_config(self, session)

    def _open_ssh_config_in_vscode(self) -> None:
        open_ssh_config_in_vscode(self)

    def _open_appdata_jsons_in_vscode(self) -> None:
        """Öffnet den SSH-Manager-AppData-Ordner mit JSON-Dateien in VS Code."""
        open_appdata_jsons_in_vscode(self)

    def _deploy_ssh_key(self, sessions: list[Session]) -> None:
        deploy_ssh_key(self, sessions)

    def _remove_ssh_key(self, sessions: list[Session]) -> None:
        remove_ssh_key(self, sessions)

    def _open_tunnel(self, session: Session | None = None) -> None:
        open_tunnel(self, session=session)

    def _open_via_jumphost(self, session: Session) -> None:
        open_via_jumphost(self, session)

    def _resolve_users_for_sessions(self, sessions: list[Session], mode: str) -> list[tuple[Session, str]] | None:
        return resolve_users_for_sessions(self, sessions, mode)

    def _run_remote_command(self, sessions: list[Session]) -> None:
        run_remote_command(self, sessions)

    def _open_in_winscp(self, sessions: list[Session]) -> None:
        open_in_winscp(self, sessions)

    def _on_close(self) -> None:
        self._persist_ui_state()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SSHManagerApp()
    app.mainloop()
