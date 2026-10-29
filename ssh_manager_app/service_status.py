"""One-shot, read-only status checks using the shared restart-template targets."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import queue
import threading
import tkinter as tk
from tkinter import ttk

from .actions_restart_templates import probe_unit
from .result_table import ResultTableTools
from .ui_components import fit_window_to_parent


@dataclass(frozen=True)
class ServiceStatus:
    actual: str
    outcome: str
    detail: str = ""


def check_unit(session, user, check):
    kind, state = probe_unit(session, user, check["unit"])
    if kind != "state":
        actual = "nicht vorhanden" if state == "Dienst nicht vorhanden" else "nicht geprüft"
        return ServiceStatus(actual, "Fehler", state)
    matches = state == check["expected"]
    return ServiceStatus(state, "Soll erfüllt" if matches else "Abweichung")


class ServiceStatusDialog(tk.Toplevel):
    def __init__(self, app, name, targets, max_parallel=0):
        super().__init__(app)
        self.title("Massendienststatus · " + name)
        self.cancel = threading.Event()
        self.finished = False
        self.full_rows, self.outcomes = {}, {}
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        header = ttk.Frame(self, padding=14)
        header.grid(row=0, column=0, sticky="ew")
        self.summary = tk.StringVar(value="Dienststatus wird geprüft …")
        summary_label = ttk.Label(header, textvariable=self.summary, style="DialogTitle.TLabel")
        summary_label.pack(anchor="w")
        parallel_text = f"maximal {max_parallel} Server gleichzeitig" if max_parallel else "alle Server parallel"
        hint = ttk.Label(header, text=f"Einmalige lesende Abfrage · {parallel_text} · Dienste werden nicht verändert",
                         style="Muted.TLabel")
        hint.pack(anchor="w", pady=5)
        def wrap_header(event):
            for label in (summary_label, hint):
                label.configure(wraplength=max(200, event.width - 28))
        header.bind("<Configure>", wrap_header)
        self.progress = ttk.Progressbar(header, mode="determinate")
        self.progress.pack(fill="x")
        body = ttk.Frame(self, padding=(14, 0, 14, 6))
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        columns = ("host", "user", "unit", "expected", "actual", "outcome", "detail")
        self.tree = ttk.Treeview(body, columns=columns, show="headings")
        for col, title, width in zip(columns, ("Server", "Benutzer", "Dienst", "Soll", "Ist", "Ergebnis", "Details"),
                                     (215, 100, 185, 80, 110, 140, 230)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=65)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.jobs = []
        for session, user, checks in targets:
            rows = []
            for check in checks or [None]:
                row = self.tree.insert("", "end", values=(f"{session.display_name} ({session.hostname}:{session.port})",
                    user, check["unit"] if check else "—", check["expected"] if check else "—", "—", "Noch nicht geprüft", ""))
                self.full_rows[row] = tuple(self.tree.item(row, "values"))
                rows.append((row, check))
            self.jobs.append((session, user, rows))
        self.progress.configure(maximum=max(1, len(self.full_rows)))
        tools = ttk.Frame(body)
        tools.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.table_tools = ResultTableTools(self, self.tree, tools,
            lambda: [row for row, result in self.outcomes.items() if result in ("Fehler", "Abweichung")],
            row_values=lambda row: self.full_rows[row])
        footer = ttk.Frame(self, padding=14)
        footer.grid(row=2, column=0, sticky="ew")
        self.stop = ttk.Button(footer, text="Prüfung abbrechen", command=self.stop_checks)
        self.stop.pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _: self.close())
        fit_window_to_parent(self, app, 1200, 680)

    def update_row(self, row, result):
        values = list(self.full_rows[row])
        values[4:] = [result.actual, result.outcome, result.detail]
        self.full_rows[row] = tuple(values)
        self.outcomes[row] = result.outcome
        self.tree.item(row, values=values)
        self.progress.configure(value=len(self.outcomes))
        self.summary.set(f"Dienststatus: {len(self.outcomes)} von {len(self.full_rows)} abgeschlossen")
        if row in self.tree.selection():
            self.table_tools.show_selection()

    def finish(self):
        self.finished = True
        results = list(self.outcomes.values())
        self.summary.set(f"Abgeschlossen: {results.count('Soll erfüllt')} Soll erfüllt · "
                         f"{results.count('Abweichung')} Abweichungen · {results.count('Fehler')} Fehler · "
                         f"{results.count('Nicht geprüft')} nicht geprüft")
        self.stop.configure(text="Schließen", state="normal", command=self.close)

    def stop_checks(self):
        self.cancel.set()
        self.stop.configure(state="disabled", text="Laufende Abfragen werden beendet …")

    def close(self):
        self.cancel.set()
        self.destroy()


def run_service_status(app, name, targets, *, max_parallel=0):
    """No reboot or credential path: only systemctl show through probe_unit."""
    from .parallelism import worker_count
    window = ServiceStatusDialog(app, name, targets, max_parallel)
    reports = queue.Queue()
    cancel = window.cancel
    jobs = ([(session, user, [row]) for session, user, rows in window.jobs for row in rows]
            if not max_parallel else list(window.jobs))
    workers = worker_count(len(jobs), max_parallel)
    def work(job):
        session, user, rows = job
        for row, check in rows:
            if cancel.is_set():
                result = ServiceStatus("nicht geprüft", "Nicht geprüft", "Prüfung abgebrochen")
            elif check is None:
                result = ServiceStatus("—", "Nicht geprüft", "Keine Dienste hinterlegt")
            else:
                try:
                    result = check_unit(session, user, check)
                except Exception as error:
                    from .errors import record_failure
                    record_failure(error)
                    result = ServiceStatus("nicht geprüft", "Fehler", "Dienststatus konnte nicht gelesen werden")
            reports.put((row, result))
    def coordinate():
        try:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="service-status") as executor:
                futures = [executor.submit(work, job) for job in jobs]
                for future in futures:
                    future.result()
        except Exception as error:
            from .errors import record_failure
            record_failure(error)
        finally:
            reports.put(None)
    def pump():
        if not window.winfo_exists():
            cancel.set()
            return
        while True:
            try:
                event = reports.get_nowait()
            except queue.Empty:
                break
            if event is None:
                for row in window.full_rows.keys() - window.outcomes.keys():
                    window.update_row(row, ServiceStatus("nicht geprüft", "Fehler", "Hintergrundprüfung konnte nicht ausgeführt werden"))
                window.finish()
                return
            window.update_row(*event)
        window.after(50, pump)
    try:
        threading.Thread(target=coordinate, daemon=True).start()
    except (RuntimeError, OSError):
        reports.put(None)
    pump()
    return window
