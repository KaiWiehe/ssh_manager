from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from . import DEFAULT_USER, QUICK_USERS

_USERNAME_RE = __import__("re").compile(r"^[A-Za-z0-9._-]+$")
_HOSTNAME_RE = __import__("re").compile(r"^[A-Za-z0-9._:-]+$")


def _build_quickselect_buttons(parent: ttk.Frame, usernames: list[str], target_var: tk.StringVar, columns: int = 4, width: int = 14) -> ttk.Frame:
    """Erzeugt ein kompaktes, umbrechendes Quickselect-Button-Grid."""
    frame = ttk.Frame(parent)
    button_columns = max(1, columns)
    for col in range(button_columns):
        frame.columnconfigure(col, weight=1)
    for index, username in enumerate(usernames):
        row = index // button_columns
        col = index % button_columns
        ttk.Button(
            frame,
            text=username,
            command=lambda u=username: target_var.set(u),
            width=width,
        ).grid(row=row, column=col, padx=2, pady=2, sticky="ew")
    return frame

class UserDialog(tk.Toplevel):
    """
    Modaler Dialog zur Benutzernamen-Auswahl.
    Nach Schließen: self.result = gewählter Username (str) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, title: str = "Benutzername auswählen", quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: Optional[str] = None
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        # Modal machen
        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        # Tastaturkürzel
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        quick_count = max(len(self._quick_users), 1)
        ttk.Label(frame, text="Quickselect:").grid(
            row=0, column=0, columnspan=quick_count, sticky="w", pady=(0, 4)
        )

        self._user_var = tk.StringVar(value=self._default_user)

        quick_frame = _build_quickselect_buttons(frame, self._quick_users, self._user_var)
        quick_frame.grid(row=1, column=0, columnspan=quick_count, sticky="ew", pady=(0, 8))

        # Freitext-Eingabe
        ttk.Label(frame, text="Benutzername:").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=3, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.select_range(0, "end")
        entry.focus()

        # OK / Abbrechen
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(
            side="left", padx=4
        )

    def _on_ok(self) -> None:
        user = self._user_var.get().strip()
        if not user:
            return  # Leeres Feld: Dialog bleibt offen
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = user
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

