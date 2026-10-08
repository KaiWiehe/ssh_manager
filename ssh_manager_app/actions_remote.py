from __future__ import annotations

from tkinter import messagebox

from .core import (
    TerminalLaunchError,
    TerminalLauncher,
    _append_ssh_config_alias,
    build_jump_wt_command,
    build_remote_command_wt_command,
    build_remote_script_wt_command,
    build_ssh_copy_id_command,
    build_ssh_remove_key_command,
    build_ssh_tunnel_command,
)
from .actions_sessions import _set_session_username, set_session_username
from .actions_ui import add_recent_session, add_recent_sessions, rebuild_sessions
from .dialogs_remote import (
    JumpHostDialog,
    RemoteCommandConfirmDialog,
    RemoteCommandDialog,
    SshCopyIdDialog,
    SshRemoveKeyDialog,
    SshTunnelDialog,
)
from .dialogs_toast import ToastNotification
from .dialogs_user import UserDialog
from .models import Session


def connect_sessions(app, sessions: list[Session]) -> None:
    """Öffnet mehrere ausgewählte Sessions im Terminal; feste Benutzernamen werden bevorzugt."""
    if not sessions:
        return
    quick_users = list(app.settings.quick_users)
    default_user = app.settings.default_user
    terminal_settings = app.settings.windows_terminal
    shared_user = ""
    if any(not session.username for session in sessions):
        dialog = UserDialog(
            app,
            quick_users=quick_users,
            default_user=default_user,
            allow_remember=True,
            remember_label="Benutzer für alle Verbindungen merken",
        )
        app.wait_window(dialog)
        if dialog.result is None:
            return
        shared_user, remember = dialog.result
        if remember:
            for session in sessions:
                _set_session_username(app, session, shared_user)
            rebuild_sessions(app)
    try:
        app._terminal_launcher.launch(
            sessions,
            shared_user,
            app._tree.get_session_colors(),
            terminal_settings=terminal_settings,
        )
        add_recent_sessions(app, sessions)
    except TerminalLaunchError as exc:
        if exc.started_sessions:
            add_recent_sessions(app, exc.started_sessions)
        messagebox.showerror("Fehler beim Starten", str(exc), parent=app)
    except Exception as exc:
        messagebox.showerror("Fehler beim Starten", str(exc), parent=app)



def resolve_single_session_user(app, session: Session, title: str = "Benutzername auswählen") -> str | None:
    """Löst den Benutzernamen für genau eine Session auf."""
    if session.username:
        return session.username
    dialog = UserDialog(app, title=title, quick_users=list(app.settings.quick_users), default_user=app.settings.default_user, allow_remember=True)
    app.wait_window(dialog)
    if dialog.result is None:
        return None
    user, remember = dialog.result
    if remember:
        set_session_username(app, session, user)
    return user



def quick_connect_session(app, session: Session) -> None:
    """Öffnet eine einzelne Session direkt, etwa via Doppelklick oder Kontextmenü."""
    user = resolve_single_session_user(app, session)
    if user is None and not (session.is_ssh_config_session and session.username):
        return
    try:
        app._terminal_launcher.launch(
            [session],
            user or "",
            app._tree.get_session_colors(),
            terminal_settings=app.settings.windows_terminal,
        )
        add_recent_session(app, session)
    except TerminalLaunchError as exc:
        if exc.started_sessions:
            add_recent_session(app, session)
        messagebox.showerror("Fehler beim Starten", str(exc), parent=app)
    except Exception as exc:
        messagebox.showerror("Fehler beim Starten", str(exc), parent=app)



def deploy_ssh_key(app, sessions: list[Session]) -> None:
    """Öffnet den ssh-copy-id Dialog und startet den Key-Transfer im Terminal."""
    dialog = SshCopyIdDialog(app, target_count=len(sessions), quick_users=list(app.settings.quick_users), default_user=app.settings.default_user)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    key_filename, user = dialog.result
    from .operation_results import create_job, track_results
    job = None
    try:
        job = create_job(app, sessions, "SSH-Key verteilen", lambda failed: deploy_ssh_key(app, failed))
        with track_results(job):
            cmd = build_ssh_copy_id_command(sessions, key_filename, user, terminal_settings=app.settings.windows_terminal)
        TerminalLauncher.launch_built_command(
            cmd,
            [session.display_name for session in sessions],
            app.settings.windows_terminal,
        )
        if job:
            job.launched()
    except (OSError, RuntimeError, ValueError) as exc:
        if job:
            job.uncertain_launch()
        messagebox.showerror("Fehler", f"Fehler beim Starten:\n{exc}", parent=app)


