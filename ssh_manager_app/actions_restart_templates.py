"""Restart-template execution; all Tk interactions stay in the event pump."""
from __future__ import annotations

import queue
from tkinter import ttk

from .dialogs_restart import ServerRestartProgressDialog
from .errors import record_failure
from .mass_restart import MassRestartRun
from .restart_templates import validate_template
from .window_policy import owner_alive


def run_template(app, template, targets, password):
    template = validate_template(template, runnable=True)
    from .restart_passwords import passwords_for_run
    secrets = passwords_for_run(template, targets, password)
    passwords = [secrets[session.key] for session, _user, _checks in targets]
    secrets.clear()
    password = ""
    progress = ServerRestartProgressDialog(app, [(s, u) for s, u, _ in targets], "")
    progress.title("Massen-Neustart · " + template["name"])
    cancel = progress.cancel_event
    try:
        run = MassRestartRun(template, targets, passwords, cancel, record_error=record_failure)
    except ValueError:
        passwords.clear()
        progress.destroy()
        raise

    def stop_on_destroy(event):
        if event.widget is progress:
            cancel.set()

    progress.bind("<Destroy>", stop_on_destroy, add="+")
    gate = ttk.Frame(progress, padding=(14, 4))
    gate.grid(row=3, column=0, sticky="ew")
    message = ttk.Label(gate, text="", wraplength=650, style="Warning.TLabel")
    message.pack(anchor="w")
    buttons = ttk.Frame(gate)
    buttons.pack(anchor="e", pady=4)
    def decide(keep_going):
        run.decide(keep_going)
        gate.grid_remove()
    ttk.Button(buttons, text="Fortsetzen", command=lambda: decide(True)).pack(side="left", padx=4)
    ttk.Button(buttons, text="Wartende Neustarts stoppen", command=lambda: decide(False)).pack(side="left")
    gate.grid_remove()
    def pump():
        visible = owner_alive(progress)
        if not visible:
            cancel.set()
        run.tick()
        while True:
            try:
                _timestamp, index, state, detail = run.events.get_nowait()
            except queue.Empty:
                break
            if visible:
                progress.update_host(targets[index][0].key, state, detail)
        if visible:
            failures = run.pause_failures()
            if failures:
                names = ", ".join(targets[index][0].display_name for index, _result in failures)
                message.configure(text=f"Pausiert nach {len(failures)} Fehler(n): {names}. "
                                       "Weitere Neustarts fortsetzen? Laufende Server werden weiter überwacht.")
                gate.grid()
            else:
                gate.grid_remove()
        if run.done:
            if visible:
                progress.finish()
        elif owner_alive(app):
            app.after(80, pump)
    pump()
    return progress


def open_restart_templates(app, sessions=None):
    from .dialogs_restart_templates import RestartTemplatesDialog
    window = RestartTemplatesDialog(app, sessions or [])
    return window


def open_service_status_templates(app, sessions=None):
    from .dialogs_restart_templates import RestartTemplatesDialog
    return RestartTemplatesDialog(app, sessions or [], status_only=True)
