"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ssh_manager_app import (
    AppSettings,
    ToolbarSettings,
    SourceVisibilitySettings,
    Session,
    WindowsTerminalSettings,
    WINDOW_MIN_SIZE,
    WINDOW_TITLE,
    REGISTRY_PATH,
    default_settings,
    load_app_sessions,
    load_filezilla_config_sessions,
    load_notes,
    load_settings,
    load_ssh_config_sessions,
    load_ui_state,
    save_app_sessions,
)

from ssh_manager_app.constants import _SSH_CONFIG_DEFAULT_FOLDER

from ssh_manager_app.core import (
    RegistryReader,
    TerminalLauncher,
    _create_checkbox_images,
)

from ssh_manager_app.ui import build_main_ui, configure_app_styles
from ssh_manager_app.actions_ui import (
    add_search_history_entry,
    apply_search_history_entry,
    apply_settings,
    build_visible_sessions,
    clear_search_history,
    collapse_all,
    deselect_all,
    expand_all,
    invert_selection,
    on_search_changed,
    on_selection_changed,
    persist_ui_state,
    preview_source_visibility,
    preview_toolbar_visibility,
    rebuild_sessions,
    reload_sessions,
    reset_session_colors,
    reset_settings,
    reset_view_state,
    select_all,
    show_main_view,
    show_settings_view,
    update_notes_info,
)
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
from ssh_manager_app.actions_app import (
    close_app,
    export_settings_dialog,
    get_all_folder_names,
    get_ssh_aliases,
    import_settings_dialog,
    show_search_history_menu,
)
from ssh_manager_app.actions_notes import edit_session_note
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

from ssh_manager_app.dialogs import SettingsView

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
        self._registry_reader = RegistryReader
        self._registry_path = REGISTRY_PATH
        self._default_settings_factory = default_settings
        self._ssh_config_default_folder = _SSH_CONFIG_DEFAULT_FOLDER

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
        add_search_history_entry(self, value)

    def _apply_search_history_entry(self, value: str) -> None:
        apply_search_history_entry(self, value)

    def _show_search_history_menu(self) -> None:
        show_search_history_menu(self)

    def _clear_search_history(self) -> None:
        clear_search_history(self)

    def _build_visible_sessions(self) -> list[Session]:
        return build_visible_sessions(self)

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
        preview_toolbar_visibility(self, toolbar_settings)

    def preview_source_visibility(self, source_visibility: SourceVisibilitySettings) -> None:
        preview_source_visibility(self, source_visibility)

    def _edit_session_note(self, session: Session) -> None:
        edit_session_note(self, session)

    def get_default_user(self) -> str:
        return self.settings.default_user

    def get_quick_users(self) -> list[str]:
        return list(self.settings.quick_users)

    def get_terminal_settings(self) -> WindowsTerminalSettings:
        return self.settings.windows_terminal

    def _export_settings_dialog(self) -> None:
        export_settings_dialog(self)

    def _import_settings_dialog(self) -> None:
        import_settings_dialog(self)

    def _persist_ui_state(self) -> None:
        persist_ui_state(self)

    def show_settings_view(self) -> None:
        show_settings_view(self)

    def show_main_view(self) -> None:
        show_main_view(self)

    def apply_settings(self, settings: AppSettings) -> None:
        apply_settings(self, settings)

    def reset_settings(self) -> None:
        reset_settings(self)

    def _reset_session_colors(self) -> None:
        reset_session_colors(self)

    def reset_view_state(self) -> None:
        reset_view_state(self)

    def _invert_selection(self) -> None:
        invert_selection(self)

    def _update_notes_info(self, session: Session | None = None) -> None:
        update_notes_info(self, session)

    def _on_selection_changed(self, count: int) -> None:
        on_selection_changed(self, count)

    def _on_search_changed(self) -> None:
        on_search_changed(self)

    def _select_all(self) -> None:
        select_all(self)

    def _deselect_all(self) -> None:
        deselect_all(self)

    def _expand_all(self) -> None:
        expand_all(self)

    def _collapse_all(self) -> None:
        collapse_all(self)

    def _on_connect(self) -> None:
        connect_sessions(self, self._tree.get_selected_sessions())

    def _resolve_single_session_user(self, session: Session, title: str = "Benutzername auswählen") -> str | None:
        return resolve_single_session_user(self, session, title=title)

    def _quick_connect_session(self, session: Session) -> None:
        quick_connect_session(self, session)

    def _get_all_folder_names(self) -> list[str]:
        return get_all_folder_names(self)

    def _get_ssh_aliases(self) -> list[str]:
        return get_ssh_aliases(self)

    def _rebuild_sessions(self, *, reload_winscp: bool = False) -> None:
        rebuild_sessions(self, reload_winscp=reload_winscp)

    def _reload_sessions(self) -> None:
        reload_sessions(self)

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
        close_app(self)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SSHManagerApp()
    app.mainloop()
