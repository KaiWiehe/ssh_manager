from __future__ import annotations

import tkinter as tk

from .actions_ui import apply_search_history_entry, clear_search_history, persist_ui_state


def show_search_history_menu(app) -> None:
    menu = tk.Menu(app, tearoff=False)
    if app._search_history:
        for item in app._search_history:
            menu.add_command(label=item, command=lambda v=item: apply_search_history_entry(app, v))
        menu.add_separator()
        menu.add_command(label="Verlauf leeren", command=lambda: clear_search_history(app))
    else:
        menu.add_command(label="Kein Suchverlauf", state=tk.DISABLED)
    x = app._search_history_btn.winfo_rootx()
    y = app._search_history_btn.winfo_rooty() + app._search_history_btn.winfo_height()
    menu.tk_popup(x, y)



def get_all_folder_names(app) -> list[str]:
    """Gibt alle bekannten Ordnernamen aus allen Session-Quellen zurück."""
    folders = {session.folder_key for session in app._sessions if session.folder_key}
    return sorted(folders)



def get_ssh_aliases(app) -> list[str]:
    """Gibt alle SSH-Config-Aliases zurück (für Alias-Picker im Dialog)."""
    return sorted(session.display_name for session in app._sessions if session.source == "ssh_config")



def export_settings_dialog(app) -> None:
    if app._settings_view is None:
        return
    app._settings_view._export_settings()



def import_settings_dialog(app) -> None:
    if app._settings_view is None:
        return
    app._settings_view._import_settings()



def close_app(app) -> None:
    persist_ui_state(app)
    app.destroy()


