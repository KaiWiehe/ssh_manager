"""Restart-template execution; all Tk interactions stay in the event pump."""
from __future__ import annotations

import queue
import shlex
import subprocess
import time
from tkinter import ttk

from .actions_restart import RestartResult, _run_ssh, monitor_server_restart
from .dialogs_restart import ServerRestartProgressDialog
from .restart_templates import RestartScheduler, validate_template


def probe_unit(session, user, unit, timeout=8):
    command = f"systemctl show --property=LoadState --property=ActiveState -- {shlex.quote(unit)}"
    try:
        completed = _run_ssh(session, user, command, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return "connection", "SSH-Abfrage nicht erreichbar oder Zeitüberschreitung"
    if completed.returncode == 255:
        return "connection", "SSH nicht erreichbar"
    props = dict(line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line)
    if props.get("LoadState") == "not-found":
        return "error", "Dienst nicht vorhanden"
    if completed.returncode or props.get("LoadState") not in ("loaded", "masked", "merged") or not props.get("ActiveState"):
        return "error", "Dienst konnte nicht zuverlässig geprüft werden"
    return "state", props["ActiveState"]


def monitor_template_restart(session, user, password, checks, reboot_timeout, service_timeout,
                             cancel, report, *, monotonic=time.monotonic, poll_interval=2):
    report("preflight", "Vorprüfung aller hinterlegten Service-Units")
    for check in checks:
        if cancel.is_set():
            return RestartResult("not_started", "Neustart wurde nicht ausgelöst")
        kind, state = probe_unit(session, user, check["unit"])
        if kind != "state":
            return RestartResult("error", f"Vorprüfung {check['unit']}: {state}; kein Neustart ausgelöst")
    result = monitor_server_restart(session, user, password, "", reboot_timeout, cancel, report,
                                    evidence_detail=True, poll_interval_seconds=poll_interval)
    if result.status != "online" or not checks:
        return result
    evidence = result.detail
    deadline = monotonic() + service_timeout
    latest = {c["unit"]: "noch nicht geprüft" for c in checks}
    def details():
        return "\n".join(f"{c['unit']}: Soll {c['expected']}, Ist {latest[c['unit']]}" for c in checks)
    while monotonic() < deadline:
        if cancel.is_set():
            return RestartResult("stopped", evidence + "\nServiceüberwachung beendet\n" + details())
        all_match = True
        for check in checks:
            remaining = deadline - monotonic()
            if remaining <= 0 or cancel.is_set():
                all_match = False
                break
            kind, state = probe_unit(session, user, check["unit"], timeout=max(.1, min(8, remaining)))
            latest[check["unit"]] = state
            if kind == "error":
                return RestartResult("error", evidence + "\n" + details())
            all_match &= kind == "state" and state == check["expected"]
        if all_match and monotonic() <= deadline:
            return RestartResult("online", evidence + "\nAlle Service-Sollzustände erfüllt\n" + details())
        report("waiting_service", evidence + "\n" + details())
        cancel.wait(max(0, min(poll_interval, deadline - monotonic())))
    return RestartResult("timeout", evidence + "\nService-Wartezeit abgelaufen\n" + details())


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
    scheduler = RestartScheduler(targets, 1 if template["mode"] == "serial" else template["max_parallel"], template["on_error"], work)
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
