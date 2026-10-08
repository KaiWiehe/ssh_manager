from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .ui_components import install_context_help, build_dialog_actions, build_dialog_header, center_on_parent


EXPORT_COLUMNS = (
    ("display_name", "Name"),
    ("hostname", "Hostname / IP-Adresse"),
    ("username", "Benutzer"),
    ("port", "Port"),
    ("notes", "Notiz"),
    ("source", "Quelle"),
)


class ExportColumnsDialog(tk.Toplevel):
    """Modal selection dialog for the columns of a connection export."""

    def __init__(self, parent: tk.Tk, export_label: str, scope_counts: dict[str, int] | None = None):
        super().__init__(parent)
        install_context_help(self, "data")
        self.title(f"{export_label} exportieren")
        self.resizable(False, False)
        self.result: list[str] | None = None
        self._excel_safe_var = tk.BooleanVar(value=True)
        self.excel_safe = True
        self.scope = "context" if scope_counts and "context" in scope_counts else "view"
        self._scope_var = tk.StringVar(value=self.scope)
        self._scope_counts = scope_counts or {}
        self._vars = {
            key: tk.BooleanVar(value=key in {"display_name", "hostname"})
            for key, _label in EXPORT_COLUMNS
        }
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build(export_label)
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _event: self._on_ok())
        self.bind("<Escape>", lambda _event: self._on_cancel())

    def _build(self, export_label: str) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        build_dialog_header(
            frame,
            f"{export_label} exportieren",
            "Verbindungsliste exportieren. Dies ist kein vollständiges App-Backup.",
        )
        scope = ttk.LabelFrame(frame, text="Umfang", padding=8)
        scope.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        options = (("context", "Nur Ziele aus diesem Rechtsklick"),) if "context" in self._scope_counts else (("view", "Aktuelle Ansicht"), ("selection", "Häkchen-Auswahl (auch verborgene Hosts)"), ("all", "Alle geladenen Verbindungen"))
        for key, label in options:
            count = self._scope_counts.get(key)
            text = f"{label}: {count}" if count is not None else label
            ttk.Radiobutton(scope, text=text, variable=self._scope_var, value=key).pack(anchor="w")
        for row, (key, label) in enumerate(EXPORT_COLUMNS, start=2):
            ttk.Checkbutton(frame, text=label, variable=self._vars[key]).grid(
                row=row, column=0, sticky="w", pady=2
            )

        if export_label == "CSV":
            ttk.Checkbutton(frame, text="Excel-sicher: mögliche Formeln als Text exportieren", variable=self._excel_safe_var).grid(
                row=len(EXPORT_COLUMNS) + 2, column=0, sticky="w", pady=(10, 0)
            )
            ttk.Label(frame, text="Ohne Haken: unveränderte Rohdaten, beim Öffnen in Excel können Formeln ausgeführt werden.",
                      wraplength=440, style="Muted.TLabel").grid(row=len(EXPORT_COLUMNS) + 3, column=0, sticky="w", pady=(4, 0))

        build_dialog_actions(
            frame,
            row=len(EXPORT_COLUMNS) + 4,
            primary_text="Exportieren",
            primary_command=self._on_ok,
            cancel_command=self._on_cancel,
        )

    def _on_ok(self) -> None:
        self.result = [key for key, _label in EXPORT_COLUMNS if self._vars[key].get()]
        if not self.result:
            return
        self.excel_safe = self._excel_safe_var.get()
        self.scope = self._scope_var.get()
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        center_on_parent(self, parent)
