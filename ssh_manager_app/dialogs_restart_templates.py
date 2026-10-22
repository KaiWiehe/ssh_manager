"""Editable restart tables, saved templates and read-only per-host service browsing."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import tkinter as tk
from tkinter import ttk, messagebox
import uuid

from .restart_templates import (all_connections, new_template, resolve_targets, service_check,
                                target_fingerprint, validate_library, validate_template)
from .ui_components import fit_window_to_parent, install_context_help
from .workers import run_worker


def modal(window, parent, title, width=820, height=520):
    window.title(title)
    window.transient(parent)
    window.grab_set()
    fit_window_to_parent(window, parent, width, height)


class SaveTemplateChoice(tk.Toplevel):
    def __init__(self, parent, name):
        super().__init__(parent)
        self.result = None
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Wie möchtest du die geänderte Vorlage speichern?").pack(anchor="w")
        self.name = tk.StringVar(value=name + " – Kopie")
        ttk.Label(body, text="Name für eine neue Vorlage:").pack(anchor="w", pady=(14, 4))
        ttk.Entry(body, textvariable=self.name).pack(fill="x")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=14)
        for label, choice in (("Als neue Vorlage speichern", "new"), ("Bestehende überschreiben", "overwrite"), ("Abbrechen", "cancel")):
            ttk.Button(buttons, text=label, command=lambda c=choice: self.choose(c)).pack(side="left", padx=(0, 6))
        modal(self, parent, "Vorlage speichern", 690, 220)

    def choose(self, choice):
        self.result = (choice, self.name.get().strip()) if choice != "cancel" else None
        self.destroy()


class ConnectionPicker(tk.Toplevel):
    def __init__(self, parent, sessions, multiple=False):
        super().__init__(parent)
        self.sessions = list(sessions)
        self.result = None
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Aktuelle Verbindung auswählen" + (" (Strg/Umschalt für mehrere)" if multiple else "")).pack(anchor="w")
        self.tree = ttk.Treeview(frame, columns=("host", "source"), selectmode="extended" if multiple else "browse")
        self.tree.heading("#0", text="Server")
        self.tree.heading("host", text="Hostname / Port")
        self.tree.heading("source", text="Quelle")
        self.tree.column("source", width=110)
        bar = ttk.Scrollbar(frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True, pady=10)
        for i, session in enumerate(self.sessions):
            self.tree.insert("", "end", iid=str(i), text=session.display_name, values=(f"{session.hostname}:{session.port}", session.source))
        ttk.Button(frame, text="Übernehmen", command=self.accept).pack(side="right")
        ttk.Button(frame, text="Abbrechen", command=self.destroy).pack(side="right", padx=8)
        modal(self, parent, "Verbindungen auswählen")

    def accept(self):
        if self.tree.selection():
            self.result = [self.sessions[int(i)] for i in self.tree.selection()]
            self.destroy()


class ServicePicker(tk.Toplevel):
    def __init__(self, parent, session, user, on_accept):
        super().__init__(parent)
        self.on_accept = on_accept
        self.entries, self.visible, self.chosen = [], [], set()
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Dienste auf {session.display_name} · Benutzer: {user}", wraplength=650).pack(anchor="w")
        self.status = tk.StringVar(value="Lesende SSH-Abfrage läuft …")
        ttk.Label(frame, textvariable=self.status, wraplength=650).pack(anchor="w", pady=8)
        self.query = tk.StringVar()
        ttk.Entry(frame, textvariable=self.query).pack(fill="x")
        self.list = tk.Listbox(frame, selectmode="extended", exportselection=False, height=14)
        self.list.pack(fill="both", expand=True, pady=8)
        self.query.trace_add("write", lambda *_: self.filter())
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Label(buttons, text="Strg/Umschalt für Mehrfachauswahl").pack(side="left")
        self.accept_button = ttk.Button(buttons, text="Auswahl übernehmen", command=self.accept, state="disabled")
        self.accept_button.pack(side="right")
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right", padx=6)
        modal(self, parent, "Services durchsuchen", 740, 520)
        session = replace(session, ssh_user_override=user if session.is_ssh_config_session else "")
        from .remote_browser import list_services
        run_worker(self, lambda: list_services(session, user), self.loaded,
                   lambda _: self.status.set("Dienste konnten nicht gelesen werden. SSH-Benutzer, Zugang und systemd prüfen. Bisherige Eingaben bleiben erhalten."))

    def loaded(self, entries):
        self.entries = [name for _, name in entries]
        self.status.set(f"{len(entries)} Dienste gefunden. Die Abfrage ändert keine Dienste.")
        self.accept_button.configure(state="normal")
        self.filter()

    def filter(self):
        for i in self.list.curselection():
            self.chosen.add(self.visible[i])
        for i, name in enumerate(self.visible):
            if i not in self.list.curselection():
                self.chosen.discard(name)
        self.visible = [name for name in self.entries if self.query.get().casefold() in name.casefold()]
        self.list.delete(0, "end")
        for i, name in enumerate(self.visible):
            self.list.insert("end", name)
            if name in self.chosen:
                self.list.selection_set(i)

    def accept(self):
        self.filter()
        self.on_accept(sorted(self.chosen, key=str.casefold))
        self.destroy()


class ServiceChecks(ttk.Frame):
    def __init__(self, parent, checks):
        super().__init__(parent)
        self.fields = []
        self.columnconfigure(0, weight=1)
        for check in checks:
            self.add(check["unit"], check["expected"])
        self.addrow = ttk.Frame(self)
        self.addrow.grid(row=100, column=0, sticky="ew", pady=3)
        self.new = tk.StringVar()
        ttk.Entry(self.addrow, textvariable=self.new, width=22).pack(side="left", fill="x", expand=True)
        ttk.Button(self.addrow, text="+", width=3, command=self.add_new).pack(side="left", padx=(4, 0))
        self.bind("<Return>", lambda _: self.add_new())

    def add(self, name="", expected="active"):
        row = ttk.Frame(self)
        row.grid(row=len(self.fields), column=0, sticky="ew", pady=2)
        row.columnconfigure(0, weight=1)
        unit, want = tk.StringVar(value=name), tk.StringVar(value="aktiv" if expected == "active" else "inaktiv")
        ttk.Entry(row, textvariable=unit, width=25).grid(row=0, column=0, sticky="ew")
        ttk.Combobox(row, textvariable=want, values=("aktiv", "inaktiv"), state="readonly", width=7).grid(row=0, column=1, padx=4)
        field = (row, unit, want)
        ttk.Button(row, text="×", width=3, command=lambda: self.remove(field)).grid(row=0, column=2)
        self.fields.append(field)

    def remove(self, field):
        self.fields.remove(field)
        field[0].destroy()
        for i, (row, _, _) in enumerate(self.fields):
            row.grid_configure(row=i)

    def add_new(self):
        if not self.new.get().strip():
            return
        try:
            check = service_check(self.new.get())
        except ValueError as error:
            messagebox.showwarning("Service", str(error), parent=self.winfo_toplevel())
            return
        if check["unit"] not in [u.get() for _, u, _ in self.fields]:
            self.add(check["unit"])
        self.new.set("")

    def values(self):
        self.add_new()
        if self.new.get().strip():
            raise ValueError("Ungültigen Service korrigieren oder entfernen.")
        return [service_check(unit.get(), "active" if want.get() == "aktiv" else "inactive") for _, unit, want in self.fields]


class RestartPreview(tk.Toplevel):
    def __init__(self, parent, template, targets):
        super().__init__(parent)
        self.result = None
        self.password = tk.StringVar()
        self._password_var = self.password
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=template["name"], style="DialogTitle.TLabel").pack(anchor="w")
        mode = "nacheinander" if template["mode"] == "serial" else f"maximal {template['max_parallel']} gleichzeitig"
        policy = {"pause": "pausieren und nachfragen", "stop": "weitere Neustarts stoppen", "continue": "weiterlaufen"}[template["on_error"]]
        ttk.Label(frame, text=f"{len(targets)} Server · {mode} · Bei Fehlern: {policy}\n"
                  f"Neustart/SSH: {template['reboot_timeout']} s · danach Services: {template['service_timeout']} s", wraplength=780).pack(anchor="w", pady=8)
        from tkinter.scrolledtext import ScrolledText
        text = ScrolledText(frame, wrap="word", height=15)
        text.pack(fill="both", expand=True)
        for i, (session, user, checks) in enumerate(targets, 1):
            text.insert("end", f"{i}. {session.display_name} · {session.hostname}:{session.port} · Benutzer: {user}\n")
            text.insert("end", "\n".join(f"    {c['unit']} → {'aktiv' if c['expected'] == 'active' else 'inaktiv'}" for c in checks) or "    Nur Neustartbestätigung und SSH")
            text.insert("end", "\n\n")
        text.configure(state="disabled")
        ttk.Label(frame, text="sudo-Passwort (optional, nur dieser Lauf):").pack(anchor="w", pady=(12, 4))
        ttk.Entry(frame, textvariable=self.password, show="•").pack(fill="x")
        ttk.Label(frame, text="Bereits ausgelöste Neustarts lassen sich nicht zurücknehmen. Dienste werden nur geprüft, nicht verändert.",
                  style="Warning.TLabel", wraplength=780).pack(anchor="w", pady=10)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text=f"{len(targets)} Server jetzt neu starten", style="Danger.TButton", command=self.accept).pack(side="right")
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right", padx=8)
        modal(self, parent, "Massen-Neustart – Startvorschau", 880, 650)

    def accept(self):
        self.result = self.password.get()
        self.password.set("")
        self.destroy()


class RestartTemplatesDialog(tk.Toplevel):
    def __init__(self, app, selection):
        super().__init__(app)
        self.app, self.selection = app, list(selection)
        self.template = None
        self.original = None
        self.rows = []
        try:
            self.library = validate_library(deepcopy(app._initial_toolbar_search_texts.get("restart_templates", {"schema": 1, "items": []})))
        except ValueError as error:
            messagebox.showerror("Neustart-Vorlagen", str(error) + "\nGespeicherte Daten bleiben unverändert.", parent=app)
            self.destroy()
            return
        install_context_help(self, "restart_templates")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=10)
        self.library_frame = ttk.Frame(self.notebook, padding=10)
        self.editor = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.library_frame, text="Vorlagen")
        self.notebook.add(self.editor, text="Vorlage bearbeiten")
        self._build_library()
        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, style="Muted.TLabel", padding=(14, 4)).pack(fill="x")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _: self.close())
        self.refresh_library()
        modal(self, app, "Massen-Neustarts", 1150, 800)
        if selection:
            self.create()
        else:
            ttk.Label(self.editor, text="Eine Vorlage öffnen oder aus ausgewählten Servern erstellen.").pack(pady=30)

    def _build_library(self):
        ttk.Label(self.library_frame, text="Gespeicherte Neustarts öffnen, prüfen und starten.", style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 10))
        self.list = ttk.Treeview(self.library_frame, columns=("count", "mode"), selectmode="browse")
        for col, label in (("#0", "Vorlage"), ("count", "Server"), ("mode", "Ablauf")):
            self.list.heading(col, text=label)
        self.list.pack(fill="both", expand=True)
        self.list.bind("<Double-1>", lambda _: self.open_selected())
        buttons = ttk.Frame(self.library_frame)
        buttons.pack(fill="x", pady=12)
        for label, callback in (("Aus Auswahl erstellen", self.create), ("Öffnen / bearbeiten", self.open_selected),
                                ("Vorlage löschen", self.delete_template), ("Schließen", self.close)):
            ttk.Button(buttons, text=label, command=callback).pack(side="left", padx=(0, 8))

    def refresh_library(self):
        self.list.delete(*self.list.get_children())
        for item in self.library["items"]:
            self.list.insert("", "end", iid=item["id"], text=item["name"],
                values=(len(item["targets"]), "parallel" if item["mode"] == "parallel" else "nacheinander"))

    def discard_ok(self):
        if self.template is None:
            return True
        try:
            dirty = self.collect() != self.original
        except ValueError:
            dirty = True
        if not dirty:
            return True
        answer = messagebox.askyesnocancel("Ungespeicherte Änderungen", "Änderungen vor dem Verlassen speichern?", parent=self)
        return self.save() if answer else answer is False

    def close(self):
        if self.discard_ok():
            self.destroy()

    def create(self):
        if not self.selection:
            messagebox.showinfo("Server auswählen", "Links im Hauptfenster Server anhaken und Massen-Neustarts erneut öffnen. Alternativ eine gespeicherte Vorlage öffnen.", parent=self)
            return
        if self.discard_ok():
            self.load(new_template(self.selection), existing=False)

    def open_selected(self):
        selected = self.list.selection()
        if selected and self.discard_ok():
            self.load(next(i for i in self.library["items"] if i["id"] == selected[0]))

    def load(self, template, existing=True):
        self.template = deepcopy(template)
        self.original = deepcopy(template) if existing else None
        self.build_editor()
        self.notebook.select(self.editor)

    def build_editor(self):
        for child in self.editor.winfo_children():
            child.destroy()
        self.rows = []
        header = ttk.Frame(self.editor)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Vorlagenname").pack(side="left", padx=(0, 8))
        self.name = tk.StringVar(value=self.template["name"])
        ttk.Entry(header, textvariable=self.name, width=40).pack(side="left", fill="x", expand=True)
        toolbar = ttk.Frame(self.editor)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="Quick-Access-User:").pack(side="left")
        self.quick = tk.StringVar(value=self.app.settings.default_user)
        ttk.Combobox(toolbar, textvariable=self.quick, values=list(self.app.settings.quick_users), width=16).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Leere Benutzer füllen", command=self.fill_users).pack(side="left")
        ttk.Button(toolbar, text="Server hinzufügen…", command=self.add_targets).pack(side="right")
        ttk.Label(self.editor, text="Service frei eingeben und + drücken · Sollzustand je Dienst wählen · Durchsuchen liest nur diesen Server",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        scroll = ttk.Frame(self.editor)
        scroll.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(scroll, highlightthickness=0)
        vertical = ttk.Scrollbar(scroll, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(scroll, orient="horizontal", command=self.canvas.xview)
        vertical.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table = ttk.Frame(self.canvas)
        window = self.canvas.create_window((0, 0), window=table, anchor="nw")
        def fit_table(_event=None):
            self.canvas.itemconfigure(window, width=max(self.canvas.winfo_width(), table.winfo_reqwidth()))
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        table.bind("<Configure>", fit_table)
        self.canvas.bind("<Configure>", fit_table)
        self.canvas.configure(background=ttk.Style(self).lookup("TFrame", "background"))
        table.columnconfigure(2, weight=1)
        for i, text in enumerate(("Server / aktuelles Ziel", "Benutzer", "Service / Sollzustand", "Serveraktionen")):
            ttk.Label(table, text=text, style="Muted.TLabel", padding=(6, 8)).grid(row=0, column=i, sticky="w")
        connections = {}
        for session in all_connections(self.app):
            connections.setdefault(session.key, []).append(session)
        for i, target in enumerate(self.template["targets"]):
            matches = connections.get(target["key"], [])
            session = matches[0] if len(matches) == 1 else None
            label = session.display_name if session else target["label"]
            details = f"{session.hostname}:{session.port}" if session else "Verbindung mehrdeutig – ersetzen oder entfernen" if matches else "Verbindung fehlt – ersetzen oder entfernen"
            server = ttk.Frame(table, padding=(6, 8))
            server.grid(row=i+1, column=0, sticky="nw")
            ttk.Label(server, text=f"{i+1}. {label}").pack(anchor="w")
            ttk.Label(server, text=details, wraplength=220, style="Muted.TLabel" if session else "Error.TLabel").pack(anchor="w")
            user = tk.StringVar(value=target["user"])
            ttk.Combobox(table, textvariable=user, values=list(self.app.settings.quick_users), width=15).grid(row=i+1, column=1, sticky="new", padx=6, pady=8)
            checks = ServiceChecks(table, target["checks"])
            checks.grid(row=i+1, column=2, sticky="new", padx=6, pady=6)
            actions = ttk.Frame(table, padding=4)
            actions.grid(row=i+1, column=3, sticky="ne")
            ttk.Button(actions, text="Durchsuchen…", command=lambda index=i: self.browse(index)).grid(row=0, column=0, columnspan=2, sticky="ew")
            ttk.Button(actions, text="Ersetzen…", command=lambda index=i: self.replace_target(index)).grid(row=1, column=0, columnspan=2, sticky="ew", pady=3)
            ttk.Button(actions, text="↑", width=3, command=lambda index=i: self.move(index, -1)).grid(row=2, column=0)
            ttk.Button(actions, text="↓", width=3, command=lambda index=i: self.move(index, 1)).grid(row=2, column=1)
            ttk.Button(actions, text="Entfernen", command=lambda index=i: self.remove_target(index)).grid(row=3, column=0, columnspan=2, sticky="ew", pady=3)
            self.rows.append((user, checks))
        self._bind_scroll(table)
        options = ttk.LabelFrame(self.editor, text="Ablauf", padding=8)
        options.pack(fill="x", pady=10)
        self.options = {}
        fields = (("mode", "Ablauf", ("parallel", "nacheinander")), ("max_parallel", "Max. gleichzeitig", None),
                  ("on_error", "Bei Fehlern", ("pausieren und nachfragen", "weitere stoppen", "weiterlaufen")),
                  ("reboot_timeout", "Neustart / SSH (s)", None), ("service_timeout", "Danach Services (s)", None))
        for col, (key, title, values) in enumerate(fields):
            options.columnconfigure(col, weight=1)
            ttk.Label(options, text=title).grid(row=0, column=col, sticky="w", padx=4)
            value = self.template[key]
            if key == "mode":
                value = "parallel" if value == "parallel" else "nacheinander"
            if key == "on_error":
                value = {"pause": "pausieren und nachfragen", "stop": "weitere stoppen", "continue": "weiterlaufen"}[value]
            var = tk.StringVar(value=str(value))
            self.options[key] = var
            if values:
                widget = ttk.Combobox(options, textvariable=var, values=values, state="readonly", width=23 if key == "on_error" else 14)
            else:
                widget = ttk.Spinbox(options, textvariable=var, from_=1, to=128 if key == "max_parallel" else 3600, width=7)
            widget.grid(row=1, column=col, sticky="ew", padx=4, pady=4)
        footer = ttk.Frame(self.editor)
        footer.pack(fill="x")
        ttk.Button(footer, text="Speichern…", command=self.save).pack(side="right", padx=6)
        ttk.Button(footer, text="Vorschau und starten…", command=self.preview, style="Accent.TButton").pack(side="right")

    def _bind_scroll(self, widget):
        if not isinstance(widget, (ttk.Combobox, ttk.Spinbox)):
            widget.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"), add="+")
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def fill_users(self):
        user = self.quick.get().strip()
        from .ssh_utils import connection_value
        try:
            connection_value(user, "Benutzer")
        except ValueError as error:
            messagebox.showwarning("Benutzer", str(error), parent=self)
            return
        for variable, _ in self.rows:
            if not variable.get().strip():
                variable.set(user)

    def collect(self):
        item = deepcopy(self.template)
        item["name"] = self.name.get().strip()
        for target, (user, checks) in zip(item["targets"], self.rows):
            target["user"], target["checks"] = user.get().strip(), checks.values()
        item["mode"] = "parallel" if self.options["mode"].get() == "parallel" else "serial"
        item["on_error"] = {"pausieren und nachfragen": "pause", "weitere stoppen": "stop", "weiterlaufen": "continue"}[self.options["on_error"].get()]
        for key in ("max_parallel", "reboot_timeout", "service_timeout"):
            try:
                item[key] = int(self.options[key].get())
            except ValueError as error:
                raise ValueError("Parallelität und Wartezeiten müssen ganze Zahlen sein.") from error
        return item

    def mutate(self, callback):
        try:
            self.template = self.collect()
        except ValueError as error:
            messagebox.showwarning("Vorlage", str(error), parent=self)
            return
        callback()
        self.build_editor()

    def move(self, index, direction):
        other = index + direction
        if 0 <= other < len(self.template["targets"]):
            def swap():
                targets = self.template["targets"]
                targets[index], targets[other] = targets[other], targets[index]
            self.mutate(swap)

    def remove_target(self, index):
        self.mutate(lambda: self.template["targets"].pop(index))

    def pick(self, multiple=False):
        picker = ConnectionPicker(self, all_connections(self.app), multiple)
        self.wait_window(picker)
        self.grab_set()
        return picker.result

    def replace_target(self, index):
        selected = self.pick()
        if selected:
            def change():
                self.template["targets"][index].update(key=selected[0].key, label=selected[0].display_name)
            self.mutate(change)

    def add_targets(self):
        selected = self.pick(multiple=True)
        if selected:
            def add():
                known = {t["key"] for t in self.template["targets"]}
                self.template["targets"].extend(t for t in new_template(selected)["targets"] if t["key"] not in known)
            self.mutate(add)

    def browse(self, index):
        target = self.template["targets"][index]
        user, checks = self.rows[index]
        matches = [s for s in all_connections(self.app) if s.key == target["key"]]
        if len(matches) != 1 or not user.get().strip():
            messagebox.showwarning("Servicebrowser", "Zuerst eindeutige aktuelle Verbindung und Benutzer festlegen.", parent=self)
            return
        session = matches[0]
        def apply(names):
            existing = {unit.get() for _, unit, _ in checks.fields}
            for name in names:
                if name not in existing:
                    checks.add(name)
            self._bind_scroll(checks)
        picker = ServicePicker(self, session, user.get().strip(), apply)
        self.wait_window(picker)
        self.grab_set()

    def persist(self, library):
        from .actions_ui import persist_ui_state
        library = validate_library(library)
        store = self.app._initial_toolbar_search_texts
        old = store.get("restart_templates")
        store["restart_templates"] = deepcopy(library)
        try:
            persist_ui_state(self.app)
        except (OSError, ValueError):
            if old is None:
                store.pop("restart_templates", None)
            else:
                store["restart_templates"] = old
            raise
        self.library = library
        self.refresh_library()

    def save(self):
        try:
            item = validate_template(self.collect())
            if item == self.original:
                return True
            if self.original is not None:
                choice = SaveTemplateChoice(self, item["name"])
                self.wait_window(choice)
                self.grab_set()
                if choice.result is None:
                    return False
                mode, name = choice.result
                if mode == "new":
                    item["id"], item["name"] = uuid.uuid4().hex, name
            library = deepcopy(self.library)
            library["items"] = [i for i in library["items"] if i["id"] != item["id"]] + [item]
            self.persist(library)
            self.template = deepcopy(next(i for i in self.library["items"] if i["id"] == item["id"]))
            self.original = deepcopy(self.template)
            self.name.set(self.template["name"])
            self.status.set("Vorlage gespeichert.")
            return True
        except (ValueError, OSError) as error:
            messagebox.showerror("Vorlage nicht gespeichert", str(error), parent=self)
            return False

    def delete_template(self):
        selected = self.list.selection()
        if not selected or not messagebox.askyesno("Vorlage löschen", "Diese Neustart-Vorlage wirklich löschen?", parent=self):
            return
        try:
            library = deepcopy(self.library)
            library["items"] = [i for i in library["items"] if i["id"] != selected[0]]
            self.persist(library)
            if self.template and self.template["id"] == selected[0]:
                self.template = self.original = None
                for child in self.editor.winfo_children():
                    child.destroy()
        except (ValueError, OSError) as error:
            messagebox.showerror("Löschen fehlgeschlagen", str(error), parent=self)

    def preview(self):
        if not self.save():
            return
        try:
            template = validate_template(self.template, runnable=True)
            targets = resolve_targets(template, all_connections(self.app))
            fingerprint = target_fingerprint(targets)
        except ValueError as error:
            messagebox.showwarning("Vorlage prüfen", str(error), parent=self)
            return
        preview = RestartPreview(self, template, targets)
        self.wait_window(preview)
        self.grab_set()
        if preview.result is None:
            return
        password, preview.result = preview.result, None
        try:
            current = resolve_targets(template, all_connections(self.app))
            if target_fingerprint(current) != fingerprint:
                raise ValueError("Verbindungsdaten haben sich geändert. Bitte Vorschau erneut öffnen und prüfen.")
            from .actions_restart_templates import run_template
            run_template(self.app, template, current, password)
        except ValueError as error:
            messagebox.showwarning("Neustart nicht gestartet", str(error), parent=self)
        finally:
            password = ""
            self.grab_set()
