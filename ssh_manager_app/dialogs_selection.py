from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .ui_components import install_context_help, center_on_parent


class SelectionReviewDialog(tk.Toplevel):
    """Review the complete action target set, including filtered-out hosts."""

    def __init__(self, app):
        super().__init__(app)
        install_context_help(self, "start")
        self.title("Häkchen-Auswahl prüfen")
        self.transient(app)
        self.geometry("620x360")
        self.tree = app._tree
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Diese Hosts werden von Aktionen für die Auswahl verwendet.", wraplength=560).pack(anchor="w", pady=(0, 10))
        self.list = ttk.Treeview(frame, columns=("host", "visibility"), show="tree headings", selectmode="extended")
        self.list.heading("#0", text="Verbindung")
        self.list.heading("host", text="Host")
        self.list.heading("visibility", text="In der Ansicht")
        self.list.column("#0", width=180)
        self.list.column("host", width=180)
        self.list.column("visibility", width=150)
        self.list.pack(fill="both", expand=True)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Markierte entfernen", command=self.remove).pack(side="left")
        ttk.Button(actions, text="Auswahl leeren", command=self.clear).pack(side="left", padx=8)
        ttk.Button(actions, text="Schließen", command=self.destroy).pack(side="right")
        self.refresh()
        center_on_parent(self, app)

    def refresh(self):
        self.list.delete(*self.list.get_children())
        hidden = self.tree.hidden_selected_keys()
        self.targets = self.tree.get_selected_sessions()
        for i, session in enumerate(self.targets):
            self.list.insert("", "end", iid=str(i), text=session.display_name,
                             values=(session.hostname, "durch Filter verborgen" if session.key in hidden else "sichtbar"))

    def remove(self):
        keys = [self.targets[int(i)].key for i in self.list.selection()]
        for key in keys:
            self.tree.remove_from_selection(key)
        self.refresh()

    def clear(self):
        self.tree.set_all_checked(False)
        self.refresh()


def review_selection(app):
    dialog = app.__dict__.get("_selection_review")
    if dialog is not None and dialog.winfo_exists():
        dialog.refresh()
        dialog.lift()
    else:
        app._selection_review = SelectionReviewDialog(app)
