from __future__ import annotations

import tkinter as tk
from tkinter import ttk


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

    def __init__(self, parent: tk.Tk, export_label: str):
        super().__init__(parent)
        self.title(f"{export_label} exportieren")
        self.resizable(False, False)
        self.result: list[str] | None = None
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
        ttk.Label(frame, text=f"Spalten für den {export_label}-Export:").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            frame,
            text="Jeder sichtbare Ordner wird als eigene Tabelle exportiert.",
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))
        for row, (key, label) in enumerate(EXPORT_COLUMNS, start=2):
            ttk.Checkbutton(frame, text=label, variable=self._vars[key]).grid(
                row=row, column=0, sticky="w", pady=2
            )

        buttons = ttk.Frame(frame)
        buttons.grid(row=len(EXPORT_COLUMNS) + 2, column=0, pady=(14, 0))
        ttk.Button(buttons, text="Exportieren", command=self._on_ok, width=12).pack(side="left", padx=4)
        ttk.Button(buttons, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        self.result = [key for key, _label in EXPORT_COLUMNS if self._vars[key].get()]
        if not self.result:
            return
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_reqheight()) // 2
        self.geometry(f"+{x}+{y}")
