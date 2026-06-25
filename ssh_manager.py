"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import tkinter as tk
from tkinter import messagebox, ttk

from ssh_manager_app import (
    Session,
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
)

from ssh_manager_app.constants import _SSH_CONFIG_DEFAULT_FOLDER

from ssh_manager_app.core import (
    RegistryReader,
    TerminalLauncher,
    _create_checkbox_images,
)

from ssh_manager_app.ui import build_main_ui, close_app_callback, configure_app_styles
from ssh_manager_app.actions_ui import build_visible_sessions
from ssh_manager_app.version import APP_NAME

if TYPE_CHECKING:
    from ssh_manager_app.dialogs_settings_misc import SettingsView


def set_window_icon(window: tk.Tk) -> None:
    """Configure the Windows title-bar/taskbar icon robustly.

    PyInstaller embeds the EXE resource icon from ``ssh_manager.spec``.  Tk still
    needs the runtime window icon set explicitly, otherwise Windows 11 can show a
    generic/blank icon for the actual window even though the assets themselves
    are valid.  ``iconbitmap`` and ``iconphoto`` can override each other on
    Windows depending on timing, so we apply them in the safe order and repeat
    once after the window has been realized.
    """
    from pathlib import Path
    import sys

    def _set_windows_app_id() -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            app_id = "KaiWiehe.SSHManager.App"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            # Best-effort only.  Without this, the window icon still works; the
            # taskbar may just group/cache more aggressively on Windows.
            pass

    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    asset_dir = base_path / "assets"
    fallback_dir = Path(__file__).resolve().parent / "assets"

    def _resolve(name: str) -> Path | None:
        candidate = asset_dir / name
        if candidate.exists():
            return candidate
        candidate = fallback_dir / name
        return candidate if candidate.exists() else None

    png_path = _resolve("ssh-manager.png")
    ico_path = _resolve("ssh-manager.ico")

    _set_windows_app_id()

    photo: tk.PhotoImage | None = None
    if png_path is not None:
        try:
            photo = tk.PhotoImage(file=str(png_path))
            # Keep a reference on the window so Tcl doesn't garbage-collect it.
            window._icon_photo = photo  # type: ignore[attr-defined]
        except tk.TclError:
            photo = None

    def _apply() -> None:
        # On Windows, set the ICO first (native titlebar/taskbar fallback), then
        # iconphoto last so the high-resolution PNG wins for the Tk window.
        if ico_path is not None:
            try:
                window.iconbitmap(default=str(ico_path))
            except tk.TclError:
                pass
        if photo is not None:
            try:
                window.iconphoto(True, photo)
            except tk.TclError:
                pass

    _apply()
    try:
        window.after_idle(_apply)
    except tk.TclError:
        pass


class SSHManagerApp(tk.Tk):
    """Hauptfenster der SSH-Manager Applikation."""

    def __init__(self):
        super().__init__()
        self.title(APP_NAME or WINDOW_TITLE)
        set_window_icon(self)
        self.minsize(*WINDOW_MIN_SIZE)
        self.geometry("750x550")

        self.settings = load_settings()
        self._persisted_settings = self.settings
        self._startup_settings = self.settings
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
        self._initial_open_folders, self._initial_session_colors, self._initial_toolbar_search_texts = load_ui_state()
        self._favorite_sessions: dict[str, bool] = dict(self._initial_toolbar_search_texts.get("favorite_sessions", {}))
        self._recent_sessions: list[str] = list(self._initial_toolbar_search_texts.get("recent_sessions", []))
        self._session_user_overrides: dict[str, str] = dict(self._initial_toolbar_search_texts.get("session_user_overrides", {}))
        self._sessions = build_visible_sessions(self)

        # Checkbox-Images (nach Tk-Initialisierung erzeugen!)
        self._img_unchecked, self._img_checked = _create_checkbox_images(self)
        if self.settings.startup_expand_mode == "expanded":
            self._initial_open_folders = {s.folder_key for s in self._sessions if s.folder_key}
        elif self.settings.startup_expand_mode == "collapsed":
            self._initial_open_folders = set()
        self._toolbar_buttons: dict[str, ttk.Button] = {}
        self._terminal_launcher = TerminalLauncher
        self._main_frame: ttk.Frame | None = None
        self._settings_view: SettingsView | None = None
        build_main_ui(self)
        # Rebuild once after the tree exists so virtual folders (Favoriten/Zuletzt)
        # are rendered from the fully initialized persisted UI state.
        self._sessions = build_visible_sessions(self)
        self._tree.refresh(self._sessions)
        self.protocol("WM_DELETE_WINDOW", lambda: close_app_callback(self))

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SSHManagerApp()
    app.mainloop()
