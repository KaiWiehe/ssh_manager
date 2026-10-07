"""Read-only connection checks; a reachable port is never a login result."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import shutil
import socket
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

from .ssh_utils import ssh_argv, read_port
from .ui_components import install_context_help, fit_window_to_parent
from .workers import run_worker


def diagnose_session(session, user="", *, authenticate=False):
    results = []
    ssh = shutil.which("ssh")
    results.append(("Lokaler SSH-Client", "bereit" if ssh else "fehlt", ssh or "SSH im PATH installieren; DNS/TCP bleiben unabhängig prüfbar."))
    host, port, proxy = session.hostname, session.port, False
    if session.is_ssh_config_session:
        if not ssh:
            return results + [("SSH-Konfiguration", "nicht geprüft", "Aliasauflösung benötigt den lokalen SSH-Client.")]
        try:
            args = ssh_argv(session, user, ["-G"])
            args[0] = ssh
            config = subprocess.run(args, capture_output=True, text=True, timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if config.returncode:
                return results + [("SSH-Konfiguration", "fehlgeschlagen", "Alias konnte nicht ausgewertet werden.")]
            fields = dict(line.split(None, 1) for line in config.stdout.splitlines() if len(line.split(None, 1)) == 2)
            host, port = fields.get("hostname", host), read_port(fields.get("port", port))
            proxy = any(fields.get(field, "none") not in ("none", "") for field in ("proxyjump", "proxycommand"))
            results.append(("SSH-Konfiguration", "bereit", f"{host}:{port}" + (" – Proxy konfiguriert" if proxy else "")))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return results + [("SSH-Konfiguration", "fehlgeschlagen", "Aliasauflösung fehlgeschlagen oder Zeitlimit überschritten.")]
    try:
        addresses = socket.getaddrinfo(host, read_port(port), type=socket.SOCK_STREAM)
        results.append(("Namensauflösung", "erfolgreich", ", ".join(dict.fromkeys(item[4][0] for item in addresses))))
    except (OSError, ValueError):
        results.append(("Namensauflösung", "fehlgeschlagen", "Hostname konnte lokal nicht aufgelöst werden."))
        addresses = []
    if proxy:
        results.append(("TCP zum Ziel", "nicht geprüft", "Direkter TCP-Test würde den SSH-Proxy umgehen. Die optionale Anmeldung prüft den tatsächlichen Weg."))
    elif addresses:
        connected = False
        for family, kind, protocol, _, address in addresses[:8]:
            try:
                with socket.socket(family, kind, protocol) as probe:
                    probe.settimeout(3)
                    probe.connect(address)
                connected = True
                break
            except OSError:
                continue
        results.append(("TCP zum Ziel", "erfolgreich" if connected else "fehlgeschlagen", f"{host}:{port} – " + ("Port offen; Anmeldung noch nicht belegt." if connected else "Timeout, Ablehnung oder Netzwerkfehler.")))
    else:
        results.append(("TCP zum Ziel", "nicht geprüft", "Kein aufgelöstes Ziel."))
    if not authenticate or not ssh:
        results.append(("SSH-Anmeldung", "nicht geprüft", "Explizit aktivieren; keine Passwortabfrage, kein Ändern von Hostschlüsseln."))
        return results
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no", "-o", "ClearAllForwardings=yes", "-o", "ControlMaster=no", "-o", "ControlPath=none"]
    try:
        args = ssh_argv(session, user, options) + ["true"]
        args[0] = ssh
        login = subprocess.run(args, capture_output=True, timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        results.append(("SSH-Anmeldung", "erfolgreich" if login.returncode == 0 else "fehlgeschlagen", "Angemeldet, Prüfkommando true beendet." if login.returncode == 0 else "SSH abgelehnt/fehlgeschlagen; Schlüssel, Benutzer und bekannten Hostschlüssel im Terminal prüfen."))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        results.append(("SSH-Anmeldung", "fehlgeschlagen", "Clientfehler oder Zeitlimit überschritten."))
    return results


def diagnose_many(sessions, user, authenticate):
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda session: (session, diagnose_session(session, session.username or user, authenticate=authenticate)), sessions))


class ConnectionDiagnosisDialog(tk.Toplevel):
    def __init__(self, parent, sessions):
        super().__init__(parent)
        install_context_help(self, "diagnosis")
        self.title("Verbindung diagnostizieren")
        self.sessions = list(sessions)
        self.transient(parent)
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{len(sessions)} Ziel(e). DNS und TCP prüfen keine Anmeldung. Quellen werden nicht verändert.", wraplength=660).pack(anchor="w")
        self.authenticate = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Zusätzlich SSH-Anmeldung mit vorhandenem Schlüssel prüfen (true)", variable=self.authenticate).pack(anchor="w", pady=8)
        userrow = ttk.Frame(frame)
        userrow.pack(fill="x")
        ttk.Label(userrow, text="Fallback-Benutzer (feste Benutzer/Aliase haben Vorrang)").pack(side="left")
        self.user = tk.StringVar(value=parent.settings.default_user)
        ttk.Entry(userrow, textvariable=self.user, width=20).pack(side="left", padx=8)
        self.status = tk.StringVar(value="Bereit. SSH-Anmeldung ist standardmäßig ausgeschaltet.")
        ttk.Label(frame, textvariable=self.status, wraplength=660).pack(anchor="w", pady=8)
        self.output = ttk.Treeview(frame, columns=("step", "status", "detail"), show="tree headings")
        self.output.heading("#0", text="Host")
        for column, label, width in (("step", "Schritt", 145), ("status", "Ergebnis", 100), ("detail", "Bedeutung", 360)):
            self.output.heading(column, text=label)
            self.output.column(column, width=width)
        self.output.column("#0", width=170)
        bar = ttk.Scrollbar(frame, command=self.output.yview)
        self.output.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.start_button = ttk.Button(frame, text="Diagnose starten", command=self.start)
        self.start_button.pack(side="bottom", pady=8)
        self.output.pack(fill="both", expand=True)
        fit_window_to_parent(self, parent, 980, 520)

    def start(self):
        self.start_button.configure(state="disabled")
        self.output.delete(*self.output.get_children())
        self.status.set("Diagnose läuft … maximal acht parallele Ziele.")
        user, authenticate = self.user.get().strip(), self.authenticate.get()
        run_worker(self, lambda: diagnose_many(self.sessions, user, authenticate), self.show_results, self.failed)

    def show_results(self, results):
        for session, checks in results:
            item = self.output.insert("", "end", text=f"{session.display_name} ({session.hostname})", open=True)
            for step, status, detail in checks:
                self.output.insert(item, "end", values=(step, status, detail))
        self.status.set("Diagnose abgeschlossen. Erfolgreiche TCP-Prüfung bedeutet nur: Port erreichbar.")
        self.start_button.configure(state="normal")

    def failed(self, _error):
        self.status.set("Diagnose konnte nicht vollständig abgeschlossen werden.")
        self.start_button.configure(state="normal")


def open_diagnosis(app):
    from .selection import single_action_target
    sessions = app._tree.get_selected_sessions()
    if not sessions:
        target = single_action_target(app._tree)
        sessions = [target] if target else []
    if not sessions:
        messagebox.showwarning("Kein Ziel", "Eine Verbindung fokussieren oder Hosts anhaken.", parent=app)
        return
    ConnectionDiagnosisDialog(app, sessions)
