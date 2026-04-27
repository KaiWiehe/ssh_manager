"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import tkinter as tk
from tkinter import messagebox, ttk

from ssh_manager_app import (
    AppSettings,
    ToolbarSettings,
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

from ssh_manager_app.ui import build_main_ui, close_app_callback, configure_app_styles
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
    on_selection_changed,
    reset_session_colors,
    reset_settings,
    reset_view_state,
    select_all,
)
from ssh_manager_app.actions_sessions import add_session, open_appdata_jsons_in_vscode
from ssh_manager_app.actions_app import get_all_folder_names, get_ssh_aliases, show_search_history_menu

if TYPE_CHECKING:
    from ssh_manager_app.dialogs_settings_misc import SettingsView


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
        self._sessions = build_visible_sessions(self)

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
        self.protocol("WM_DELETE_WINDOW", lambda: close_app_callback(self))

    def get_default_user(self) -> str:
        return self.settings.default_user

    def get_quick_users(self) -> list[str]:
        return list(self.settings.quick_users)

    def get_terminal_settings(self) -> WindowsTerminalSettings:
        return self.settings.windows_terminal

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

    def _on_selection_changed(self, count: int) -> None:
        on_selection_changed(self, count)

    def _select_all(self) -> None:
        select_all(self)

    def _deselect_all(self) -> None:
        deselect_all(self)

    def _expand_all(self) -> None:
        expand_all(self)

    def _collapse_all(self) -> None:
        collapse_all(self)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SSHManagerApp()
    app.mainloop()
