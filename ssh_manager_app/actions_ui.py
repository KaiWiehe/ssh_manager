from __future__ import annotations

import tkinter as tk
from dataclasses import replace

from .dialogs_toast import ToastNotification
from .models import AppearanceSettings, AppSettings, SourceVisibilitySettings, ToolbarSettings
from .storage import load_filezilla_config_sessions, load_ssh_config_sessions, save_settings, save_ui_state
from .ui import configure_app_styles, layout_toolbar_buttons


def preview_toolbar_visibility(app, toolbar_settings: ToolbarSettings) -> None:
    app.settings.toolbar = toolbar_settings
    layout_toolbar_buttons(app)
    app._tree.update_toolbar_settings(toolbar_settings)



def preview_source_visibility(app, source_visibility: SourceVisibilitySettings) -> None:
    app.settings.source_visibility = source_visibility
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    persist_ui_state(app)



def preview_appearance(app, appearance: AppearanceSettings) -> None:
    app.settings.appearance = appearance
    configure_app_styles(app)
    if getattr(app, "_settings_view", None) is not None:
        app._settings_view.tkraise()


def persist_ui_state(app) -> None:
    toolbar_texts = {
        "main": app._search_var.get(),
        "last_remote_command": app._initial_toolbar_search_texts.get("last_remote_command", ""),
        "search_history": list(app._search_history),
    }
    if "_favorite_sessions" in getattr(app, "__dict__", {}):
        toolbar_texts["favorite_sessions"] = dict(app._favorite_sessions)
    if "_recent_sessions" in getattr(app, "__dict__", {}):
        toolbar_texts["recent_sessions"] = list(app._recent_sessions)
    save_ui_state(
        app._tree.get_open_folders(),
        app._tree.get_session_colors(),
        toolbar_texts,
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
    configure_app_styles(app)
    layout_toolbar_buttons(app)
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    app._search_entry.focus_set()
    ToastNotification(app, "Einstellungen gespeichert")



def reset_settings(app) -> None:
    apply_settings(app, app._default_settings_factory())
    app._persisted_settings = app.settings
    if app._settings_view is not None:
        app._settings_view.load_from_app()



def restore_saved_settings(app) -> None:
    apply_settings(app, getattr(app, "_persisted_settings", app.settings))
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
    base: list[Session] = []
    if app.settings.source_visibility.show_winscp:
        base.extend(app._winscp_sessions)
    if app.settings.source_visibility.show_app_connections:
        base.extend(app._app_sessions)
    if app.settings.source_visibility.show_ssh_config:
        base.extend(app._ssh_config_sessions)
    if app.settings.source_visibility.show_filezilla_config:
        base.extend(app._filezilla_sessions)

    by_key = {s.key: s for s in base}
    favorites = getattr(app, "_favorite_sessions", {})
    sorted_normal = sorted(
        base,
        key=lambda s: (0 if s.folder_key == app._ssh_config_default_folder else 1, s.folder_key.lower(), s.display_name.lower()),
    )

    special: list[Session] = []
    if app.settings.source_visibility.show_favorites:
        for key, include_original_tree in favorites.items():
            if key not in by_key:
                continue
            session = by_key[key]
            favorite_folder = ["★ Favoriten"] + (list(session.folder_path) if include_original_tree else [])
            special.append(replace(session, folder_path=favorite_folder))
    if app.settings.source_visibility.show_recent:
        recent_sessions = [by_key[key] for key in getattr(app, "_recent_sessions", []) if key in by_key and key not in favorites]
        special.extend(replace(s, folder_path=["↺ Zuletzt verwendet"]) for s in recent_sessions[:10])
    return special + sorted_normal



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



def add_recent_session(app, session: Session) -> None:
    recent = [key for key in getattr(app, "_recent_sessions", []) if key != session.key]
    recent.insert(0, session.key)
    app._recent_sessions = recent[:10]
    persist_ui_state(app)


def set_favorite_session(app, session: Session, *, include_original_tree: bool) -> None:
    set_favorite_sessions(app, [session], include_original_tree=include_original_tree)


def set_favorite_sessions(app, sessions: list[Session], *, include_original_tree: bool) -> None:
    for session in sessions:
        app._favorite_sessions[session.key] = include_original_tree
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    persist_ui_state(app)


def remove_favorite_session(app, session: Session) -> None:
    app._favorite_sessions.pop(session.key, None)
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    persist_ui_state(app)


def connect_selected_or_focused(app) -> None:
    from .actions_remote import connect_sessions, quick_connect_session

    selected = app._tree.get_selected_sessions()
    if selected:
        connect_sessions(app, selected)
        return
    focused = app._tree.get_single_context_session()
    if focused is not None:
        quick_connect_session(app, focused)


def delete_focused_editable_session(app) -> None:
    from .actions_sessions import delete_session

    selected = app._tree.get_selected_sessions()
    target = selected[0] if len(selected) == 1 else app._tree.get_single_context_session()
    if target is None or target.source not in ("app", "ssh_alias"):
        return
    delete_session(app, target)


def focus_search(app) -> None:
    app._search_entry.focus_set()
    app._search_entry.select_range(0, "end")


def reload_sessions(app) -> None:
    rebuild_sessions(app, reload_winscp=True)
    ToastNotification(app, "Verbindungen neu geladen")
