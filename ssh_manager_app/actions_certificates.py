from __future__ import annotations

import subprocess
from tkinter import messagebox

from .actions_remote import resolve_users_for_sessions
from .core import build_certificate_deploy_wt_command
from .dialogs_certificates import CertificateDeployDialog
from .models import Session


def deploy_certificate_files(app, sessions: list[Session]) -> None:
    """Upload selected certificate files to each selected host."""
    runnable = [session for session in sessions if session.hostname]
    if not runnable:
        messagebox.showwarning("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=app)
        return

    session_users = resolve_users_for_sessions(app, runnable, "all")
    if session_users is None:
        return

    favorites = list(app._initial_toolbar_search_texts.get("remote_command_favorites", []))
    dialog = CertificateDeployDialog(
        app,
        target_count=len(runnable),
        reference_sessions=session_users,
        favorites=favorites,
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return

    deployment = dialog.result
    overwrite_text = "Ja" if deployment["overwrite"] else "Nein (vorhandene Dateien blockieren den Host)"
    post_text = "Ja" if deployment["post_command"] else "Nein"
    target_dirs = deployment["target_dirs"]
    target_preview = "\n".join(f"  - {path}" for path in target_dirs)
    confirmation = (
        f"Dateien: {len(deployment['files'])}\n"
        f"Hosts: {len(runnable)}\n"
        f"Zielordner ({len(target_dirs)}):\n{target_preview}\n"
        f"Überschreiben: {overwrite_text}\n"
        f"Nach-Befehl: {post_text}\n\n"
        "Übertragung jetzt starten?"
    )
    if not messagebox.askyesno("Dateiübertragung bestätigen", confirmation, icon="warning", parent=app):
        return

    try:
        command = build_certificate_deploy_wt_command(
            [(session, user, deployment) for session, user in session_users],
            session_colors=app._tree.get_session_colors(),
            terminal_settings=app.settings.windows_terminal,
        )
        subprocess.Popen(command, shell=True)
    except OSError as exc:
        messagebox.showerror("Übertragung fehlgeschlagen", f"Terminal konnte nicht gestartet werden:\n{exc}", parent=app)