def remove_ssh_key(app, sessions: list[Session]) -> None:
    """Öffnet den Remove-Key Dialog und entfernt den Key remote via SSH."""
    dialog = SshRemoveKeyDialog(app, target_count=len(sessions), quick_users=list(app.settings.quick_users), default_user=app.settings.default_user)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    key_filename, user = dialog.result
    from .operation_results import create_job, track_results
    job = None
    try:
        job = create_job(app, sessions, "SSH-Key entfernen", lambda failed: remove_ssh_key(app, failed))
        with track_results(job):
            cmd = build_ssh_remove_key_command(sessions, key_filename, user, terminal_settings=app.settings.windows_terminal)
        TerminalLauncher.launch_built_command(
            cmd,
            [session.display_name for session in sessions],
            app.settings.windows_terminal,
        )
        if job:
            job.launched()
    except (OSError, RuntimeError, ValueError) as exc:
        if job:
            job.uncertain_launch()
        messagebox.showerror("Fehler", f"Fehler beim Starten:\n{exc}", parent=app)


def open_tunnel(app, session: Session | None = None) -> None:
    """Öffnet den Tunnel-Dialog und startet den SSH-Tunnel im Terminal."""
    dialog = SshTunnelDialog(
        app,
        session=session,
        quick_users=list(app.settings.quick_users),
        default_user=app.settings.default_user,
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return
    jumphost, local_port, remote_host, remote_port, user = dialog.result
    try:
        cmd = build_ssh_tunnel_command(jumphost, local_port, remote_host, remote_port, user, terminal_settings=app.settings.windows_terminal)
        TerminalLauncher.launch_built_command(
            cmd,
            [f"SSH-Tunnel {user}@{jumphost}"],
            app.settings.windows_terminal,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        messagebox.showerror("Fehler", f"Fehler beim Starten:\n{exc}", parent=app)


def resolve_users_for_sessions(app, sessions: list[Session], mode: str, *, shared_user: str | None = None) -> list[tuple[Session, str]] | None:
    """Löst Benutzernamen für Sessions auf, global oder pro Host."""
    resolved: list[tuple[Session, str]] = []
    if mode == "all":
        missing = [session for session in sessions if not session.username]
        if missing and not shared_user:
            dialog = UserDialog(app, title="Benutzername für alle Hosts", quick_users=list(app.settings.quick_users), default_user=app.settings.default_user)
            app.wait_window(dialog)
            if dialog.result is None:
                return None
            shared_user = dialog.result
        for session in sessions:
            user = session.username if session.username else shared_user
            if not user:
                messagebox.showwarning("Fehlender Benutzer", f"Für '{session.display_name}' konnte kein Benutzer bestimmt werden.", parent=app)
                return None
            resolved.append((session, user))
        return resolved

    for session in sessions:
        if session.username:
            resolved.append((session, session.username))
            continue
        dialog = UserDialog(app, title=f"Benutzername für {session.display_name}", quick_users=list(app.settings.quick_users), default_user=app.settings.default_user)
        app.wait_window(dialog)
        if dialog.result is None:
            return None
        resolved.append((session, dialog.result))
    return resolved


def run_remote_command(app, sessions: list[Session], *, run_mode: str | None = None, initial_spec: dict | None = None) -> None:
    """Führt einen Remote-Befehl auf einem oder mehreren Hosts aus."""
    runnable = [session for session in sessions if session.hostname]
    if not runnable:
        messagebox.showwarning("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=app)
        return

    dialog_kwargs = {
        "target_count": len(runnable),
        "last_command": app._initial_toolbar_search_texts.get("last_remote_command", ""),
        "quick_users": list(app.settings.quick_users),
        "default_user": app.settings.default_user,
    }
    remote_history = list(app._initial_toolbar_search_texts.get("remote_command_history", []))
    remote_favorites = list(app._initial_toolbar_search_texts.get("remote_command_favorites", []))
    if run_mode is not None:
        dialog_kwargs["run_mode"] = run_mode
        if run_mode == "remote_script":
            dialog_kwargs["reference_sessions"] = runnable
        remote_history = [item for item in remote_history if item.get("mode", "command") == run_mode]
        remote_favorites = [item for item in remote_favorites if item.get("mode", "command") == run_mode]
    if remote_history:
        dialog_kwargs["history"] = remote_history
    if remote_favorites:
        dialog_kwargs["favorites"] = remote_favorites
    dialog = RemoteCommandDialog(app, **dialog_kwargs)
    if initial_spec is not None:
        dialog._apply_spec(initial_spec)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    sudo_password = ""
    if len(dialog.result) == 3:
        user_mode, command, close_on_success = dialog.result
        spec = {"mode": "command", "command": command, "interpreter": "bash", "path": ""}
        save_favorite = False
    else:
        user_mode, spec, close_on_success, save_favorite, *password_result = dialog.result
        sudo_password = password_result[0] if password_result else ""
        command = spec.get("command", "")
    if initial_spec is not None:
        spec = {**initial_spec, **spec}
    if hasattr(dialog, "_favorites"):
        other_favorites = [item for item in app._initial_toolbar_search_texts.get("remote_command_favorites", []) if run_mode is not None and item.get("mode", "command") != run_mode]
        app._initial_toolbar_search_texts["remote_command_favorites"] = (list(dialog._favorites) + other_favorites)[:25]
    app._initial_toolbar_search_texts["last_remote_command"] = command
    history = list(app._initial_toolbar_search_texts.get("remote_command_history", []))
    label = spec.get("name") or spec.get("path") or (command.splitlines()[0] if command else "Ausführung")
    history_item = {"label": label, **spec}
    history = [item for item in history if item != history_item]
    history.insert(0, history_item)
    app._initial_toolbar_search_texts["remote_command_history"] = history[:25]
    if save_favorite:
        favorites = list(app._initial_toolbar_search_texts.get("remote_command_favorites", []))
        if history_item not in favorites:
            favorites.insert(0, history_item)
        app._initial_toolbar_search_texts["remote_command_favorites"] = favorites[:25]

    entered_user = dialog._user_var.get() if hasattr(dialog, "_user_var") else None
    user_options = {"shared_user": entered_user.strip()} if user_mode == "all" and isinstance(entered_user, str) and entered_user.strip() else {}
    session_users = resolve_users_for_sessions(app, runnable, user_mode, **user_options)
    if session_users is None:
        return

    runtime_spec = spec
    display_spec = spec
    if spec.get("parameters"):
        from .runbook_parameters import RunbookParametersDialog, prepare_parameter_spec
        try:
            inputs = RunbookParametersDialog(app, spec["parameters"])
            app.wait_window(inputs)
            if inputs.result is None:
                return
            values = inputs.result
            runtime_spec = prepare_parameter_spec(spec, values)
            display_spec = prepare_parameter_spec(spec, values, redact=True)
            runtime_spec["_display_spec"] = display_spec
            values.clear()
            inputs.result = None
        except ValueError:
            messagebox.showwarning("Ungültige Parameter", "Die Runbook-Parameter bitte in der Bibliothek prüfen.", parent=app)
            return
    preview = display_spec if spec.get("mode") != "command" else display_spec["command"]
    confirm = RemoteCommandConfirmDialog(app, preview, session_users, close_on_success)
    app.wait_window(confirm)
    if not confirm.result:
        return

    from .operation_results import create_job, track_results
    job = None
    try:
        job = create_job(app, [session for session, _ in session_users], "Remote-Ausführung", lambda failed: run_remote_command(app, failed, run_mode=spec.get("mode", "command"), initial_spec=dict(spec)))
        with track_results(job):
            if spec.get("mode") == "command":
                build_kwargs = {
                    "close_on_success": close_on_success,
                    "session_colors": app._tree.get_session_colors(),
                    "terminal_settings": app.settings.windows_terminal,
                }
                if sudo_password:
                    build_kwargs["sudo_password"] = sudo_password
                if spec.get("parameters"):
                    build_kwargs["display_command"] = display_spec["command"]
                cmd = build_remote_command_wt_command([(session, user, runtime_spec["command"]) for session, user in session_users], **build_kwargs)
            else:
                build_kwargs = {
                    "close_on_success": close_on_success,
                    "session_colors": app._tree.get_session_colors(),
                    "terminal_settings": app.settings.windows_terminal,
                }
                if sudo_password:
                    build_kwargs["sudo_password"] = sudo_password
                cmd = build_remote_script_wt_command([(session, user, runtime_spec) for session, user in session_users], **build_kwargs)
        sudo_password = ""
        dialog.result = None
        TerminalLauncher.launch_built_command(
            cmd,
            [session.display_name for session, _user in session_users],
            app.settings.windows_terminal,
        )
        if job:
            job.launched()
    except (OSError, RuntimeError, ValueError) as exc:
        if job:
            job.uncertain_launch()
        from .errors import record_failure
        record_failure(exc)
        messagebox.showerror("Fehler", "Der Remote-Aufruf konnte nicht vorbereitet oder gestartet werden. Bitte Eingaben und Dateizugriff prüfen.", parent=app)
    finally:
        sudo_password = ""
        runtime_spec = None
        dialog.result = None


def _resolve_copy_user(app, sessions: list[Session]) -> str | None:
    """Fragt einen Benutzer für alle Sessions ohne festen User ab."""
    if not any((not s.username) and (not s.is_ssh_config_session) for s in sessions):
        return ""
    title = "Benutzername für SSH-Befehl" if len(sessions) == 1 else "Benutzername für SSH-Befehle"
    dialog = UserDialog(
        app,
        title=title,
        quick_users=list(app.settings.quick_users),
        default_user=app.settings.default_user,
        allow_remember=False,
    )
    app.wait_window(dialog)
    if dialog.result is None:
        return None
    return dialog.result[0] if isinstance(dialog.result, tuple) else dialog.result


def _ssh_copy_command_for_session(session: Session, fallback_user: str = "") -> str | None:
    if session.is_ssh_config_session:
        return f"ssh {session.display_name}"
    if not session.hostname:
        return None
    user = session.username or fallback_user
    if not user:
        return None
    if session.port and session.port != 22:
        return f"ssh -p {session.port} {user}@{session.hostname}"
    return f"ssh {user}@{session.hostname}"


def copy_ssh_commands(app, sessions: list[Session]) -> None:
    """Kopiert simple ssh-Befehle für eine oder mehrere Sessions in die Zwischenablage."""
    runnable = [session for session in sessions if session.is_ssh_config_session or session.hostname]
    if not runnable:
        messagebox.showwarning("Keine Hosts", "Für die Auswahl sind keine kopierbaren SSH-Ziele hinterlegt.", parent=app)
        return
    fallback_user = _resolve_copy_user(app, runnable)
    if fallback_user is None:
        return
    commands = [cmd for session in runnable if (cmd := _ssh_copy_command_for_session(session, fallback_user))]
    if not commands:
        messagebox.showwarning("Kein Benutzer", "Ohne Benutzer konnte kein SSH-Befehl erzeugt werden.", parent=app)
        return
    text = "\n".join(commands)
    app.clipboard_clear()
    app.clipboard_append(text)
    ToastNotification(app, f"{len(commands)} SSH-Befehl(e) kopiert")


def copy_ssh_command(app, session: Session) -> None:
    """Kopiert einen simplen ssh-Befehl für eine Session in die Zwischenablage."""
    copy_ssh_commands(app, [session])


def open_via_jumphost(app, session: Session) -> None:
    """Öffnet eine einzelne Verbindung temporär über einen Jumphost."""
    dialog = JumpHostDialog(app, session, app._sessions, open_folders_getter=app._tree.get_open_folders)
    app.wait_window(dialog)

    if dialog.save_result is not None:
        alias, jump_host, jump_port, jump_user, _target_key = dialog.save_result
        target_user = resolve_single_session_user(app, session, title=f"Benutzername für {session.display_name}")
        if target_user is None:
            return
        try:
            _append_ssh_config_alias(alias, session, target_user, jump_host, jump_user, jump_port)
        except ValueError as exc:
            messagebox.showwarning("SSH-Config", str(exc), parent=app)
            return
        except OSError as exc:
            messagebox.showerror("SSH-Config", f"Fehler beim Schreiben von ~/.ssh/config:\n{exc}", parent=app)
            return
        rebuild_sessions(app, reload_winscp=True)
        ToastNotification(app, f"SSH-Config '{alias}' gespeichert")
        return

    if dialog.result is None:
        return

    jump_host, jump_user, jump_port = dialog.result
    target_user = resolve_single_session_user(app, session, title=f"Benutzername für {session.display_name}")
    if target_user is None:
        return
    try:
        cmd = build_jump_wt_command(
            session,
            target_user,
            jump_host,
            jump_user or None,
            jump_port,
            app._tree.get_session_colors().get(session.key),
            terminal_settings=app.settings.windows_terminal,
        )
        TerminalLauncher.launch_built_command(
            cmd,
            [session.display_name],
            app.settings.windows_terminal,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        messagebox.showerror("Fehler", f"Fehler beim Starten:\n{exc}", parent=app)
