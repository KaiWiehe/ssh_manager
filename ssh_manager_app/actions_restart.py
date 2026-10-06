from __future__ import annotations

import queue
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from tkinter import messagebox

from .actions_remote import resolve_users_for_sessions
from .dialogs_restart import ServerRestartDialog, ServerRestartProgressDialog
from .ssh_utils import connection_value
from .models import Session


POLL_INTERVAL_SECONDS = 2.0
SSH_PROBE_TIMEOUT_SECONDS = 8
SSH_REBOOT_TIMEOUT_SECONDS = 20
_CONNECTED_MARKER = "__SSH_MANAGER_CONNECTED__"
_BOOT_ID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


@dataclass(frozen=True)
class RestartResult:
    status: str
    detail: str


def _ssh_args(session: Session, user: str, connect_timeout: int = 5) -> list[str]:
    args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={max(1, int(connect_timeout))}",
        "-o",
        "ConnectionAttempts=1",
    ]
    if session.is_ssh_config_session:
        args.extend(["--", connection_value(session.display_name)])
        return args
    if session.port and session.port != 22:
        args.extend(["-p", str(session.port)])
    args.extend(["--", f"{connection_value(user)}@{connection_value(session.hostname)}"])
    return args


def _run_ssh(
    session: Session,
    user: str,
    remote_command: str,
    *,
    input_text: str | None = None,
    timeout: int = SSH_PROBE_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*_ssh_args(session, user), remote_command],
        input=input_text,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _process_error(completed: subprocess.CompletedProcess[str], fallback: str) -> str:
    value = (completed.stderr or completed.stdout or fallback).strip()
    compact = " ".join(value.split())
    return compact[:500] if compact else fallback


def _read_boot_id(session: Session, user: str) -> tuple[bool, str | None, str]:
    command = f"printf '%s\\n' '{_CONNECTED_MARKER}'; cat /proc/sys/kernel/random/boot_id 2>/dev/null || true"
    try:
        completed = _run_ssh(session, user, command)
    except subprocess.TimeoutExpired:
        return False, None, "SSH-Verbindung hat das Zeitlimit überschritten."
    except OSError as exc:
        return False, None, str(exc)
    if completed.returncode != 0 or _CONNECTED_MARKER not in completed.stdout.splitlines():
        return False, None, _process_error(completed, "SSH-Verbindung fehlgeschlagen.")
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip() and line.strip() != _CONNECTED_MARKER]
    boot_id = next((line for line in lines if _BOOT_ID_RE.fullmatch(line)), None)
    return True, boot_id, ""


def _service_load_state(session: Session, user: str, service: str) -> tuple[bool, str, str]:
    command = f"systemctl show --property=LoadState --value {shlex.quote(service)}"
    try:
        completed = _run_ssh(session, user, command)
    except subprocess.TimeoutExpired:
        return False, "", "Service-Prüfung hat das Zeitlimit überschritten."
    except OSError as exc:
        return False, "", str(exc)
    state = completed.stdout.strip().splitlines()[0].strip() if completed.stdout.strip() else ""
    if completed.returncode != 0:
        return False, state, _process_error(completed, f"systemd-Unit '{service}' konnte nicht geprüft werden.")
    if not state or state == "not-found":
        return True, state or "not-found", f"systemd-Unit '{service}' ist nicht vorhanden."
    return True, state, ""


def _service_active(session: Session, user: str, service: str) -> tuple[bool, bool, str]:
    command = f"systemctl is-active {shlex.quote(service)}"
    try:
        completed = _run_ssh(session, user, command)
    except subprocess.TimeoutExpired:
        return False, False, "SSH-Zeitüberschreitung"
    except OSError as exc:
        return False, False, str(exc)
    if completed.returncode == 255:
        return False, False, _process_error(completed, "SSH nicht erreichbar")
    state = (completed.stdout or completed.stderr).strip().splitlines()
    state_text = state[0].strip() if state else "unbekannt"
    return True, completed.returncode == 0 and state_text == "active", state_text


