from __future__ import annotations

from tkinter import messagebox, simpledialog

from .constants import _APPDATA_DIR
from .dialogs import MoveFolderDialog, SessionEditDialog
from .models import Session
from .storage import save_app_sessions, save_notes


def add_session(app, folder_preset: str = "") -> None:
    """Öffnet den Dialog zum Anlegen einer neuen Session (App oder SSH-Alias)."""
    dialog = SessionEditDialog(
        app,
        app._get_all_folder_names(),
        ssh_aliases=app._get_ssh_aliases(),
        folder_preset=folder_preset,
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return
    app._app_sessions.append(dialog.result)
    if dialog.note_result:
        app._notes[dialog.result.key] = dialog.note_result
    else:
        app._notes.pop(dialog.result.key, None)
    save_notes(app._notes)
    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def edit_session(app, session: Session) -> None:
    """Öffnet den Dialog zum Bearbeiten einer App-Session."""
    dialog = SessionEditDialog(app, app._get_all_folder_names(), session=session, note=app._notes.get(session.key, ""))
    app.wait_window(dialog)
    if dialog.result is None:
        return
    for i, existing in enumerate(app._app_sessions):
        if existing.key == session.key:
            app._app_sessions[i] = dialog.result
            break
    if dialog.note_result:
        app._notes[dialog.result.key] = dialog.note_result
    else:
        app._notes.pop(dialog.result.key, None)
    save_notes(app._notes)
    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def duplicate_app_session(app, session: Session) -> None:
    """Dupliziert eine App-Session (öffnet Dialog mit vorausgefüllten Daten, neue UUID)."""
    dialog = SessionEditDialog(app, app._get_all_folder_names(), session=session, duplicate=True)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    app._app_sessions.append(dialog.result)
    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def move_session(app, session: Session) -> None:
    """Verschiebt eine App- oder SSH-Alias-Session in einen anderen Ordner."""
    dialog = MoveFolderDialog(app, app._get_all_folder_names(), session.folder_key)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    folder_path = [p for p in dialog.result.split("/") if p]
    for i, existing in enumerate(app._app_sessions):
        if existing.key == session.key:
            app._app_sessions[i] = Session(
                key=existing.key,
                display_name=existing.display_name,
                folder_path=folder_path,
                hostname=existing.hostname,
                username=existing.username,
                port=existing.port,
                source=existing.source,
            )
            break
    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def move_sessions(app, sessions: list[Session]) -> None:
    """Verschiebt mehrere App-/SSH-Alias-Sessions in denselben Ordner."""
    dialog = MoveFolderDialog(app, app._get_all_folder_names(), sessions[0].folder_key)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    folder_path = [p for p in dialog.result.split("/") if p]
    keys = {session.key for session in sessions}
    for i, existing in enumerate(app._app_sessions):
        if existing.key in keys:
            app._app_sessions[i] = Session(
                key=existing.key,
                display_name=existing.display_name,
                folder_path=folder_path,
                hostname=existing.hostname,
                username=existing.username,
                port=existing.port,
                source=existing.source,
            )
    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def delete_session(app, session: Session) -> None:
    """Löscht eine App-Session nach Bestätigung."""
    if not messagebox.askyesno(
        "Verbindung löschen",
        f"Verbindung '{session.display_name}' wirklich löschen?",
        parent=app,
    ):
        return
    app._app_sessions = [existing for existing in app._app_sessions if existing.key != session.key]
    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def delete_folder(app, sessions: list[Session], folder_key: str) -> None:
    """Löscht alle App-Sessions in einem Ordner nach Bestätigung."""
    if not messagebox.askyesno(
        "Ordner löschen",
        f"Ordner '{folder_key}' und alle {len(sessions)} Verbindung(en) darin löschen?",
        parent=app,
    ):
        return
    keys_to_delete = {session.key for session in sessions}
    app._app_sessions = [existing for existing in app._app_sessions if existing.key not in keys_to_delete]
    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def rename_folder(app, folder_key: str) -> None:
    """Benennt einen Ordner um, indem folder_path aller enthaltenen Sessions angepasst wird."""
    parts = folder_key.split("/")
    depth = len(parts) - 1
    old_name = parts[depth]
    prefix = parts[:depth]

    new_name = simpledialog.askstring(
        "Ordner umbenennen",
        f"Neuer Name für '{old_name}':",
        initialvalue=old_name,
        parent=app,
    )
    if not new_name or new_name.strip() == old_name:
        return
    new_name = new_name.strip()

    for session in app._app_sessions:
        folder_path = session.folder_path
        if len(folder_path) > depth and folder_path[:depth] == prefix and folder_path[depth] == old_name:
            session.folder_path = folder_path[:depth] + [new_name] + folder_path[depth + 1:]

    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def duplicate_ssh_alias(app, session: Session) -> None:
    """Dupliziert einen SSH-Config-Alias in einen anderen Ordner."""
    dialog = SessionEditDialog(
        app,
        app._get_all_folder_names(),
        ssh_aliases=app._get_ssh_aliases(),
        alias_preset=session.display_name,
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return
    app._app_sessions.append(dialog.result)
    save_app_sessions(app._app_sessions)
    app._rebuild_sessions()


def open_appdata_jsons_in_vscode(app) -> None:
    """Öffnet den SSH-Manager-AppData-Ordner mit JSON-Dateien in VS Code."""
    try:
        _APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        app._popen_shell(f'code "{_APPDATA_DIR}"')
    except OSError as exc:
        messagebox.showerror("VS Code nicht gefunden", f"Fehler beim Öffnen:\n{exc}")
