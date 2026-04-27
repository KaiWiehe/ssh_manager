from __future__ import annotations

import subprocess
from tkinter import messagebox

from .core import (
    build_remote_command_wt_command,
    build_ssh_copy_id_command,
    build_ssh_remove_key_command,
    build_ssh_tunnel_command,
)
from .dialogs import RemoteCommandConfirmDialog, RemoteCommandDialog, SshCopyIdDialog, SshRemoveKeyDialog, SshTunnelDialog, UserDialog
from .models import Session


def deploy_ssh_key(app, sessions: list[Session]) -> None:
    """Öffnet den ssh-copy-id Dialog und startet den Key-Transfer im Terminal."""
    dialog = SshCopyIdDialog(app, target_count=len(sessions), quick_users=app.get_quick_users(), default_user=app.get_default_user())
    app.wait_window(dialog)
    if dialog.result is None:
        return
    key_filename, user = dialog.result
    try:
        cmd = build_ssh_copy_id_command(sessions, key_filename, user, terminal_settings=app.get_terminal_settings())
        subprocess.Popen(cmd, shell=True)
    except OSError as exc:
        messagebox.showerror("Fehler", f"Fehler beim Starten:\n{exc}")


def remove_ssh_key(app, sessions: list[Session]) -> None:
    """Öffnet den Remove-Key Dialog und entfernt den Key remote via SSH."""
    dialog = SshRemoveKeyDialog(app, target_count=len(sessions), quick_users=app.get_quick_users(), default_user=app.get_default_user())
    app.wait_window(dialog)
    if dialog.result is None:
        return
    key_filename, user = dialog.result
    try:
        cmd = build_ssh_remove_key_command(sessions, key_filename, user, terminal_settings=app.get_terminal_settings())
        subprocess.Popen(cmd, shell=True)
    except OSError as exc:
        messagebox.showerror("Fehler", f"Fehler beim Starten:\n{exc}")


def open_tunnel(app, session: Session | None = None) -> None:
    """Öffnet den Tunnel-Dialog und startet den SSH-Tunnel im Terminal."""
    dialog = SshTunnelDialog(
        app,
        session=session,
        quick_users=app.get_quick_users(),
        default_user=app.get_default_user(),
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return
    jumphost, local_port, remote_host, remote_port, user = dialog.result
    try:
        cmd = build_ssh_tunnel_command(jumphost, local_port, remote_host, remote_port, user, terminal_settings=app.get_terminal_settings())
        subprocess.Popen(cmd)
    except OSError as exc:
        messagebox.showerror("Fehler", f"Fehler beim Starten:\n{exc}")


def resolve_users_for_sessions(app, sessions: list[Session], mode: str) -> list[tuple[Session, str]] | None:
    """Löst Benutzernamen für Sessions auf, global oder pro Host."""
    resolved: list[tuple[Session, str]] = []
    if mode == "all":
        missing = [session for session in sessions if not (session.is_ssh_config_session and session.username)]
        shared_user = None
        if missing:
            dialog = UserDialog(app, title="Benutzername für alle Hosts")
            app.wait_window(dialog)
            if dialog.result is None:
                return None
            shared_user = dialog.result
        for session in sessions:
            user = session.username if session.is_ssh_config_session and session.username else shared_user
            if not user:
                messagebox.showwarning("Fehlender Benutzer", f"Für '{session.display_name}' konnte kein Benutzer bestimmt werden.", parent=app)
                return None
            resolved.append((session, user))
        return resolved

    for session in sessions:
        if session.is_ssh_config_session and session.username:
            resolved.append((session, session.username))
            continue
        dialog = UserDialog(app, title=f"Benutzername für {session.display_name}")
        app.wait_window(dialog)
        if dialog.result is None:
            return None
        resolved.append((session, dialog.result))
    return resolved


def run_remote_command(app, sessions: list[Session]) -> None:
    """Führt einen Remote-Befehl auf einem oder mehreren Hosts aus."""
    runnable = [session for session in sessions if session.hostname]
    if not runnable:
        messagebox.showwarning("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=app)
        return

    dialog = RemoteCommandDialog(
        app,
        target_count=len(runnable),
        last_command=app._initial_toolbar_search_texts.get("last_remote_command", ""),
        quick_users=app.get_quick_users(),
        default_user=app.get_default_user(),
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return
    user_mode, command, close_on_success = dialog.result
    app._initial_toolbar_search_texts["last_remote_command"] = command

    session_users = resolve_users_for_sessions(app, runnable, user_mode)
    if session_users is None:
        return

    confirm = RemoteCommandConfirmDialog(app, command, session_users, close_on_success)
    app.wait_window(confirm)
    if not confirm.result:
        return

    cmd = build_remote_command_wt_command(
        [(session, user, command) for session, user in session_users],
        close_on_success=close_on_success,
        session_colors=app._tree.get_session_colors(),
        terminal_settings=app.get_terminal_settings(),
    )
    try:
        subprocess.Popen(cmd, shell=True)
    except OSError as exc:
        messagebox.showerror("Fehler", f"Fehler beim Starten:\n{exc}", parent=app)
