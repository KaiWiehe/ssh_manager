from __future__ import annotations

from tkinter import messagebox
from pathlib import Path

from .actions_remote import resolve_users_for_sessions
from .core import TerminalLauncher, build_certificate_deploy_wt_command, build_file_upload_wt_command
from .dialogs_certificates import CertificateDeployDialog
from .models import Session


def deploy_certificate_files(app, sessions: list[Session], *, simple: bool = False) -> None:
    """Upload selected certificate files to each selected host."""
    runnable = [session for session in sessions if session.hostname]
    if not runnable:
        messagebox.showwarning("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=app)
        return
    if simple and len(runnable) != 1:
        messagebox.showwarning("Ein Host erforderlich", "Für ‚Datei hochladen‘ genau eine Verbindung wählen. Für mehrere Hosts ‚Dateien verteilen‘ verwenden.", parent=app)
        return

    session_users = resolve_users_for_sessions(app, runnable, "all")
    if session_users is None:
        return

    favorites = list(app._initial_toolbar_search_texts.get("remote_command_favorites", []))
    dialog_options = {"simple": True} if simple else {}
    dialog = CertificateDeployDialog(
        app,
        target_count=len(runnable),
        reference_sessions=session_users,
        favorites=favorites,
        **dialog_options,
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return

    deployment = dict(dialog.result)
    dialog.result = None
    overwrite_text = "Ja" if deployment["overwrite"] else "Nein (vorhandene Dateien blockieren den Host)"
    post_text = "Ja" if deployment["post_command"] else "Nein"
    target_dirs = deployment["target_dirs"]
    target_preview = "\n".join(f"  - {path}" for path in target_dirs)
    owners = deployment.get("owners", {})
    rights_preview = "\n".join(f"  - {session.display_name}: {owners.get(session.key, user)}" for session, user in session_users)
    mode_preview = "\n".join(f"  - {Path(path).name}: {mode}" for path, mode in deployment.get("file_modes", {}).items())
    confirmation = (
        f"Dateien: {len(deployment['files'])}\n"
        f"Hosts: {len(runnable)} – " + ", ".join(session.display_name for session in runnable) + "\n"
        f"Zielordner ({len(target_dirs)}):\n{target_preview}\n"
        f"Überschreiben: {overwrite_text}\n"
        f"Nach-Befehl: {post_text}\n\n"
        f"Dateibesitzer (primäre Gruppe):\n{rights_preview}\n"
        f"Rechte neuer Dateien:\n{mode_preview}\n"
        f"Vorhandene Rechte: {'gewählte Regel anwenden' if deployment.get('apply_to_existing') else 'beibehalten'}\n\n"
        "Übertragung jetzt starten?"
    )
    if simple:
        confirmation = f"Datei: {Path(deployment['files'][0]).name}\nHost: {runnable[0].display_name} ({runnable[0].hostname})\nZielordner: {target_dirs[0]}\nÜberschreiben: {overwrite_text}\n\nOhne sudo. Neue Dateien sind nur für den Benutzer lesbar/schreibbar; bei Überschreiben bleiben bestehende Rechte und Besitzer erhalten. Übertragung starten?"
    if not messagebox.askyesno("Dateiübertragung bestätigen", confirmation, icon="warning", parent=app):
        return

    try:
        builder = build_file_upload_wt_command if simple else build_certificate_deploy_wt_command
        command = builder(
            [(session, user, {**deployment, "file_owner": owners[session.key]} if owners else deployment) for session, user in session_users],
            session_colors=app._tree.get_session_colors(),
            terminal_settings=app.settings.windows_terminal,
        )
        deployment.pop("sudo_password", None)
        TerminalLauncher.launch_built_command(
            command,
            [session.display_name for session, _user in session_users],
            app.settings.windows_terminal,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        deployment.pop("sudo_password", None)
        messagebox.showerror("Übertragung fehlgeschlagen", f"Terminal konnte nicht gestartet werden:\n{exc}", parent=app)
