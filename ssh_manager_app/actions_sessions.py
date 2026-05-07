from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .actions_app import get_all_folder_names, get_ssh_aliases
from .actions_ui import rebuild_sessions
from .constants import _APPDATA_DIR
from .dialogs_base import _USERNAME_RE
from .dialogs_move_folder import MoveFolderDialog
from .dialogs_session_edit import SessionEditDialog
from .models import Session
from .storage import save_app_sessions, save_notes


def add_session(app, folder_preset: str = "") -> None:
    """Öffnet den Dialog zum Anlegen einer neuen Session (App oder SSH-Alias)."""
    dialog = SessionEditDialog(
        app,
        get_all_folder_names(app),
        ssh_aliases=get_ssh_aliases(app),
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
    rebuild_sessions(app)


def edit_session(app, session: Session) -> None:
    """Öffnet den Dialog zum Bearbeiten einer App-Session."""
    dialog = SessionEditDialog(app, get_all_folder_names(app), session=session, note=app._notes.get(session.key, ""))
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
    rebuild_sessions(app)


def duplicate_app_session(app, session: Session) -> None:
    """Dupliziert eine App-Session (öffnet Dialog mit vorausgefüllten Daten, neue UUID)."""
    dialog = SessionEditDialog(app, get_all_folder_names(app), session=session, duplicate=True)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    app._app_sessions.append(dialog.result)
    save_app_sessions(app._app_sessions)
    rebuild_sessions(app)


def move_session(app, session: Session) -> None:
    """Verschiebt eine App- oder SSH-Alias-Session in einen anderen Ordner."""
    dialog = MoveFolderDialog(app, get_all_folder_names(app), session.folder_key)
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
    rebuild_sessions(app)


def move_sessions(app, sessions: list[Session]) -> None:
    """Verschiebt mehrere App-/SSH-Alias-Sessions in denselben Ordner."""
    dialog = MoveFolderDialog(app, get_all_folder_names(app), sessions[0].folder_key)
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
    rebuild_sessions(app)


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
    rebuild_sessions(app)


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
    rebuild_sessions(app)


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
    rebuild_sessions(app)


def duplicate_ssh_alias(app, session: Session) -> None:
    """Dupliziert einen SSH-Config-Alias in einen anderen Ordner."""
    dialog = SessionEditDialog(
        app,
        get_all_folder_names(app),
        ssh_aliases=get_ssh_aliases(app),
        alias_preset=session.display_name,
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return
    app._app_sessions.append(dialog.result)
    save_app_sessions(app._app_sessions)
    rebuild_sessions(app)


def open_appdata_jsons_in_vscode(app) -> None:
    """Öffnet den SSH-Manager-AppData-Ordner mit JSON-Dateien in VS Code."""
    try:
        _APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        app._popen_shell(f'code "{_APPDATA_DIR}"')
    except OSError as exc:
        messagebox.showerror("VS Code nicht gefunden", f"Fehler beim Öffnen:\n{exc}")


def _set_session_username(app, session: Session, username: str) -> None:
    """Setzt/entfernt einen festen Benutzer für App- oder importierte Sessions."""
    updated_app_session = False
    for i, existing in enumerate(app._app_sessions):
        if existing.key == session.key:
            app._app_sessions[i] = Session(
                key=existing.key,
                display_name=existing.display_name,
                folder_path=existing.folder_path,
                hostname=existing.hostname,
                username=username,
                port=existing.port,
                source=existing.source,
            )
            updated_app_session = True
            break
    if updated_app_session:
        save_app_sessions(app._app_sessions)
    else:
        if username:
            app._session_user_overrides[session.key] = username
        else:
            app._session_user_overrides.pop(session.key, None)


def set_session_username(app, session: Session, username: str) -> None:
    _set_session_username(app, session, username.strip())
    rebuild_sessions(app)


def set_sessions_username(app, sessions: list[Session]) -> None:
    user = simpledialog.askstring(
        "Benutzer setzen",
        f"Benutzername für {len(sessions)} Verbindung(en):",
        initialvalue=app.settings.default_user,
        parent=app,
    )
    if user is None:
        return
    user = user.strip()
    if not user:
        messagebox.showwarning("Benutzer setzen", "Benutzername darf nicht leer sein.", parent=app)
        return
    if not _USERNAME_RE.match(user):
        messagebox.showwarning("Ungültiger Benutzername", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=app)
        return
    for session in sessions:
        _set_session_username(app, session, user)
    rebuild_sessions(app)


def clear_sessions_username(app, sessions: list[Session]) -> None:
    if not messagebox.askyesno(
        "Benutzer entfernen",
        f"Fest gesetzten Benutzer für {len(sessions)} Verbindung(en) entfernen?\n\nDanach wird beim Verbinden wieder gefragt.",
        parent=app,
    ):
        return
    for session in sessions:
        _set_session_username(app, session, "")
    rebuild_sessions(app)


def edit_session_details(app, session: Session) -> None:
    """Bearbeitet festen Benutzer und Notiz für jede Session-Art."""
    dialog = tk.Toplevel(app)
    dialog.title("Verbindung bearbeiten")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=16)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)

    username_var = tk.StringVar(value=session.username)
    ttk.Label(frame, text=f"Verbindung: {session.display_name}").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
    ttk.Label(frame, text="Fester Benutzer:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
    ttk.Entry(frame, textvariable=username_var, width=34).grid(row=1, column=1, sticky="ew", pady=(0, 6))
    ttk.Label(frame, text="Leer lassen = beim Verbinden fragen", foreground="#666666").grid(row=2, column=1, sticky="w", pady=(0, 10))
    ttk.Label(frame, text="Notiz:").grid(row=3, column=0, sticky="nw", padx=(0, 8))
    note_text = tk.Text(frame, width=42, height=6)
    note_text.grid(row=3, column=1, sticky="ew")
    note = app._notes.get(session.key, "")
    if note:
        note_text.insert("1.0", note)

    result = {"saved": False}

    def on_ok() -> None:
        username = username_var.get().strip()
        if username and not _USERNAME_RE.match(username):
            messagebox.showwarning("Ungültiger Benutzername", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=dialog)
            return
        _set_session_username(app, session, username)
        note_value = note_text.get("1.0", "end").strip()
        if note_value:
            app._notes[session.key] = note_value
        else:
            app._notes.pop(session.key, None)
        save_notes(app._notes)
        result["saved"] = True
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=4, column=0, columnspan=2, pady=(12, 0))
    ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side="left", padx=4)
    ttk.Button(btn_frame, text="Abbrechen", command=on_cancel, width=10).pack(side="left", padx=4)
    dialog.bind("<Escape>", lambda _e: on_cancel())
    dialog.bind("<Control-Return>", lambda _e: on_ok())
    app.wait_window(dialog)
    if result["saved"]:
        rebuild_sessions(app)
