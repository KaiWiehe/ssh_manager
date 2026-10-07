"""Record local source reads without mixing missing, empty and failed sources."""
from __future__ import annotations

from datetime import datetime
from functools import wraps
from pathlib import Path
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox

from .ui_components import fit_window_to_parent

SOURCE_LABELS = {"winscp": "WinSCP", "ssh_config": "SSH Config", "filezilla_config": "FileZilla", "app": "Eigene App-Verbindungen"}
SOURCE_ATTRIBUTES = {"winscp": "_winscp_sessions", "ssh_config": "_ssh_config_sessions", "filezilla_config": "_filezilla_sessions", "app": "_app_sessions"}
STATUS_LABELS = {"loaded": "geladen", "empty": "leer", "missing": "Quelle fehlt", "error": "Lesefehler", "partial": "teilweise geladen"}
STATUSES = {}


def source_path(source):
    from . import storage
    if source == "ssh_config":
        return storage._SSH_CONFIG_FILE
    if source == "app":
        return storage._APP_SESSIONS_FILE
    if source == "filezilla_config":
        base = Path(os.environ.get("APPDATA", Path.home()))
        candidates = [base / "FileZilla" / "sitemanager.xml", base / "filezilla" / "sitemanager.xml"]
        return next((path for path in candidates if path.exists()), candidates[0])
    return None


def source_load(source):
    def decorate(loader):
        @wraps(loader)
        def load(*args, **kwargs):
            from . import storage
            started = time.monotonic()
            path = source_path(source)
            if path:
                storage._load_warnings.pop(path, None)
            error, warnings, count = None, [], 0
            try:
                sessions = loader(*args, **kwargs)
                count = len(sessions)
                if path and path in storage._load_warnings:
                    warnings = [storage._load_warnings[path]]
                elif source == "winscp" and args:
                    warnings = getattr(args[0], "warnings", [])
                state = "partial" if warnings and count else "error" if warnings else "missing" if path and not path.exists() else "loaded" if count else "empty"
                return sessions
            except FileNotFoundError:
                state, error = "missing", "Datenquelle nicht vorhanden."
                raise
            except (OSError, ValueError):
                state, error = "error", "Datenquelle konnte nicht gelesen werden."
                raise
            finally:
                STATUSES[source] = {"state": locals().get("state", "error"), "count": count, "time": datetime.now().strftime("%H:%M:%S"), "duration_ms": round((time.monotonic() - started) * 1000), "detail": error or "\n".join(warnings) or str(path or "HKCU – WinSCP Sessions")}
        return load
    return decorate


def reload_source(app, source):
    from . import storage
    from .actions_ui import build_visible_sessions, _migrate_filezilla_in_app
    loaders = {"ssh_config": storage.load_ssh_config_sessions, "filezilla_config": storage.load_filezilla_config_sessions, "app": storage.load_app_sessions}
    try:
        sessions = app._registry_reader().load_sessions() if source == "winscp" else loaders[source]()
    except FileNotFoundError:
        sessions = []
    except (OSError, ValueError):
        return False
    if STATUSES.get(source, {}).get("state") == "error":
        return False  # Preserve last usable tree data after a failed read.
    setattr(app, SOURCE_ATTRIBUTES[source], sessions)
    if source == "filezilla_config":
        _migrate_filezilla_in_app(app)
    app._sessions = build_visible_sessions(app)
    app._tree.refresh(app._sessions)
    return True


class SourceStatusDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Quellenstatus")
        self.app = parent
        self.transient(parent)
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Externe Quellen werden live gelesen. Eigene Verbindungen sind App-Daten. Eine Übernahme erzeugt eine Kopie; das Original bleibt unverändert.", wraplength=720).pack(anchor="w")
        self.table = ttk.Treeview(frame, columns=("source", "state", "count", "time", "duration"), show="headings", height=4)
        for column, label, width in (("source", "Quelle", 180), ("state", "Status", 160), ("count", "Geladen", 75), ("time", "Letzter Leseversuch", 140), ("duration", "Dauer (ms)", 90)):
            self.table.heading(column, text=label)
            self.table.column(column, width=width)
        self.table.pack(fill="both", expand=True, pady=12)
        self.details = tk.StringVar(value="Quelle auswählen, um Pfad und Hinweise anzuzeigen.")
        ttk.Label(frame, textvariable=self.details, wraplength=720).pack(anchor="w", pady=8)
        self.table.bind("<<TreeviewSelect>>", lambda _: self.show_detail())
        ttk.Button(frame, text="Nur gewählte Quelle neu laden", command=self.reload).pack(anchor="e")
        self.refresh()
        fit_window_to_parent(self, parent, 820, 360)

    def refresh(self):
        selected = self.table.selection()
        self.table.delete(*self.table.get_children())
        for source, label in SOURCE_LABELS.items():
            status = STATUSES.get(source)
            values = (label, STATUS_LABELS[status["state"]], status["count"], status["time"], status["duration_ms"]) if status else (label, "noch nicht geprüft", len(getattr(self.app, SOURCE_ATTRIBUTES[source], [])), "—", "—")
            self.table.insert("", "end", iid=source, values=values)
        if selected:
            self.table.selection_set(selected)
            self.show_detail()

    def show_detail(self):
        selected = self.table.selection()
        if selected:
            self.details.set(STATUSES.get(selected[0], {}).get("detail", "Noch keine Ladeinformationen."))

    def reload(self):
        selected = self.table.selection()
        if not selected:
            self.details.set("Zuerst eine Quelle auswählen.")
            return
        ok = reload_source(self.app, selected[0])
        self.refresh()
        if not ok:
            self.details.set(self.details.get() + "\nDer bisherige nutzbare Stand bleibt angezeigt.")
