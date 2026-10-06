from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from copy import deepcopy

from .dialogs_toast import ToastNotification
from .models import AppearanceSettings, AppSettings, SourceVisibilitySettings, ToolbarSettings, Session
from .storage import load_filezilla_config_sessions, load_ssh_config_sessions, save_settings, save_ui_state
from .ui import configure_app_styles, layout_toolbar_buttons, refresh_checkbox_images


def preview_toolbar_visibility(app, toolbar_settings: ToolbarSettings) -> None:
    app.settings = replace(app.settings, toolbar=deepcopy(toolbar_settings))
    layout_toolbar_buttons(app)
    app._tree.update_toolbar_settings(toolbar_settings)


_COLUMN_LABELS_DE = {
    "username": "Benutzer",
    "hostname": "Hostname",
    "port": "Port",
    "notes": "Notizen",
}


def hide_column_from_header(app, column_key: str) -> None:
    """Blendet eine Tabellenspalte aus.

    Wiederverwendung der bestehenden Toolbar-/Spalten-Settings-Mechanik:
    setzt `show_<col>_column = False` auf den persistierten Settings, speichert
    sie ueber den ueblichen Settings-Pfad und aktualisiert die Sichtbarkeit.
    """
    visibility_attr = f"show_{column_key}_column"
    persisted = getattr(app, "_persisted_settings", app.settings)
    toolbar = persisted.toolbar
    if not hasattr(toolbar, visibility_attr):
        return
    if not getattr(toolbar, visibility_attr):
        return
    new_order = [c for c in toolbar.column_order if c != column_key]
    new_toolbar = replace(toolbar, **{visibility_attr: False}, column_order=new_order)
    new_settings = replace(persisted, toolbar=new_toolbar)
    save_settings(new_settings)
    app.settings = deepcopy(new_settings)
    app._persisted_settings = deepcopy(new_settings)
    preview_toolbar_visibility(app, new_toolbar)
    if getattr(app, "_settings_view", None) is not None:
        try:
            app._settings_view.load_from_app()
        except Exception:
            pass
    label = _COLUMN_LABELS_DE.get(column_key, column_key)
    ToastNotification(
        app,
        f"Spalte '{label}' ausgeblendet \u2013 in den Einstellungen wieder aktivierbar.",
        duration_ms=4000,
    )



def preview_source_visibility(app, source_visibility: SourceVisibilitySettings) -> None:
    app.settings = replace(app.settings, source_visibility=deepcopy(source_visibility))
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    persist_ui_state(app)



def preview_appearance(app, appearance: AppearanceSettings) -> None:
    if app.settings.appearance == appearance:
        return
    app.settings = replace(app.settings, appearance=deepcopy(appearance))
    configure_app_styles(app)
    refresh_checkbox_images(app)
    if getattr(app, "_settings_view", None) is not None:
        app._settings_view.tkraise()


def persist_ui_state(app) -> None:
    toolbar_texts = {
        "main": app._search_var.get(),
        "last_remote_command": app._initial_toolbar_search_texts.get("last_remote_command", ""),
        "search_history": list(app._search_history),
    }
    remote_history = list(app._initial_toolbar_search_texts.get("remote_command_history", []))
    if remote_history:
        toolbar_texts["remote_command_history"] = remote_history
    remote_favorites = list(app._initial_toolbar_search_texts.get("remote_command_favorites", []))
    if remote_favorites:
        toolbar_texts["remote_command_favorites"] = remote_favorites
    if "certificate_replace_whitelist" in app._initial_toolbar_search_texts:
        toolbar_texts["certificate_replace_whitelist"] = list(app._initial_toolbar_search_texts["certificate_replace_whitelist"])
    # Persist UI-pref sub-dicts that other features write to
    # ``_initial_toolbar_search_texts`` (e.g. command palette width).
    command_palette_prefs = app._initial_toolbar_search_texts.get("command_palette")
    if isinstance(command_palette_prefs, dict) and command_palette_prefs:
        toolbar_texts["command_palette"] = dict(command_palette_prefs)
    if "_favorite_sessions" in getattr(app, "__dict__", {}):
        toolbar_texts["favorite_sessions"] = dict(app._favorite_sessions)
    if "_recent_sessions" in getattr(app, "__dict__", {}):
        toolbar_texts["recent_sessions"] = list(app._recent_sessions)
    if "_session_user_overrides" in getattr(app, "__dict__", {}):
        toolbar_texts["session_user_overrides"] = dict(app._session_user_overrides)
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
    save_settings(settings)
    app.settings = deepcopy(settings)
    app._persisted_settings = deepcopy(settings)
    configure_app_styles(app)
    refresh_checkbox_images(app)
    layout_toolbar_buttons(app)
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    app._search_entry.focus_set()
    from .ui import reapply_shortcut_bindings
    reapply_shortcut_bindings(app)
    ToastNotification(app, "Einstellungen gespeichert")



def reset_settings(app) -> None:
    apply_settings(app, app._default_settings_factory())
    app._persisted_settings = deepcopy(app.settings)
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
        status_var = app.__dict__.get("_selection_status_var")
        if status_var is not None:
            status_var.set(f"{count} Verbindung{'en' if count != 1 else ''} ausgewählt")
    else:
        app._connect_btn.config(text="Verbinden", state=tk.DISABLED)
        status_var = app.__dict__.get("_selection_status_var")
        if status_var is not None:
            status_var.set("Keine Verbindung ausgewählt")



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



def _with_effective_username(app, session: Session) -> Session:
    override = getattr(app, "_session_user_overrides", {}).get(session.key)
    if override is not None:
        return replace(session, username=override)
    if session.source == "winscp" and not app.settings.import_settings.winscp_include_username:
        return replace(session, username="")
    if session.source == "filezilla_config" and not app.settings.import_settings.filezilla_include_username:
        return replace(session, username="")
    return session


