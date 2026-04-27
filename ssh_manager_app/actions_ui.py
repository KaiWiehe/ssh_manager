from __future__ import annotations

import tkinter as tk

from .dialogs_toast import ToastNotification
from .models import AppSettings, Session, SourceVisibilitySettings, ToolbarSettings
from .storage import load_filezilla_config_sessions, load_ssh_config_sessions, save_settings, save_ui_state
from .ui import layout_toolbar_buttons


def preview_toolbar_visibility(app, toolbar_settings: ToolbarSettings) -> None:
    app.settings.toolbar = toolbar_settings
    layout_toolbar_buttons(app)
    app._tree.update_toolbar_settings(toolbar_settings)



def preview_source_visibility(app, source_visibility: SourceVisibilitySettings) -> None:
    app.settings.source_visibility = source_visibility
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    persist_ui_state(app)



def persist_ui_state(app) -> None:
    save_ui_state(
        app._tree.get_open_folders(),
        app._tree.get_session_colors(),
        {
            "main": app._search_var.get(),
            "last_remote_command": app._initial_toolbar_search_texts.get("last_remote_command", ""),
            "search_history": list(app._search_history),
        },
    )



def show_settings_view(app) -> None:
    if app._settings_view is None or app._main_frame is None:
        return
    app._settings_view.load_from_app()
    app._main_frame.grid_remove()
    app._settings_view.grid(row=0, column=0, sticky="nsew")



def show_main_view(app) -> None:
    if app._settings_view is not None:
        app._settings_view.grid_remove()
    if app._main_frame is not None:
        app._main_frame.grid()
    layout_toolbar_buttons(app)



def apply_settings(app, settings: AppSettings) -> None:
    app.settings = settings
    save_settings(settings)
    layout_toolbar_buttons(app)
    app._search_entry.focus_set()
    ToastNotification(app, "Einstellungen gespeichert")



def reset_settings(app) -> None:
    apply_settings(app, app._default_settings_factory())
    if app._settings_view is not None:
        app._settings_view.load_from_app()



def reset_session_colors(app) -> None:
    for session_key in list(app._tree.get_session_colors().keys()):
        app._tree.set_session_color(session_key, None)
    ToastNotification(app, "Farben zurückgesetzt")



def reset_view_state(app) -> None:
    app._search_var.set("")
    app._tree.populate(app._sessions, open_folders=set(app._initial_open_folders))
    current_colors = set(app._tree.get_session_colors())
    startup_colors = dict(app._initial_session_colors)
    for session_key in current_colors | set(startup_colors):
        app._tree.set_session_color(session_key, startup_colors.get(session_key))
    ToastNotification(app, "Ansicht auf Startzustand zurückgesetzt")



def invert_selection(app) -> None:
    app._tree.invert_checked()



def update_notes_info(app, session: Session | None = None) -> None:
    if not hasattr(app, "_notes_info_var"):
        return
    if session is None:
        app._notes_info_var.set("Notizinfo: Zeige den Mauszeiger auf Name oder Notiz, oder nutze Rechtsklick → Notiz bearbeiten…")
        return
    note = app._notes.get(session.key, "").strip()
    if note:
        app._notes_info_var.set(f"Notiz für {session.display_name}: {note}")
    else:
        app._notes_info_var.set(f"Notiz für {session.display_name}: Keine Notiz hinterlegt")



def on_selection_changed(app, count: int) -> None:
    if count > 0:
        app._connect_btn.config(text=f"Verbinden ({count} ausgewählt)", state=tk.NORMAL)
    else:
        app._connect_btn.config(text="Verbinden", state=tk.DISABLED)



def add_search_history_entry(app, value: str) -> None:
    query = value.strip()
    if len(query) < 2:
        return
    app._search_history = [item for item in app._search_history if item != query]
    app._search_history.insert(0, query)
    app._search_history = app._search_history[:10]
    persist_ui_state(app)



def apply_search_history_entry(app, value: str) -> None:
    app._search_var.set(value)
    app._search_entry.icursor("end")
    app._search_entry.focus_set()



def clear_search_history(app) -> None:
    app._search_history = []
    persist_ui_state(app)



def on_search_changed(app) -> None:
    value = app._search_var.get()
    app._tree.filter(value)
    persist_ui_state(app)
    app.after_cancel(app._search_history_after_id) if getattr(app, '_search_history_after_id', None) else None
    query = value.strip()
    if len(query) >= 2:
        app._search_history_after_id = app.after(450, lambda q=query: add_search_history_entry(app, q))
    else:
        app._search_history_after_id = None



def select_all(app) -> None:
    app._tree.set_all_checked(True)



def deselect_all(app) -> None:
    app._tree.set_all_checked(False)



def expand_all(app) -> None:
    app._tree.expand_all()



def collapse_all(app) -> None:
    app._tree.collapse_all()



def build_visible_sessions(app) -> list[Session]:
    visible: list[Session] = []
    if app.settings.source_visibility.show_winscp:
        visible.extend(app._winscp_sessions)
    if app.settings.source_visibility.show_app_connections:
        visible.extend(app._app_sessions)
    if app.settings.source_visibility.show_ssh_config:
        visible.extend(app._ssh_config_sessions)
    if app.settings.source_visibility.show_filezilla_config:
        visible.extend(app._filezilla_sessions)
    return sorted(
        visible,
        key=lambda s: (0 if s.folder_key == app._ssh_config_default_folder else 1, s.folder_key.lower(), s.display_name.lower()),
    )



def rebuild_sessions(app, *, reload_winscp: bool = False) -> None:
    app._ssh_config_sessions = load_ssh_config_sessions()
    app._filezilla_sessions = load_filezilla_config_sessions()
    if reload_winscp:
        try:
            app._winscp_sessions = app._registry_reader().load_sessions()
        except OSError as exc:
            from tkinter import messagebox
            messagebox.showerror(
                "Registry-Fehler",
                f"WinSCP-Sessions konnten nicht geladen werden:\n{exc}\n\nPfad: HKCU\\{app._registry_path}",
                parent=app,
            )
            app._winscp_sessions = []
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)



def reload_sessions(app) -> None:
    rebuild_sessions(app, reload_winscp=True)
    ToastNotification(app, "Verbindungen neu geladen")
