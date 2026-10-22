"""Full table snapshots, text selection and theme-aware row hover."""
from __future__ import annotations

import csv
import io
import tkinter as tk
from tkinter import ttk
from .ui_components import fit_window_to_parent


def table_text(headers, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue()


def install_hover(tree):
    style = ttk.Style(tree)
    tree.tag_configure("row_hover", background=style.lookup("TreeHover.TFrame", "background") or style.lookup("Treeview", "selectbackground"))
    current = [None]
    def move(event=None):
        row = tree.identify_row(event.y) if event is not None else ""
        if current[0] and tree.exists(current[0]):
            tags = [t for t in tree.item(current[0], "tags") if t != "row_hover"]
            tree.item(current[0], tags=tags)
        current[0] = row
        if row:
            tree.item(row, tags=("row_hover", *[t for t in tree.item(row, "tags") if t != "row_hover"]))
    tree.bind("<Motion>", move, add="+")
    tree.bind("<Leave>", lambda _: move(), add="+")
    return move


class ResultTableTools:
    def __init__(self, owner, tree, parent, error_rows, row_values=None):
        self.owner, self.tree, self.error_rows = owner, tree, error_rows
        self.row_values = row_values or (lambda row: self.tree.item(row, "values"))
        tree.configure(selectmode="extended")
        self.hover = install_hover(tree)
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(6, 3))
        for label, mode in (("Alle Fehler kopieren", "errors"), ("Alles kopieren", "all"), ("Auswahl kopieren", "selection")):
            ttk.Button(actions, text=label, command=lambda m=mode: self.copy(m)).pack(side="left", padx=(0, 6))
        ttk.Label(parent, text="Zeilen: Strg/Umschalt · Textausschnitte unten markieren · Doppelklick für vollständige Details", style="Muted.TLabel").pack(anchor="w")
        self.text = tk.Text(parent, height=4, wrap="word", exportselection=False)
        self.text.pack(fill="x", pady=(4, 0))
        self.text.configure(state="disabled")
        tree.bind("<<TreeviewSelect>>", self.show_selection, add="+")
        tree.bind("<Control-c>", lambda _: self.copy("selection"))
        tree.bind("<Control-a>", self.select_all)
        tree.bind("<Double-1>", self.open_details, add="+")
        self.status = tk.StringVar()
        ttk.Label(parent, textvariable=self.status, style="Muted.TLabel").pack(anchor="w")

    def select_all(self, _event=None):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def snapshot(self, mode):
        columns = self.tree["columns"]
        headers = [self.tree.heading(c, "text") for c in columns]
        ids = set(self.error_rows()) if mode == "errors" else set(self.tree.selection()) if mode == "selection" else None
        rows = [self.row_values(i) for i in self.tree.get_children() if ids is None or i in ids]
        return headers, rows

    def copy(self, mode):
        headers, rows = self.snapshot(mode)
        if not rows:
            self.status.set("Keine passenden Zeilen vorhanden.")
            return "break"
        self.owner.clipboard_clear()
        self.owner.clipboard_append(table_text(headers, rows))
        self.status.set(f"{len(rows)} Zeilen kopiert.")
        return "break"

    def show_selection(self, _event=None):
        headers, rows = self.snapshot("selection")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n\n".join("\n".join(f"{h}: {v}" for h, v in zip(headers, row)) for row in rows))
        self.text.configure(state="disabled")

    def open_details(self, _event=None):
        headers, rows = self.snapshot("selection")
        if not rows:
            return
        window = tk.Toplevel(self.owner)
        window.title("Vollständige Ergebnisdetails")
        window.transient(self.owner)
        from tkinter.scrolledtext import ScrolledText
        text = ScrolledText(window, wrap="word", padx=12, pady=12)
        text.pack(fill="both", expand=True)
        text.insert("1.0", "\n\n".join("\n".join(f"{h}: {v}" for h, v in zip(headers, row)) for row in rows))
        text.configure(state="disabled")
        ttk.Button(window, text="Schließen", command=window.destroy).pack(pady=8)
        fit_window_to_parent(window, self.owner, 760, 430)