def open_command_palette(app) -> None:
    """Open the VSCode-style command palette."""
    from .palette import CommandPaletteDialog, CommandPaletteItem
    from .actions_remote import connect_sessions, quick_connect_session
    from .actions_ui import (
        collapse_all,
        deselect_all,
        expand_all,
        focus_search,
        invert_selection,
        reload_sessions,
        select_all,
        show_settings_view,
        toggle_recent_folder,
    )
    from .actions_sessions import add_session, delete_session, edit_session, edit_session_details
    from .actions_dns import open_dns_lookup_dialog

    if getattr(app, "_command_palette", None) is not None:
        try:
            app._command_palette.destroy()
        except Exception:
            pass
        app._command_palette = None

    # Build session items.
    sessions = list(getattr(app, "_sessions", []))
    seen_keys: set[str] = set()
    session_items: list[CommandPaletteItem] = []
    recent_keys = list(getattr(app, "_recent_sessions", []))
    recent_lookup = {key: idx for idx, key in enumerate(recent_keys)}
    for session in sessions:
        if session.key in seen_keys:
            continue
        seen_keys.add(session.key)
        subtitle_parts: list[str] = []
        if session.username:
            subtitle_parts.append(f"{session.username}@{session.hostname or session.display_name}")
        elif session.hostname:
            subtitle_parts.append(session.hostname)
        if session.folder_key:
            subtitle_parts.append(session.folder_key)
        subtitle = " · ".join(subtitle_parts)
        recent_idx = recent_lookup.get(session.key)
        recent_score = (100 - recent_idx * 5) if recent_idx is not None else 0
        session_ref = session  # bind for closure
        session_items.append(CommandPaletteItem(
            id=f"session:{session.key}",
            label=session.display_name,
            subtitle=subtitle,
            kind="session",
            callback=lambda s=session_ref: quick_connect_session(app, s),
            recent_score=recent_score,
        ))

    # Build action items.
    def _connect_selection() -> None:
        sel = app._tree.get_selected_sessions()
        if sel:
            connect_sessions(app, sel)

    def _edit_selection() -> None:
        sel = app._tree.get_selected_sessions()
        target = sel[0] if len(sel) == 1 else None
        if target is None:
            return
        if target.source in ("app", "ssh_alias"):
            edit_session(app, target)
        else:
            edit_session_details(app, target)

    def _delete_selection() -> None:
        sel = app._tree.get_selected_sessions()
        target = sel[0] if len(sel) == 1 else None
        if target is None or target.source not in ("app", "ssh_alias"):
            return
        delete_session(app, target)

    def _accel(action_id: str) -> str:
        mgr = getattr(app, "_shortcut_manager", None)
        return mgr.current_mapping().get(action_id, "") if mgr else ""

    action_items = [
        CommandPaletteItem("act:connect", "Verbinden mit Auswahl", _accel("connect"),
                           kind="action", callback=_connect_selection),
        CommandPaletteItem("act:edit", "Bearbeiten", _accel("edit"),
                           kind="action", callback=_edit_selection),
        CommandPaletteItem("act:delete", "Löschen", _accel("delete"),
                           kind="action", callback=_delete_selection),
        CommandPaletteItem("act:new_session", "Neue Verbindung", _accel("new_session"),
                           kind="action", callback=lambda: add_session(app)),
        CommandPaletteItem("act:settings", "Einstellungen öffnen", _accel("open_settings"),
                           kind="action", callback=lambda: show_settings_view(app)),
        CommandPaletteItem("act:focus_search", "Suche fokussieren", _accel("focus_search"),
                           kind="action", callback=lambda: focus_search(app)),
        CommandPaletteItem("act:refresh", "Sessions neu laden", _accel("refresh"),
                           kind="action", callback=lambda: reload_sessions(app)),
        CommandPaletteItem("act:dns_lookup", "DNS/IP auflösen…", "",
                           kind="action", callback=lambda: open_dns_lookup_dialog(app)),
        CommandPaletteItem("act:select_all", "Alle auswählen", _accel("select_all"),
                           kind="action", callback=lambda: select_all(app)),
        CommandPaletteItem("act:deselect_all", "Alle abwählen", _accel("deselect_all"),
                           kind="action", callback=lambda: deselect_all(app)),
        CommandPaletteItem("act:invert", "Auswahl umkehren", _accel("invert_selection"),
                           kind="action", callback=lambda: invert_selection(app)),
        CommandPaletteItem("act:expand_all", "Ordner ausklappen", "",
                           kind="action", callback=lambda: expand_all(app)),
        CommandPaletteItem("act:collapse_all", "Ordner einklappen", "",
                           kind="action", callback=lambda: collapse_all(app)),
        CommandPaletteItem("act:toggle_recent", "Ordner 'Zuletzt verwendet' umschalten", _accel("toggle_recent_folder"),
                           kind="action", callback=lambda: toggle_recent_folder(app)),
        CommandPaletteItem("act:import", "Einstellungen importieren…", _accel("import_settings"),
                           kind="action", callback=lambda: import_settings_dialog(app)),
        CommandPaletteItem("act:export", "Einstellungen exportieren…", _accel("export_settings"),
                           kind="action", callback=lambda: export_settings_dialog(app)),
    ]

    # Recent commands track recent_score so they bubble to the top when the
    # query is empty.
    recent_actions = list(getattr(app, "_recent_command_palette_actions", []))
    for idx, action_id in enumerate(recent_actions):
        for item in action_items:
            if item.id == action_id:
                item.recent_score = 80 - idx * 5
                break

    # Wrap callbacks so we remember recently-used palette actions.
    def _wrap_action_callback(item: CommandPaletteItem):
        original = item.callback
        if original is None:
            return

        def wrapped(action_id=item.id, cb=original):
            recents = list(getattr(app, "_recent_command_palette_actions", []))
            recents = [a for a in recents if a != action_id]
            recents.insert(0, action_id)
            app._recent_command_palette_actions = recents[:10]
            cb()

        item.callback = wrapped

    for item in action_items:
        _wrap_action_callback(item)

    # Load persisted palette width (sub-dict under toolbar_search_texts).
    palette_prefs_raw = getattr(app, "_initial_toolbar_search_texts", {}).get("command_palette", {})
    palette_prefs = palette_prefs_raw if isinstance(palette_prefs_raw, dict) else {}
    saved_width = palette_prefs.get("width")

    def _persist_palette_width(width: int) -> None:
        prefs = getattr(app, "_initial_toolbar_search_texts", None)
        if not isinstance(prefs, dict):
            return
        bucket_raw = prefs.get("command_palette")
        bucket = bucket_raw if isinstance(bucket_raw, dict) else {}
        bucket["width"] = int(width)
        prefs["command_palette"] = bucket
        try:
            persist_ui_state(app)
        except Exception:
            # Settings persistence must never break the palette close path.
            pass

    dialog = CommandPaletteDialog(
        app,
        sessions=session_items,
        actions=action_items,
        initial_width=saved_width,
        on_width_changed=_persist_palette_width,
    )
    app._command_palette = dialog

    def _on_destroy(_e=None):
        if getattr(app, "_command_palette", None) is dialog:
            app._command_palette = None

    dialog.bind("<Destroy>", _on_destroy)
