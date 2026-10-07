"""Session-local undo deltas. Remote actions and credentials never enter it."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
from tkinter import messagebox


def snapshot(app):
    return deepcopy({"sessions": {session.key: session for session in app._app_sessions}, "notes": app._notes,
                     "colors": app._tree.get_session_colors(), "favorites": app._favorite_sessions,
                     "overrides": app._session_user_overrides, "recent": app._recent_sessions})


def local_undo(label, *, tree=False):
    def decorate(action):
        @wraps(action)
        def perform(owner, *args, **kwargs):
            app = owner.__dict__.get("_undo_owner") if tree else owner
            if app is None or not app.__dict__.get("_local_undo_enabled") or app.__dict__.get("_undo_depth", 0):
                return action(owner, *args, **kwargs)
            before = snapshot(app)
            app._undo_depth = 1
            try:
                result = action(owner, *args, **kwargs)
                after = snapshot(app)
                if before != after:
                    from .actions_ui import persist_ui_state
                    persist_ui_state(app)
                    app._undo_stack.append((label, before, after))
                    app._undo_stack = app._undo_stack[-20:]
                return result
            finally:
                app._undo_depth = 0
        return perform
    return decorate


def cleanup_session_metadata(app, keys):
    for key in keys:
        app._notes.pop(key, None)
        app._favorite_sessions.pop(key, None)
        app._session_user_overrides.pop(key, None)
        app._tree.set_session_color(key, None)
    app._recent_sessions = [key for key in app._recent_sessions if key not in keys]


def reverted_snapshot(current, before, after):
    result = deepcopy(current)
    affected = set()
    for field in ("sessions", "notes", "colors", "favorites", "overrides"):
        missing = object()
        keys = set(before[field]) | set(after[field])
        for key in keys:
            if before[field].get(key, missing) == after[field].get(key, missing):
                continue
            affected.add(key)
            if key in before[field]:
                result[field][key] = deepcopy(before[field][key])
            else:
                result[field].pop(key, None)
    if before["recent"] != after["recent"]:
        # Preserve later connections to unrelated hosts.
        restored = [key for key in before["recent"] if key in affected]
        result["recent"] = restored + [key for key in current["recent"] if key not in affected]
        result["recent"] = result["recent"][:10]
    return result


def undo_last(app):
    stack = app.__dict__.get("_undo_stack", [])
    if not stack:
        messagebox.showinfo("Lokales Rückgängig", "Keine lokale Änderung in dieser App-Sitzung vorhanden. Remote-Aktionen sind nicht rückgängig machbar.", parent=app)
        return
    label, before, after = stack[-1]
    restored = reverted_snapshot(snapshot(app), before, after)
    from .storage import save_local_undo_state, _APP_SESSIONS_FILE
    from .actions_ui import current_ui_state, build_visible_sessions
    expanded, _colors, toolbar = current_ui_state(app)
    toolbar.update(favorite_sessions=restored["favorites"], session_user_overrides=restored["overrides"], recent_sessions=restored["recent"])
    sessions = list(restored["sessions"].values())
    try:
        save_local_undo_state(sessions, restored["notes"], expanded, restored["colors"], toolbar)
    except OSError:
        pending = _APP_SESSIONS_FILE.with_name("session-notes-pending.json").exists()
        messagebox.showerror("Rückgängig konnte nicht gespeichert werden", "Verlauf bleibt erhalten. " + ("Die App wird geschlossen; beim nächsten Start wird das gespeicherte Journal fertiggestellt." if pending else "Originalzustand bleibt erhalten; Dateizugriff prüfen."), parent=app)
        if pending:
            app.destroy()
        return
    app._undo_depth = 1
    try:
        app._app_sessions, app._notes = sessions, restored["notes"]
        app._favorite_sessions, app._session_user_overrides, app._recent_sessions = restored["favorites"], restored["overrides"], restored["recent"]
        app._tree._session_colors = restored["colors"]
        app._sessions = build_visible_sessions(app)
        app._tree.refresh(app._sessions)
        panel = app.__dict__.get("_details_panel")
        if panel:
            panel.refresh()
        stack.pop()
    finally:
        app._undo_depth = 0
    from .dialogs_toast import ToastNotification
    ToastNotification(app, "Rückgängig: " + label)
