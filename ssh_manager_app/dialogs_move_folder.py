from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from .ui_components import install_context_help, build_dialog_actions, build_dialog_header, center_on_parent


class MoveFolderDialog(tk.Toplevel):
    """
    Minimaler modaler Dialog zum Verschieben einer Session in einen anderen Ordner.
    Nach Schließen: self.result = Ordner-String oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, existing_folders: list[str], current_folder: str):
        super().__init__(parent)
        install_context_help(self, "folders")
        self.title("In Ordner verschieben")
        self.resizable(False, False)
        self.result: Optional[str] = None
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build(existing_folders, current_folder)
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, existing_folders: list[str], current_folder: str) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        build_dialog_header(
            frame,
            "In Ordner verschieben",
            "Vorhandenen Ordner auswählen oder einen neuen Pfad eingeben.",
            columnspan=2,
        )

        ttk.Label(frame, text="Ordner:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self._folder_var = tk.StringVar(value=current_folder)
        ttk.Combobox(
            frame, textvariable=self._folder_var,
            values=existing_folders, width=30,
        ).grid(row=1, column=1, sticky="ew")

        build_dialog_actions(
            frame,
            row=2,
            columnspan=2,
            primary_text="Verschieben",
            primary_command=self._on_ok,
            cancel_command=self._on_cancel,
        )

    def _on_ok(self) -> None:
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Ordner eingeben.", parent=self)
            return
        self.result = folder
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        center_on_parent(self, parent)
