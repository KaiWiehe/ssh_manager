"""Per-host terminal receipts. No command, output or secret is persisted here."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import re
import shlex
import tempfile
import time
import tkinter as tk
from tkinter import ttk, messagebox
import uuid

from .ui_components import install_context_help, fit_window_to_parent

_paths = ContextVar("operation_result_paths", default={})
LABELS = {"prepared": "vorbereitet", "started": "Terminal gestartet", "running": "läuft", "success": "erfolgreich", "failed": "fehlgeschlagen", "unknown": "Status unbekannt"}


@contextmanager
def track_results(job):
    token = _paths.set(job.paths if job else {})
    try:
        yield
    finally:
        _paths.reset(token)


def result_statement(session, code=None):
    path = _paths.get().get(session.key)
    if path is None:
        return ":"
    target = shlex.quote(str(path).replace("\\", "/"))
    temporary = shlex.quote(str(path).replace("\\", "/") + ".tmp")
    status, value = ("running", "'-'") if code is None else ("exit", str(code))
    return f"{{ printf '%s\\t%s\\n' '{status}' {value} > {temporary} && mv -f -- {temporary} {target}; }} 2>/dev/null || true"


def result_lines(lines, session):
    if session.key not in _paths.get():
        return lines
    result = list(lines)
    # This is a list of local script statements. Embedded here-doc bodies are
    # single strings or delimited arrays; the last standalone capture is local.
    captures = [i for i, line in enumerate(result) if line == "status=$?"]
    if captures:
        result.insert(captures[-1] + 1, result_statement(session, "$status"))
    result.insert(1, result_statement(session))
    return result


class OperationJob:
    def __init__(self, sessions, title, retry=None, directory=None, exit_labels=None):
        self.sessions = list(dict((session.key, session) for session in sessions).values())
        self.title, self.retry = title, retry
        self.exit_labels = dict(exit_labels or {})
        folder = Path(directory or tempfile.gettempdir()) / "ssh-manager-results" / uuid.uuid4().hex
        folder.mkdir(parents=True)
        self.paths = {session.key: folder / f"{i}.status" for i, session in enumerate(self.sessions)}
        self.states = {session.key: ("prepared", "") for session in self.sessions}
        self.started_at = None

    def launched(self):
        self.started_at = time.monotonic()
        self.states = {key: ("started", "") for key in self.states}

    def uncertain_launch(self):
        # A launch error can occur after tabs have already started. Never claim
        # remote failure or offer automatic retries without an exit receipt.
        self.started_at = time.monotonic()
        self.states = {key: ("unknown", "Start nicht vollständig bestätigt") for key in self.states}

    def poll(self):
        for key, path in self.paths.items():
            try:
                if path.stat().st_size > 64:
                    continue
                receipt = path.read_text(encoding="ascii").strip()
            except (OSError, UnicodeError):
                if self.started_at and time.monotonic() - self.started_at > 90 and self.states[key][0] == "started":
                    self.states[key] = ("unknown", "Keine Rückmeldung des Terminalskripts")
                continue
            if receipt == "running\t-":
                if self.states[key][0] not in ("success", "failed"):
                    self.states[key] = ("running", "SSH-Aufgabe läuft; Abschluss noch nicht belegt")
            elif re.fullmatch(r"exit\t\d{1,3}", receipt):
                code = int(receipt.split("\t")[1])
                if code <= 255:
                    self.states[key] = ("success" if code == 0 else "failed", self.exit_labels.get(code, f"Exit-Code {code}"))
        return self.states

    def failed_sessions(self):
        self.poll()
        return [session for session in self.sessions if self.states[session.key][0] == "failed"]


class OperationResultsDialog(tk.Toplevel):
    def __init__(self, parent, job):
        super().__init__(parent)
        install_context_help(self, "results")
        self.job, self.timer = job, None
        self.title("Sammelergebnisse – " + job.title)
        self.transient(parent)
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Terminalstart ist kein Remote-Erfolg. Erfolg/Fehler wird nur aus einer Rückmeldung des ausgeführten Skripts abgeleitet. Ein fehlgeschlagener Ablauf kann bereits Teilschritte verändert haben.", wraplength=700).pack(anchor="w", pady=(0, 10))
        self.summary = tk.StringVar()
        ttk.Label(frame, textvariable=self.summary).pack(anchor="w")
        self.table = ttk.Treeview(frame, columns=("host", "state", "detail"), show="headings")
        for column, label, width in (("host", "Ziel", 250), ("state", "Status", 150), ("detail", "Nachweis", 300)):
            self.table.heading(column, text=label)
            self.table.column(column, width=width)
        self.table.pack(fill="both", expand=True, pady=10)
        for session in job.sessions:
            self.table.insert("", "end", iid=session.key, values=(session.display_name, LABELS["prepared"], ""))
        self.retry_button = ttk.Button(frame, text="Fehlgeschlagene Ziele erneut vorbereiten…", command=self.retry)
        self.retry_button.pack(anchor="e")
        self.bind("<Destroy>", self.on_destroy, add="+")
        fit_window_to_parent(self, parent, 820, 440)
        self.refresh()

    def refresh(self):
        counts = {}
        for key, (state, detail) in self.job.poll().items():
            counts[state] = counts.get(state, 0) + 1
            values = self.table.item(key, "values")
            self.table.item(key, values=(values[0], LABELS[state], detail))
        self.summary.set(" · ".join(f"{LABELS[state]}: {count}" for state, count in counts.items()))
        self.retry_button.configure(state="normal" if counts.get("failed") and self.job.retry else "disabled")
        self.retry_button.configure(text="Fehlgeschlagene Ziele erneut vorbereiten…" if counts.get("failed") and self.job.retry else "Keine bestätigten Fehler zum erneuten Starten")
        self.timer = self.after(500, self.refresh)

    def on_destroy(self, event):
        if event.widget is self and self.timer:
            self.after_cancel(self.timer)
            self.timer = None

    def retry(self):
        failed = self.job.failed_sessions()
        if failed and self.job.retry and messagebox.askyesno("Nur fehlgeschlagene Ziele", f"{len(failed)} bekannte fehlgeschlagene Ziele erneut vorbereiten?\n\nErfolgreiche und unbekannte Ziele bleiben ausgeschlossen. Parameter/Rechte erneut prüfen; Teilschritte können bereits ausgeführt sein. Danach folgt eine neue Ausführungsvorschau.", parent=self):
            self.job.retry(failed)


def create_job(app, sessions, title, retry=None, *, exit_labels=None):
    if not isinstance(app, tk.Misc):
        return None
    job = OperationJob(sessions, title, retry, exit_labels=exit_labels)
    if "_operation_jobs" not in app.__dict__:
        app._operation_jobs = []
    app._operation_jobs.append(job)
    app._operation_jobs = app._operation_jobs[-20:]
    OperationResultsDialog(app, job)
    return job


def show_last_results(app):
    jobs = app.__dict__.get("_operation_jobs", [])
    if jobs:
        OperationResultsDialog(app, jobs[-1])
    else:
        messagebox.showinfo("Sammelergebnisse", "In dieser App-Sitzung wurde noch keine unterstützte Sammelaktion gestartet.", parent=app)
