"""Read-only reference-host browser shared by script and service forms."""
from __future__ import annotations

import posixpath
import re
import subprocess
import tkinter as tk
from tkinter import ttk

from .ssh_utils import ssh_argv
from .workers import run_worker


def list_services(session, user):
    """Include installed and runtime service units, without changing their state."""
    command = "systemctl list-unit-files --type=service --no-legend --no-pager && systemctl list-units --all --type=service --plain --no-legend --no-pager"
    args = ssh_argv(session, user, ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no"])
    result = subprocess.run(args + [command], capture_output=True, text=True, timeout=20,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise ValueError("Dienste konnten nicht gelesen werden. SSH-Zugang und systemd auf dem Referenzhost prüfen.")
    units = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields and re.fullmatch(r"(?!-)[A-Za-z0-9_.:@-]{1,200}\.service", fields[0]):
            units.add(fields[0])
    return [("service", unit) for unit in sorted(units, key=str.casefold)]


class ReferenceBrowser(ttk.Frame):
    def __init__(self, parent, sessions, on_select, *, kind="script", user_getter=None, default_user="", initial_path="/", on_close=None):
        super().__init__(parent, padding=8)
        self.sessions = list(sessions)
        self.kind, self.on_select, self.user_getter = kind, on_select, user_getter
        self.generation, self.entries, self.visible_entries = 0, [], []
        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)
        title = ttk.Frame(self)
        title.grid(row=0, column=0, sticky="ew")
        ttk.Label(title, text="Referenzhost durchsuchen").pack(side="left")
        if on_close:
            ttk.Button(title, text="Schließen", command=on_close).pack(side="right")
        self.host = ttk.Combobox(self, state="readonly", values=[f"{i + 1}. {s.display_name} ({s.hostname})" for i, s in enumerate(self.sessions)])
        self.host.grid(row=1, column=0, sticky="ew", pady=6)
        if self.sessions:
            self.host.current(0)
        self.host.bind("<<ComboboxSelected>>", self.load)
        self.warning = tk.StringVar()
        ttk.Label(self, textvariable=self.warning, wraplength=420, justify="left").grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.user = tk.StringVar(value=default_user)
        if user_getter is None:
            userrow = ttk.Frame(self)
            userrow.grid(row=3, column=0, sticky="ew", pady=(0, 8))
            ttk.Label(userrow, text="SSH-Benutzer zum Durchsuchen:").pack(anchor="w")
            ttk.Entry(userrow, textvariable=self.user).pack(fill="x")
            ttk.Label(userrow, text="Feste Benutzer und SSH-Aliase haben Vorrang.").pack(anchor="w")
        self.path = tk.StringVar(value=initial_path or "/")
        navigation = ttk.Frame(self)
        navigation.grid(row=4, column=0, sticky="ew")
        navigation.columnconfigure(1, weight=1)
        if kind == "script":
            ttk.Button(navigation, text="↑", width=3, command=self.up).grid(row=0, column=0)
            entry = ttk.Entry(navigation, textvariable=self.path)
            entry.grid(row=0, column=1, sticky="ew", padx=4)
            entry.bind("<Return>", self.load)
        self.load_button = ttk.Button(navigation, text="Laden", command=self.load)
        self.load_button.grid(row=0, column=2)
        self.search = tk.StringVar()
        searchrow = ttk.Frame(self)
        searchrow.grid(row=5, column=0, sticky="ew", pady=8)
        ttk.Label(searchrow, text="Suche:").pack(side="left")
        ttk.Entry(searchrow, textvariable=self.search).pack(side="left", fill="x", expand=True, padx=4)
        self.search.trace_add("write", lambda *_: self.filter())
        listrow = ttk.Frame(self)
        listrow.grid(row=6, column=0, sticky="nsew")
        self.listbox = tk.Listbox(listrow, exportselection=False, height=8)
        self.listbox.pack(side="left", fill="both", expand=True)
        bar = ttk.Scrollbar(listrow, command=self.listbox.yview)
        bar.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=bar.set)
        self.listbox.bind("<Double-Button-1>", self.select)
        self.listbox.bind("<Return>", self.select)
        self.status = tk.StringVar(value="Noch keine Abfrage. Laden startet eine lesende SSH-Abfrage.")
        ttk.Label(self, textvariable=self.status, wraplength=420).grid(row=7, column=0, sticky="ew", pady=8)
        ttk.Button(self, text="Skript verwenden" if kind == "script" else "Dienst verwenden", command=self.select).grid(row=8, column=0, sticky="e")
        self._warning()

    def _warning(self):
        index = self.host.current()
        name = self.sessions[index].display_name if index >= 0 else "kein Host ausgewählt"
        subject = "Der gewählte Skriptpfad muss auf allen Zielhosts vorhanden sein und dasselbe Skript bezeichnen." if self.kind == "script" else "Der gewählte Dienst muss auf allen Zielhosts verfügbar sein. Fehlende Dienste werden je Host als „Dienst wurde nicht gefunden“ gemeldet."
        self.warning.set(f"Ich benutze ausschließlich {name} als Referenzhost für die Auswahl. {subject}")

    def load(self, _event=None):
        self.generation += 1
        generation = self.generation
        self.entries = []
        self.filter()
        self._warning()
        index = self.host.current()
        if index < 0:
            self.status.set("Zum Durchsuchen zunächst einen Zielhost auswählen.")
            return
        session = self.sessions[index]
        fallback = self.user_getter() if self.user_getter else self.user.get()
        user = session.username or fallback.strip()
        if not user and not session.is_ssh_config_session:
            self.status.set("SSH-Benutzer für den Referenzhost eingeben und erneut laden.")
            return
        path = self.path.get().strip() or "/"
        if self.kind == "script" and not path.startswith("/"):
            self.status.set("Zum Durchsuchen einen absoluten Serverpfad angeben, z. B. /opt.")
            return
        self.status.set(f"Lesende Abfrage auf {session.display_name} läuft …")

        def work():
            if self.kind == "service":
                return list_services(session, user)
            from .dialogs_certificates import _ssh_folder_list_command, _sort_remote_entries
            entries, error = _ssh_folder_list_command(session, user, path, "")
            if error:
                raise ValueError("Ordnerabfrage fehlgeschlagen")
            return _sort_remote_entries(entries)

        def success(entries):
            if generation != self.generation:
                return
            self.entries = entries
            self.path.set(path)
            self.filter()
            self.status.set(f"{len(entries)} Einträge auf {session.display_name}. Nur dieser Host wurde durchsucht.")

        def failed(_error):
            if generation == self.generation:
                self.status.set("Abfrage fehlgeschlagen. SSH-Zugang, Pfad, Rechte bzw. systemd auf dem Referenzhost prüfen.")

        run_worker(self, work, success, failed)

    def filter(self):
        term = self.search.get().casefold()
        self.visible_entries = [item for item in self.entries if term in item[1].casefold()]
        self.listbox.delete(0, "end")
        for kind, path in self.visible_entries:
            label = posixpath.basename(path) if self.kind == "script" else path
            self.listbox.insert("end", ("[Ordner] " if kind == "d" else "") + label)

    def up(self):
        self.path.set(posixpath.dirname(self.path.get().rstrip("/")) or "/")
        self.load()

    def select(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        kind, path = self.visible_entries[selection[0]]
        if kind == "d":
            self.path.set(path)
            self.search.set("")
            self.load()
        elif kind in ("f", "l", "service"):
            self.on_select(path)
            self.status.set(f"Übernommen: {path}")
