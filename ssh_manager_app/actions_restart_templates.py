"""Restart-template execution; all Tk interactions stay in the event pump."""
from __future__ import annotations

import queue
from tkinter import ttk

from .dialogs_restart import ServerRestartProgressDialog
from .errors import record_failure
from .restart_runtime import RestartResult, RestartScheduler, execution_policy, monitor_template_restart
from .restart_templates import validate_template


def run_template(app, template, targets, password):
    template = validate_template(template, runnable=True)
    from .restart_passwords import passwords_for_run
    passwords = passwords_for_run(template, targets, password)
    password = ""
    progress = ServerRestartProgressDialog(app, [(s, u) for s, u, _ in targets], "")
    progress.title("Massen-Neustart · " + template["name"])
    reports = queue.Queue()
    cancel = progress.cancel_event
    def work(target):
        session, user, checks = target
        if cancel.is_set():
            return RestartResult("not_started", "Neustart wurde nicht ausgelöst")
        return monitor_template_restart(session, user, passwords.get(session.key, ""), checks, template["reboot_timeout"],
            template["service_timeout"], cancel,
            lambda state, detail: reports.put((session.key, state, detail)))
    limit, error_policy = execution_policy(template)
    scheduler = RestartScheduler(targets, limit, error_policy, work, record_error=record_failure)
    gate = ttk.Frame(progress, padding=(14, 4))
    gate.grid(row=3, column=0, sticky="ew")
    message = ttk.Label(gate, text="", wraplength=650, style="Warning.TLabel")
    message.pack(anchor="w")
    buttons = ttk.Frame(gate)
    buttons.pack(anchor="e", pady=4)
    def decide(keep_going):
        scheduler.decide(keep_going)
        gate.grid_remove()
    ttk.Button(buttons, text="Fortsetzen", command=lambda: decide(True)).pack(side="left", padx=4)
    ttk.Button(buttons, text="Wartende Neustarts stoppen", command=lambda: decide(False)).pack(side="left")
    gate.grid_remove()
    completed = set()
    def pump():
        if not progress.winfo_exists():
            cancel.set()
            scheduler.decide(False)
            passwords.clear()
            return
        if cancel.is_set():
            scheduler.decide(False)
        while True:
            try:
                key, state, detail = reports.get_nowait()
            except queue.Empty:
                break
            if key not in completed:
                progress.update_host(key, state, detail)
        scheduler.tick()
        while True:
            try:
                target, result = scheduler.events.get_nowait()
            except queue.Empty:
                break
            completed.add(target[0].key)
            progress.update_host(target[0].key, result.status, result.detail)
        with scheduler.lock:
            paused = scheduler.paused and bool(scheduler.pending) and not scheduler.stopped
            failures = list(scheduler.failures)
        if paused:
            message.configure(text=f"Pausiert nach {len(failures)} Fehler(n): " + ", ".join(t[0].display_name for t, _ in failures) +
                              ". Weitere Neustarts fortsetzen? Laufende Server werden weiter überwacht.")
            gate.grid()
        else:
            gate.grid_remove()
        if scheduler.done and len(completed) == len(targets):
            passwords.clear()
            progress.finish()
            return
        progress.after(80, pump)
    pump()
    return progress


def open_restart_templates(app, sessions=None):
    from .dialogs_restart_templates import RestartTemplatesDialog
    window = RestartTemplatesDialog(app, sessions or [])
    return window


def open_service_status_templates(app, sessions=None):
    from .dialogs_restart_templates import RestartTemplatesDialog
    return RestartTemplatesDialog(app, sessions or [], status_only=True)
