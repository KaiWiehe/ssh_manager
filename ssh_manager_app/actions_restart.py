from __future__ import annotations

from .window_policy import single_pending

import queue
import threading
from .window_policy import messagebox

from .actions_remote import resolve_users_for_sessions
from .dialogs_restart import ServerRestartDialog, ServerRestartProgressDialog
from .models import Session
from .restart_runtime import monitor_server_restart


def _deduplicate_sessions(sessions: list[Session]) -> list[Session]:
    result: list[Session] = []
    seen: set[str] = set()
    for session in sessions:
        if session.hostname and session.key not in seen:
            seen.add(session.key)
            result.append(session)
    return result


@single_pending
def restart_servers(app, sessions: list[Session]) -> ServerRestartProgressDialog | None:
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
    dialog.result = None
    sudo_password = str(spec.pop("sudo_password", ""))
    service = str(spec.get("service", ""))
    timeout_seconds = int(spec.get("timeout_seconds", 300))
    max_parallel = int(spec.get("max_parallel", 0))

    progress = ServerRestartProgressDialog(app, session_users, service)
    events: queue.Queue[tuple[str, str, str, str]] = queue.Queue()

    def run_one(session: Session, user: str) -> None:
        def report(state: str, detail: str) -> None:
            events.put(("status", session.key, state, detail))

        try:
            if progress.cancel_event.is_set():
                events.put(("done", session.key, "stopped", "Neustart wurde noch nicht ausgelöst"))
                return
            result = monitor_server_restart(
                session, user, sudo_password, service, timeout_seconds,
                progress.cancel_event, report,
            )
            events.put(("done", session.key, result.status, result.detail))
        except Exception:
            events.put(("done", session.key, "error", "Neustart-Prüfung unerwartet fehlgeschlagen. Zustand bitte manuell prüfen; kein automatischer Neustartversuch."))

    pending = queue.Queue()
    for entry in session_users:
        pending.put(entry)

    def run_pending() -> None:
        while True:
            try:
                session, user = pending.get_nowait()
            except queue.Empty:
                return
            run_one(session, user)

    worker_count = min(max_parallel, len(session_users)) if max_parallel > 0 else len(session_users)
    started = 0
    for _ in range(worker_count):
        try:
            threading.Thread(target=run_pending, daemon=True).start()
            started += 1
        except (RuntimeError, OSError):
            continue
    if not started:
        for session, _user in session_users:
            events.put(("done", session.key, "error", "Hintergrundaufgabe konnte nicht gestartet werden."))

    completed: set[str] = set()

    def pump_events() -> None:
        nonlocal sudo_password
        if not progress.winfo_exists():
            return
        try:
            while True:
                kind, session_key, state, detail = events.get_nowait()
                progress.update_host(session_key, state, detail)
                if kind == "done":
                    completed.add(session_key)
        except queue.Empty:
            pass
        if len(completed) == len(session_users):
            sudo_password = ""
            progress.finish()
        else:
            app.after(100, pump_events)

    app.after(50, pump_events)
    return progress
