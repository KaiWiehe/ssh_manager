"""Run the native app's bounded IPC waits outside Tk, deliver results on Tk."""
from __future__ import annotations

from dataclasses import replace

from .core import TerminalLauncher
from .herdr_app import HerdrAppUnavailableError, HerdrAppBusyError
from .window_policy import messagebox, owner_alive
from .workers import run_worker


def run_terminal_ui(app, work, settings, success, error, *, resources=(), cleanup=None):
    # Snapshot before yielding to the event loop. Different target selections may
    # proceed; overlapping targets cannot accidentally get a second launch.
    pending = app.__dict__.setdefault("_pending_terminal_targets", set())
    keys = set(resources)
    if keys & pending:
        if cleanup:
            cleanup()
        error(HerdrAppBusyError("Für diese Verbindung läuft bereits ein Terminalstart."))
        return
    if settings.ssh_open_mode != "herdr_app":
        work(settings)
        success(None)
        return
    pending.update(keys)
    snapshot = replace(settings)

    def done(value):
        pending.difference_update(keys)
        success(value)

    def failed(exc):
        try:
            if isinstance(exc, HerdrAppUnavailableError):
                if messagebox.askyesno("Herdr App nicht verfügbar", str(exc) + "\n\nStattdessen in Windows Terminal öffnen?", parent=app):
                    if not owner_alive(app):
                        if cleanup:
                            cleanup()
                        return
                    try:
                        work(replace(snapshot, ssh_open_mode="windows_terminal"))
                        success(None)
                    except (OSError, RuntimeError, ValueError) as fallback_error:
                        error(fallback_error)
                else:
                    if cleanup:
                        cleanup()
                    error(exc)
                return
            if isinstance(exc, HerdrAppBusyError) and cleanup:
                cleanup()
            error(exc)
        finally:
            pending.difference_update(keys)

    run_worker(app, lambda: work(snapshot), done, failed)


def launch_built_command_ui(app, command, labels, settings, job=None):
    if settings.ssh_open_mode != "herdr_app" and not app.__dict__.get("_pending_terminal_targets"):
        TerminalLauncher.launch_built_command(command, labels, settings)
        if job:
            job.launched()
        return

    def success(_value):
        if job:
            job.launched()

    def failed(exc):
        if job:
            if isinstance(exc, (HerdrAppBusyError, HerdrAppUnavailableError)):
                job.not_started()
            else:
                job.uncertain_launch()
        messagebox.showerror("Terminalstart fehlgeschlagen", str(exc), parent=app)

    run_terminal_ui(
        app, lambda snapshot: TerminalLauncher.launch_built_command(command, labels, snapshot),
        settings, success, failed,
        resources=[tab.session.key for tab in command.tabs if tab.session is not None], cleanup=command.cleanup,
    )
