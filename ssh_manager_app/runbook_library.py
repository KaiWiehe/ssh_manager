from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox

from .dialogs_remote import RemoteCommandDialog, RemoteFavoriteEditDialog
from .ui_components import fit_window_to_parent


class RunbookLibraryDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Runbook-Bibliothek")
        self.transient(app)
        self.items = deepcopy(app._initial_toolbar_search_texts.get("remote_command_favorites", []))
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Runbooks verwalten. Ausführen verwendet die Häkchen-Auswahl im Hauptfenster.", wraplength=660).pack(anchor="w")
        self.query = tk.StringVar()
        ttk.Entry(frame, textvariable=self.query).pack(fill="x", pady=8)
        self.query.trace_add("write", lambda *_: self.refresh())
        self.list = ttk.Treeview(frame, columns=("mode", "note"), show="tree headings", selectmode="browse")
        self.list.heading("#0", text="Name")
        self.list.heading("mode", text="Aufgabe")
        self.list.heading("note", text="Notiz")
        self.list.column("#0", width=220)
        self.list.column("mode", width=140)
        self.list.column("note", width=270)
        self.list.pack(fill="both", expand=True)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=10)
        new_menu = tk.Menu(actions, tearoff=False)
        for mode, label in (("command", "Befehl"), ("local_script", "Lokales Skript"), ("remote_script", "Serverskript")):
            new_menu.add_command(label=label, command=lambda m=mode: self.edit_content(m))
        ttk.Menubutton(actions, text="Neu…", menu=new_menu).pack(side="left")
        for label, callback in (("Inhalt…", self.edit_content), ("Name/Notiz…", self.metadata),
                                ("An-/abpinnen", self.pin), ("Löschen", self.delete), ("Ausführen…", self.run)):
            ttk.Button(actions, text=label, command=callback).pack(side="left", padx=(5, 0))
        ttk.Button(frame, text="Schließen", command=self.destroy).pack(anchor="e")
        self.refresh()
        fit_window_to_parent(self, app, 780, 480, min_width=620, min_height=340)

    def refresh(self):
        selected = self.list.selection()
        keep = selected[0] if selected else None
        self.list.delete(*self.list.get_children())
        query = self.query.get().casefold().strip()
        for index in sorted(range(len(self.items)), key=lambda i: (not self.items[i].get("pinned"), str(self.items[i].get("name", "")).casefold())):
            item = self.items[index]
            name = item.get("name") or item.get("label") or item.get("path") or next(iter(item.get("command", "").splitlines()), "Runbook")
            name = str(name or "Runbook")
            if query and query not in f"{name} {item.get('note', '')} {item.get('mode', 'command')}".casefold():
                continue
            self.list.insert("", "end", iid=str(index), text=("★ " if item.get("pinned") else "") + name,
                             values=(item.get("mode", "command"), item.get("note", "")))
        if keep and self.list.exists(keep):
            self.list.selection_set(keep)

    def selected_index(self):
        selection = self.list.selection()
        return int(selection[0]) if selection else None

    def save(self):
        from .actions_ui import persist_ui_state
        old = self.app._initial_toolbar_search_texts.get("remote_command_favorites", [])
        self.app._initial_toolbar_search_texts["remote_command_favorites"] = deepcopy(self.items)
        try:
            persist_ui_state(self.app)
        except OSError:
            self.app._initial_toolbar_search_texts["remote_command_favorites"] = old
            self.items = deepcopy(old)
            messagebox.showerror("Speichern fehlgeschlagen", "Runbook-Änderungen konnten nicht gespeichert werden.", parent=self)
        self.refresh()

    def edit_content(self, new_mode=None):
        index = self.selected_index() if new_mode is None else None
        if new_mode is None and index is None:
            return
        if new_mode and len(self.items) >= 25:
            messagebox.showinfo("Bibliothek voll", "Maximal 25 Runbooks. Bitte nicht mehr benötigte Einträge entfernen.", parent=self)
            return
        original = self.items[index] if index is not None else {"mode": new_mode, "interpreter": "bash"}
        editor = RemoteCommandDialog(self, 0, run_mode=original.get("mode", "command"), editing=True)
        editor.title("Runbook-Inhalt bearbeiten")
        if index is not None:
            editor._apply_spec(original)
        self.wait_window(editor)
        if editor.result is None:
            return
        updated = {**original, **editor.result[1]}
        if index is None:
            updated.setdefault("name", updated.get("path") or next(iter(updated.get("command", "").splitlines()), "Runbook"))
            metadata = RemoteFavoriteEditDialog(self, updated, title="Runbook anlegen")
            self.wait_window(metadata)
            if metadata.result is None:
                return
            self.items.append(metadata.result)
        else:
            self.items[index] = updated
        self.save()

    def metadata(self):
        index = self.selected_index()
        if index is None:
            return
        editor = RemoteFavoriteEditDialog(self, self.items[index])
        self.wait_window(editor)
        if editor.result is not None:
            self.items[index] = editor.result
            self.save()

    def pin(self):
        index = self.selected_index()
        if index is not None:
            self.items[index]["pinned"] = not self.items[index].get("pinned", False)
            self.save()

    def delete(self):
        index = self.selected_index()
        if index is not None and messagebox.askyesno("Runbook löschen", "Diesen Eintrag aus der Bibliothek entfernen?", parent=self):
            self.items.pop(index)
            self.save()

    def run(self):
        index = self.selected_index()
        if index is None:
            return
        from .actions_remote import run_remote_command
        item = deepcopy(self.items[index])
        run_remote_command(self.app, self.app._tree.get_selected_sessions(), run_mode=item.get("mode", "command"), initial_spec=item)
        self.items = deepcopy(self.app._initial_toolbar_search_texts.get("remote_command_favorites", []))
        self.refresh()


def open_runbook_library(app):
    existing = app.__dict__.get("_runbook_library")
    if existing is not None and existing.winfo_exists():
        existing.items = deepcopy(app._initial_toolbar_search_texts.get("remote_command_favorites", []))
        existing.refresh()
        existing.lift()
    else:
        app._runbook_library = RunbookLibraryDialog(app)