def build_visible_sessions(app) -> list[Session]:
    base: list[Session] = []
    if app.settings.source_visibility.show_winscp:
        base.extend(_with_effective_username(app, s) for s in app._winscp_sessions)
    if app.settings.source_visibility.show_app_connections:
        base.extend(_with_effective_username(app, s) for s in app._app_sessions)
    if app.settings.source_visibility.show_ssh_config:
        base.extend(_with_effective_username(app, s) for s in app._ssh_config_sessions)
    if app.settings.source_visibility.show_filezilla_config:
        base.extend(_with_effective_username(app, s) for s in app._filezilla_sessions)

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
        recent_sessions = [by_key[key] for key in getattr(app, "_recent_sessions", []) if key in by_key]
        special.extend(replace(s, folder_path=["↺ Zuletzt verwendet"]) for s in recent_sessions[:10])
    return special + sorted_normal



def _migrate_filezilla_in_app(app) -> None:
    if not any(session.legacy_key for session in app._filezilla_sessions):
        return
    from .storage import migrate_filezilla_metadata, save_filezilla_migration
    toolbar = dict(app._initial_toolbar_search_texts)
    toolbar.update(favorite_sessions=dict(app._favorite_sessions), recent_sessions=list(app._recent_sessions),
                   session_user_overrides=dict(app._session_user_overrides))
    colors = app._tree.get_session_colors()
    migrated = migrate_filezilla_metadata(app._filezilla_sessions, app._notes, colors, toolbar)
    if migrated != (app._notes, colors, toolbar):
        app._notes, new_colors, new_toolbar = migrated
        app._initial_toolbar_search_texts = new_toolbar
        app._favorite_sessions = new_toolbar.get("favorite_sessions", {})
        app._recent_sessions = new_toolbar.get("recent_sessions", [])
        app._session_user_overrides = new_toolbar.get("session_user_overrides", {})
        previous_suppression = app._tree._suppress_open_state_events
        app._tree._suppress_open_state_events = previous_suppression + 1
        try:
            for key in colors.keys() - new_colors.keys():
                app._tree.set_session_color(key, None)
            for key, value in new_colors.items():
                if colors.get(key) != value:
                    app._tree.set_session_color(key, value)
        finally:
            app._tree._suppress_open_state_events = previous_suppression
        save_filezilla_migration(app._tree.get_open_folders(), *migrated)


def rebuild_sessions(app, *, reload_winscp: bool = False) -> None:
    app._ssh_config_sessions = load_ssh_config_sessions()
    app._filezilla_sessions = load_filezilla_config_sessions()
    _migrate_filezilla_in_app(app)
    success = True
    if reload_winscp:
        from tkinter import messagebox
        try:
            reader = app._registry_reader()
            app._winscp_sessions = reader.load_sessions()
            warnings = getattr(reader, "warnings", [])
            if isinstance(warnings, list) and warnings:
                messagebox.showwarning("WinSCP-Import", "\n".join(warnings), parent=app)
                success = False
        except FileNotFoundError:
            app._winscp_sessions = []
        except OSError:
            messagebox.showerror("Registry-Fehler", "WinSCP-Sessions konnten nicht neu geladen werden. Der bisherige Stand bleibt angezeigt.", parent=app)
            success = False
    from .storage import take_load_warnings
    warnings = take_load_warnings()
    if warnings:
        from tkinter import messagebox
        messagebox.showwarning("Import unvollständig", "\n\n".join(warnings), parent=app)
        success = False
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    return success



def add_recent_session(app, session: Session) -> None:
    add_recent_sessions(app, [session])


def add_recent_sessions(app, sessions: list[Session]) -> None:
    recent = list(getattr(app, "_recent_sessions", []))
    for session in reversed(sessions):
        recent = [key for key in recent if key != session.key]
        recent.insert(0, session.key)
    app._recent_sessions = recent[:10]
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
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
    """Activate the focused tree row, independent of checkbox selection."""
    app._tree.activate_focused()


def connect_selected_sessions(app) -> None:
    """Connect all checked sessions; do nothing when none are checked."""
    from .actions_remote import connect_sessions

    selected = app._tree.get_selected_sessions()
    if selected:
        connect_sessions(app, selected)


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


def toggle_recent_folder(app) -> None:
    """Toggle visibility of the virtual 'Recently used' folder."""
    visibility = app.settings.source_visibility
    new_visibility = replace(visibility, show_recent=not visibility.show_recent)
    persisted = getattr(app, "_persisted_settings", app.settings)
    new_settings = replace(persisted, source_visibility=new_visibility)
    save_settings(new_settings)
    app.settings = deepcopy(new_settings)
    app._persisted_settings = deepcopy(new_settings)
    preview_source_visibility(app, new_visibility)
    state = "sichtbar" if new_visibility.show_recent else "ausgeblendet"
    ToastNotification(app, f"'Zuletzt verwendet' jetzt {state}")


def edit_focused_session(app) -> None:
    """Edit the currently focused or single-selected editable session."""
    from .actions_sessions import edit_session, edit_session_details

    selected = app._tree.get_selected_sessions()
    target = selected[0] if len(selected) == 1 else app._tree.get_single_context_session()
    if target is None:
        return
    if target.source in ("app", "ssh_alias"):
        edit_session(app, target)
    else:
        edit_session_details(app, target)


def open_command_palette(app) -> None:
    """Open the VSCode-style command palette."""
    from .actions_app import open_command_palette as _impl

    _impl(app)


def reload_sessions(app) -> None:
    if rebuild_sessions(app, reload_winscp=True) is not False:
        ToastNotification(app, "Verbindungen neu geladen")
