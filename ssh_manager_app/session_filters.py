from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox

from .ssh_utils import read_port
from .ui_components import install_context_help, fit_window_to_parent

SOURCES = ("", "winscp", "ssh_config", "filezilla_config", "app", "ssh_alias")
SOURCE_LABELS = {"": "Alle aktivierten Quellen", "winscp": "WinSCP", "ssh_config": "SSH Config",
                 "filezilla_config": "FileZilla", "app": "Eigene Verbindungen", "ssh_alias": "Alias-Kopien"}


def validate_filters(filters):
    if not isinstance(filters, dict) or any(key not in ("source", "folder", "username", "port") for key in filters):
        raise ValueError("Ungültige Filter.")
    if not all(isinstance(v, str) for v in filters.values()):
        raise ValueError("Filterwerte müssen Text sein.")
    if filters.get("source", "") not in SOURCES:
        raise ValueError("Unbekannte Quelle.")
    if filters.get("port"):
        read_port(filters["port"])
    return {key: value.strip() for key, value in filters.items() if value.strip()}


def matches_filters(session, filters):
    return (not filters.get("source") or session.source == filters["source"]) and (
        not filters.get("folder") or filters["folder"].casefold() in session.folder_key.casefold()) and (
        not filters.get("username") or filters["username"].casefold() in session.username.casefold()) and (
        not filters.get("port") or session.port == int(filters["port"]))


def apply_session_filters(app, filters, query, *, persist=True):
    filters = validate_filters(filters)
    app._tree._structured_filters = dict(filters)
    app._initial_toolbar_search_texts["session_filters"] = dict(filters)
    if persist:
        app._search_var.set(query)
    app._tree.filter(query)
    names = {"source": "Quelle", "folder": "Ordner", "username": "Benutzer", "port": "Port"}
    app._filter_summary.set(" · ".join(f"{names[key]}: {SOURCE_LABELS[value] if key == 'source' else value}" for key, value in filters.items()) or "Keine Zusatzfilter")
    if persist:
        from .actions_ui import persist_ui_state
        persist_ui_state(app)


class SessionFiltersDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        install_context_help(self, "filters")
        self.app = app
        self.title("Filter und gespeicherte Ansichten")
        self.transient(app)
        self.grab_set()
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Filter wirken innerhalb der in Einstellungen aktivierten Quellen.", wraplength=550).grid(row=0, column=0, columnspan=2, sticky="w", pady=10)
        self.fields = {}
        active = app._tree.__dict__.get("_structured_filters", {})
        for row, (key, label) in enumerate((("query", "Suchtext"), ("source", "Quelle"), ("folder", "Ordner enthält"), ("username", "Benutzer enthält"), ("port", "Port (exakt)")), 1):
            variable = tk.StringVar(value=app._search_var.get() if key == "query" else SOURCE_LABELS[active.get(key, "")] if key == "source" else active.get(key, ""))
            self.fields[key] = variable
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
            widget = ttk.Combobox(frame, textvariable=variable, values=tuple(SOURCE_LABELS.values()), state="readonly") if key == "source" else ttk.Entry(frame, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text="Ansicht / neuer Name").grid(row=6, column=0, sticky="w", padx=(0, 10), pady=10)
        self.name = tk.StringVar()
        self.views = ttk.Combobox(frame, textvariable=self.name, values=list(app._initial_toolbar_search_texts.get("session_filter_views", {})))
        self.views.grid(row=6, column=1, sticky="ew")
        self.views.bind("<<ComboboxSelected>>", lambda _: self.load())
        actions = ttk.Frame(frame)
        actions.grid(row=7, column=0, columnspan=2, sticky="ew", pady=10)
        for label, callback in (("Ansicht speichern", self.save), ("Ansicht löschen", self.delete), ("Filter anwenden", self.apply), ("Abbrechen", self.destroy)):
            ttk.Button(actions, text=label, command=callback).pack(side="left", padx=(0, 5))
        fit_window_to_parent(self, app, 670, 420)

    def spec(self):
        values = {key: var.get() for key, var in self.fields.items() if key != "query"}
        values["source"] = next((key for key, label in SOURCE_LABELS.items() if label == values["source"]), "")
        return {"query": self.fields["query"].get(), "filters": validate_filters(values)}

    def load(self):
        spec = self.app._initial_toolbar_search_texts.get("session_filter_views", {}).get(self.name.get())
        if not isinstance(spec, dict):
            return
        try:
            filters = validate_filters(spec.get("filters", {}))
        except ValueError:
            messagebox.showwarning("Ungültige Ansicht", "Diese gespeicherte Ansicht bitte neu anlegen.", parent=self)
            return
        self.fields["query"].set(spec.get("query", ""))
        for key, var in self.fields.items():
            if key != "query":
                var.set(SOURCE_LABELS[filters.get(key, "")] if key == "source" else filters.get(key, ""))

    def persist_views(self, updated):
        from .actions_ui import persist_ui_state
        old = self.app._initial_toolbar_search_texts.get("session_filter_views", {})
        self.app._initial_toolbar_search_texts["session_filter_views"] = updated
        try:
            persist_ui_state(self.app)
        except OSError:
            self.app._initial_toolbar_search_texts["session_filter_views"] = old
            messagebox.showerror("Speichern fehlgeschlagen", "Ansichten konnten nicht gespeichert werden.", parent=self)
        self.views.configure(values=list(self.app._initial_toolbar_search_texts.get("session_filter_views", {})))

    def save(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showwarning("Name fehlt", "Einen Namen für die Ansicht eingeben.", parent=self)
            return
        try:
            spec = self.spec()
        except ValueError as exc:
            messagebox.showwarning("Filter prüfen", str(exc), parent=self)
            return
        views = deepcopy(self.app._initial_toolbar_search_texts.get("session_filter_views", {}))
        views[name] = spec
        self.persist_views(views)

    def delete(self):
        views = deepcopy(self.app._initial_toolbar_search_texts.get("session_filter_views", {}))
        if self.name.get() in views and messagebox.askyesno("Ansicht löschen", "Diese gespeicherte Ansicht entfernen?", parent=self):
            views.pop(self.name.get())
            self.persist_views(views)

    def apply(self):
        try:
            spec = self.spec()
            apply_session_filters(self.app, spec["filters"], spec["query"])
        except (ValueError, OSError) as exc:
            messagebox.showwarning("Filter prüfen", str(exc), parent=self)
            return
        self.destroy()