def _issue_reboot(session: Session, user: str, sudo_password: str) -> tuple[bool, bool, str]:
    if sudo_password:
        remote_command = "sudo -S -p '' reboot"
        input_text = sudo_password + "\n"
    else:
        remote_command = "sudo -n -p '' reboot"
        input_text = None
    try:
        completed = _run_ssh(
            session,
            user,
            remote_command,
            input_text=input_text,
            timeout=SSH_REBOOT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, True, "SSH-Verbindung wurde während des Neustarts beendet."
    except OSError as exc:
        return False, False, str(exc)
    if completed.returncode == 0:
        return True, False, ""
    if completed.returncode == 255:
        return False, True, _process_error(completed, "SSH-Verbindung wurde während des Neustarts beendet.")
    return False, False, _process_error(completed, "sudo reboot ist fehlgeschlagen.")


def monitor_server_restart(
    session: Session,
    user: str,
    sudo_password: str,
    service: str,
    timeout_seconds: int,
    cancel_event: threading.Event,
    report,
    *,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    monotonic=time.monotonic,
) -> RestartResult:
    """Restart one server and wait until SSH and the optional unit are ready."""
    report("preflight", "SSH und Neustartstatus werden geprüft")
    connected, original_boot_id, error = _read_boot_id(session, user)
    if not connected:
        return RestartResult("error", error)

    if service:
        service_connected, load_state, service_error = _service_load_state(session, user, service)
        if not service_connected:
            return RestartResult("error", service_error)
        if load_state == "not-found" or service_error:
            return RestartResult("error", service_error)

    if cancel_event.is_set():
        return RestartResult("stopped", "Neustart wurde noch nicht ausgelöst")

    report("restarting", "sudo reboot wird ausgeführt")
    deadline = monotonic() + timeout_seconds
    accepted, uncertain, reboot_error = _issue_reboot(session, user, sudo_password)
    if not accepted and not uncertain:
        return RestartResult("error", reboot_error)

    saw_ssh_down = False
    online_streak = 0
    reboot_confirmed = False
    last_service_state = ""
    last_connected = True

    while monotonic() < deadline:
        if cancel_event.is_set():
            return RestartResult("stopped", "Überwachung durch Benutzer beendet")

        connected, current_boot_id, _probe_error = _read_boot_id(session, user)
        last_connected = connected
        if not connected:
            saw_ssh_down = True
            online_streak = 0
            report("waiting_ssh", "SSH ist noch nicht wieder erreichbar")
        else:
            if original_boot_id and current_boot_id:
                reboot_confirmed = current_boot_id != original_boot_id
            elif saw_ssh_down:
                reboot_confirmed = True

            if not reboot_confirmed:
                online_streak = 0
                detail = "SSH antwortet noch mit der bisherigen Boot-ID" if original_boot_id else "Warte auf den SSH-Ausfall"
                report("waiting_down", detail)
            else:
                online_streak += 1
                if online_streak < 2:
                    report("waiting_ssh", "SSH antwortet; Stabilität wird bestätigt")
                elif service:
                    service_connected, active, state = _service_active(session, user, service)
                    if not service_connected:
                        online_streak = 0
                        report("waiting_ssh", "SSH ist während der Service-Prüfung nicht erreichbar")
                    elif active:
                        return RestartResult("online", f"SSH und {service} sind verfügbar")
                    else:
                        last_service_state = state
                        report("waiting_service", f"{service}: {state}")
                else:
                    return RestartResult("online", "Neustart bestätigt; SSH ist wieder erreichbar")

        if cancel_event.wait(max(0.0, poll_interval_seconds)):
            return RestartResult("stopped", "Überwachung durch Benutzer beendet")

    if service and reboot_confirmed and last_connected:
        detail = f"{service} wurde nicht aktiv"
        if last_service_state:
            detail += f" (letzter Zustand: {last_service_state})"
    elif saw_ssh_down and not last_connected:
        detail = "SSH wurde innerhalb der Wartezeit nicht wieder erreichbar"
    else:
        detail = "Der Server-Neustart konnte innerhalb der Wartezeit nicht bestätigt werden"
    return RestartResult("timeout", detail)


def _deduplicate_sessions(sessions: list[Session]) -> list[Session]:
    result: list[Session] = []
    seen: set[str] = set()
    for session in sessions:
        if session.hostname and session.key not in seen:
            seen.add(session.key)
            result.append(session)
    return result


def restart_servers(app, sessions: list[Session]) -> None:
    """Run and monitor ``sudo reboot`` on all selected sessions in parallel."""
    runnable = _deduplicate_sessions(sessions)
    if not runnable:
        messagebox.showwarning("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=app)
        return

    session_users = resolve_users_for_sessions(app, runnable, "all")
    if session_users is None:
        return

    dialog = ServerRestartDialog(app, session_users)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    spec = dict(dialog.result)
    sudo_password = str(spec.pop("sudo_password", ""))
    service = str(spec.get("service", ""))
    timeout_seconds = int(spec.get("timeout_seconds", 300))

    progress = ServerRestartProgressDialog(app, session_users, service)
    events: queue.Queue[tuple[str, str, str, str]] = queue.Queue()

    def run_one(session: Session, user: str) -> None:
        def report(state: str, detail: str) -> None:
            events.put(("status", session.key, state, detail))

        result = monitor_server_restart(
            session,
            user,
            sudo_password,
            service,
            timeout_seconds,
            progress.cancel_event,
            report,
        )
        events.put(("done", session.key, result.status, result.detail))

    for session, user in session_users:
        threading.Thread(target=run_one, args=(session, user), daemon=True).start()

    completed: set[str] = set()

    def pump_events() -> None:
        try:
            while True:
                kind, session_key, state, detail = events.get_nowait()
                progress.update_host(session_key, state, detail)
                if kind == "done":
                    completed.add(session_key)
        except queue.Empty:
            pass
        if len(completed) == len(session_users):
            progress.finish()
        else:
            app.after(100, pump_events)

    app.after(50, pump_events)
    app.wait_window(progress)
