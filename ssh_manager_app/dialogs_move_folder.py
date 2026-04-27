from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional


class MoveFolderDialog(tk.Toplevel):
    """
    Minimaler modaler Dialog zum Verschieben einer Session in einen anderen Ordner.
    Nach Schließen: self.result = Ordner-String oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, existing_folders: list[str], current_folder: str):
        super().__init__(parent)
        self.title("In Ordner verschieben")
        self.resizable(False, False)
        self.result: Optional[str] = None
        self.transient(parent)
        self.grab_set()
        self._build(existing_folders, current_folder)
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, existing_folders: list[str], current_folder: str) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Ordner:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        self._folder_var = tk.StringVar(value=current_folder)
        ttk.Combobox(
            frame, textvariable=self._folder_var,
            values=existing_folders, width=30,
        ).grid(row=0, column=1, sticky="ew")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

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
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")
