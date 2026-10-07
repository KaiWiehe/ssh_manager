from __future__ import annotations

import re
import shlex
import tkinter as tk
from tkinter import ttk, messagebox

from .ui_components import fit_window_to_parent
from .secret_scripts import clear_password_fields

ACTION_LABELS = {"status": "Dienststatus anzeigen", "restart": "Dienst neu starten", "logs": "Dienstlogs anzeigen"}


def service_command(action, unit, lines=100, sudo=False):
    if action not in ACTION_LABELS or not re.fullmatch(r"(?!-)[A-Za-z0-9_.:@-]{1,200}", unit):
        raise ValueError("Dienstname enthält ungültige Zeichen.")
    if not unit.endswith(".service"):
        unit += ".service"
    if not isinstance(lines, int) or not 1 <= lines <= 1000:
        raise ValueError("1 bis 1000 Logzeilen wählen.")
    quoted = shlex.quote(unit)
    prefix = "sudo " if sudo else ""
    if action == "restart":
        return f"{prefix}systemctl restart -- {quoted} && systemctl is-active -- {quoted}"
    if action == "logs":
        return f"{prefix}journalctl --no-pager -n {lines} --unit={quoted}"
    return f"{prefix}systemctl status --no-pager --lines=20 -- {quoted}\nstatus=$?\nif [ $status -eq 3 ]; then exit 0; fi\nexit $status"


class ServiceActionDialog(tk.Toplevel):
    def __init__(self, parent, action, target_count, initial=None):
        super().__init__(parent)
        self.action = action
        self.title(ACTION_LABELS[action])
        self.transient(parent)
        self.grab_set()
        self.result = None
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=f"{ACTION_LABELS[action]} für {target_count} angehakte Host(s).", wraplength=520).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        initial = initial or {}
        self.unit = tk.StringVar(value=initial.get("unit", "nginx.service"))
        ttk.Label(frame, text="Dienst").grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Combobox(frame, textvariable=self.unit, values=("nginx.service", "wildfly.service", "postgresql.service", "ssh.service")).grid(row=1, column=1, sticky="ew")
        self.lines = tk.StringVar(value=initial.get("lines", "100"))
        if action == "logs":
            ttk.Label(frame, text="Letzte Logzeilen").grid(row=2, column=0, sticky="w", pady=10)
            ttk.Spinbox(frame, from_=1, to=1000, textvariable=self.lines).grid(row=2, column=1, sticky="ew", pady=10)
        self.sudo = tk.BooleanVar(value=initial.get("sudo", action == "restart"))
        ttk.Checkbutton(frame, text="Mit sudo ausführen", variable=self.sudo).grid(row=3, column=0, columnspan=2, sticky="w", pady=8)
        self._sudo_password_var = tk.StringVar()
        ttk.Label(frame, text="sudo-Passwort (optional)").grid(row=4, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(frame, textvariable=self._sudo_password_var, show="•").grid(row=4, column=1, sticky="ew")
        ttk.Label(frame, text="Ohne Passwort wird die vorhandene sudo-Konfiguration verwendet. Der Dienstneustart startet ausschließlich diesen Dienst, keinen Server.", wraplength=520).grid(row=5, column=0, columnspan=2, sticky="w", pady=12)
        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(actions, text="Abbrechen", command=self.cancel).pack(side="left", padx=8)
        ttk.Button(actions, text="Weiter zur Vorschau", command=self.confirm).pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        fit_window_to_parent(self, parent, 620, 360)

    def confirm(self):
        try:
            command = service_command(self.action, self.unit.get().strip(), int(self.lines.get()), self.sudo.get())
        except ValueError as exc:
            messagebox.showwarning("Dienst prüfen", str(exc), parent=self)
            return
        self.result = (command, self._sudo_password_var.get() if self.sudo.get() else "")
        clear_password_fields(self)
        self.destroy()

    def cancel(self):
        self.result = None
        clear_password_fields(self)
        self.destroy()


def run_service_action(app, sessions, action, initial=None):
    from .actions_remote import resolve_users_for_sessions
    from .dialogs_remote import RemoteCommandConfirmDialog
    from .core import build_remote_command_wt_command, TerminalLauncher
    if not sessions:
        messagebox.showwarning("Keine Auswahl", "Bitte mindestens einen Host anhaken.", parent=app)
        return
    dialog = ServiceActionDialog(app, action, len(sessions), **({"initial": initial} if initial else {}))
    app.wait_window(dialog)
    if dialog.result is None:
        return
    retry_values = {"unit": dialog.unit.get(), "lines": dialog.lines.get(), "sudo": dialog.sudo.get()}
    command, password = dialog.result
    dialog.result = None
    from .operation_results import create_job, track_results
    job = None
    try:
        session_users = resolve_users_for_sessions(app, sessions, "all")
        if session_users is None:
            return
        confirm = RemoteCommandConfirmDialog(app, command, session_users, False)
        app.wait_window(confirm)
        if not confirm.result:
            return
        job = create_job(app, [session for session, _ in session_users], "Dienstaktion", lambda failed: run_service_action(app, failed, action, retry_values))
        with track_results(job):
            built = build_remote_command_wt_command([(session, user, command) for session, user in session_users], close_on_success=False,
                      sudo_password=password or None, session_colors=app._tree.get_session_colors(), terminal_settings=app.settings.windows_terminal)
        password = ""
        TerminalLauncher.launch_built_command(built, [session.display_name for session, _ in session_users], app.settings.windows_terminal)
        if job:
            job.launched()
    except (OSError, ValueError, RuntimeError):
        if job:
            job.uncertain_launch()
        messagebox.showerror("Dienstaktion fehlgeschlagen", "Dienstaktion konnte nicht vorbereitet oder gestartet werden.", parent=app)
    finally:
        password = ""
