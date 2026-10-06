from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from .secret_scripts import clear_password_fields
from .models import Session
from .ui_components import build_dialog_header, fit_window_to_parent


class ServerRestartDialog(tk.Toplevel):
    """Collects the shared options for a distributed server restart."""

    def __init__(self, parent: tk.Tk, session_users: list[tuple[Session, str]]):
        super().__init__(parent)
        self.title("Server neu starten")
        self.geometry("720x570")
        self.minsize(640, 500)
        self.result: dict | None = None
        self._password_var = tk.StringVar()
        self._show_password_var = tk.BooleanVar(value=False)
        self._service_var = tk.StringVar()
        self._timeout_var = tk.StringVar(value="5")
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build(session_users)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _event: self._on_cancel())

    def _build(self, session_users: list[tuple[Session, str]]) -> None:
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        build_dialog_header(
            frame,
            f"{len(session_users)} Server parallel neu starten?",
            "Optionen prüfen, bevor der Neustart auf allen ausgewählten Hosts ausgelöst wird.",
        )
        ttk.Label(
            frame,
            text="Achtung: Bereits ausgelöste Neustarts können nicht rückgängig gemacht werden.",
            style="Warning.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        hosts = ttk.LabelFrame(frame, text="Server", padding=8)
        hosts.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        hosts.columnconfigure(0, weight=1)
        hosts.rowconfigure(0, weight=1)
        hosts_text = scrolledtext.ScrolledText(hosts, wrap="word", height=9)
        hosts_text.grid(row=0, column=0, sticky="nsew")
        hosts_text.insert(
            "1.0",
            "\n".join(
                f"- {session.display_name} ({session.hostname})  Benutzer: {user}"
                for session, user in session_users
            ),
        )
        hosts_text.configure(state="disabled")

        options = ttk.LabelFrame(frame, text="Neustart und Prüfung", padding=10)
        options.grid(row=3, column=0, sticky="ew")
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="sudo-Passwort:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
        self._password_entry = ttk.Entry(options, textvariable=self._password_var, show="•")
        self._password_entry.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(
            options,
            text="anzeigen",
            variable=self._show_password_var,
            command=self._toggle_password,
        ).grid(row=0, column=2, sticky="w", padx=(8, 0), pady=5)

        ttk.Label(options, text="systemd-Unit (optional):").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(options, textvariable=self._service_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(
            options,
            text="Leer lassen, um nur Neustart und SSH-Rückkehr zu prüfen; Beispiel: wildfly.service",
            style="Muted.TLabel",
        ).grid(row=2, column=1, columnspan=2, sticky="w", pady=(0, 5))

        ttk.Label(options, text="Maximale Wartezeit:").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=5)
        timeout = ttk.Spinbox(options, from_=1, to=60, textvariable=self._timeout_var, width=7)
        timeout.grid(row=3, column=1, sticky="w", pady=5)
        ttk.Label(options, text="Minuten").grid(row=3, column=1, sticky="w", padx=(72, 0), pady=5)
        ttk.Label(
            options,
            text="Das Passwort wird nur für diesen Lauf verwendet und nicht gespeichert.",
            style="Muted.TLabel",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Server neu starten", command=self._on_ok, width=20, style="Danger.TButton").pack(side="left")
        self._password_entry.focus()

    def _toggle_password(self) -> None:
        self._password_entry.configure(show="" if self._show_password_var.get() else "•")

    def _on_ok(self) -> None:
        try:
            timeout_minutes = int(self._timeout_var.get().strip())
        except ValueError:
            messagebox.showwarning("Server neu starten", "Die Wartezeit muss eine ganze Zahl zwischen 1 und 60 sein.", parent=self)
            return
        if not 1 <= timeout_minutes <= 60:
            messagebox.showwarning("Server neu starten", "Die Wartezeit muss zwischen 1 und 60 Minuten liegen.", parent=self)
            return
        service = self._service_var.get().strip()
        if any(character in service for character in ("\n", "\r", "\x00")):
            messagebox.showwarning("Server neu starten", "Die systemd-Unit enthält ungültige Zeichen.", parent=self)
            return
        self.result = {
            "sudo_password": self._password_var.get(),
            "service": service,
            "timeout_seconds": timeout_minutes * 60,
        }
        clear_password_fields(self)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        clear_password_fields(self)
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        fit_window_to_parent(self, parent, 720, 570, min_width=580, min_height=440)


class ServerRestartProgressDialog(tk.Toplevel):
    """Displays live status for all parallel restart workers."""

    TERMINAL_STATES = {"online", "error", "timeout", "stopped"}
    STATUS_LABELS = {
        "pending": "… Wartet",
        "preflight": "… Vorprüfung",
        "restarting": "… Wird neu gestartet",
        "waiting_down": "… Warte auf Herunterfahren",
        "waiting_ssh": "… Warte auf SSH",
        "waiting_service": "… Warte auf Service",
        "online": "✓ Online",
        "error": "✗ Fehler",
        "timeout": "✗ Zeitüberschreitung",
        "stopped": "■ Überwachung gestoppt",
    }

    def __init__(self, parent: tk.Tk, session_users: list[tuple[Session, str]], service: str):
        super().__init__(parent)
        self.title("Server werden neu gestartet")
        self.geometry("860x480")
        self.minsize(720, 380)
        self._cancel_event = threading.Event()
        self._finished = False
        self._service = service
        self._rows: dict[str, str] = {}
        self._states = {session.key: "pending" for session, _user in session_users}
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_stop)
        self._build(session_users)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _event: self._on_stop())

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _build(self, session_users: list[tuple[Session, str]]) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = ttk.Frame(self, padding=(14, 14, 14, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self._summary_var = tk.StringVar(value=f"Neustart läuft… 0 von {len(session_users)} abgeschlossen")
        ttk.Label(header, textvariable=self._summary_var, style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")
        hint = "Nach SSH wird zusätzlich geprüft: " + self._service if self._service else "Nach dem Neustart wird die SSH-Rückkehr geprüft."
        ttk.Label(header, text=hint, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 8))
        self._progress = ttk.Progressbar(header, mode="indeterminate")
        self._progress.grid(row=2, column=0, sticky="ew")
        self._progress.start(12)

        table_frame = ttk.Frame(self, padding=(14, 0, 14, 8))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self._tree = ttk.Treeview(table_frame, columns=("host", "status", "detail"), show="headings", selectmode="none")
        self._tree.heading("host", text="Server", anchor="w")
        self._tree.heading("status", text="Status", anchor="w")
        self._tree.heading("detail", text="Details", anchor="w")
        self._tree.column("host", width=210, minwidth=140, anchor="w")
        self._tree.column("status", width=210, minwidth=170, anchor="w")
        self._tree.column("detail", width=390, minwidth=220, anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        for session, _user in session_users:
            host_label = f"{session.display_name} ({session.hostname})"
            item_id = self._tree.insert("", "end", values=(host_label, self.STATUS_LABELS["pending"], ""))
            self._rows[session.key] = item_id

        footer = ttk.Frame(self, padding=(14, 4, 14, 14))
        footer.grid(row=2, column=0, sticky="ew")
        self._stop_button = ttk.Button(footer, text="Überwachung stoppen", command=self._on_stop, width=22, style="Danger.TButton")
        self._stop_button.pack(side="right")

    def update_host(self, session_key: str, state: str, detail: str = "") -> None:
        item_id = self._rows.get(session_key)
        if item_id is None:
            return
        self._states[session_key] = state
        values = list(self._tree.item(item_id, "values"))
        values[1] = self.STATUS_LABELS.get(state, state)
        values[2] = detail
        self._tree.item(item_id, values=values)
        completed = sum(state in self.TERMINAL_STATES for state in self._states.values())
        self._summary_var.set(f"Neustart läuft… {completed} von {len(self._states)} abgeschlossen")

    def finish(self) -> None:
        self._finished = True
        try:
            self._progress.stop()
        except tk.TclError:
            pass
        online = sum(state == "online" for state in self._states.values())
        failed = sum(state in {"error", "timeout"} for state in self._states.values())
        stopped = sum(state == "stopped" for state in self._states.values())
        parts = [f"{online} online"]
        if failed:
            parts.append(f"{failed} fehlgeschlagen")
        if stopped:
            parts.append(f"{stopped} nicht weiter überwacht")
        self._summary_var.set("Abgeschlossen: " + ", ".join(parts))
        self._stop_button.configure(text="Schließen", command=self.destroy, style="Accent.TButton")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_stop(self) -> None:
        if self._finished:
            clear_password_fields(self)
            self.destroy()
            return
        if self._cancel_event.is_set():
            return
        confirmed = messagebox.askyesno(
            "Überwachung stoppen",
            "Die lokale Überwachung wird beendet. Bereits ausgelöste Server-Neustarts laufen weiter.\n\nÜberwachung wirklich stoppen?",
            parent=self,
        )
        if confirmed:
            self._cancel_event.set()
            self._stop_button.configure(state="disabled", text="Überwachung wird beendet…")

    def _center_on_parent(self, parent: tk.Tk) -> None:
        fit_window_to_parent(self, parent, 860, 480, min_width=640, min_height=340)
