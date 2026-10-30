"""Editable restart tables, saved templates and read-only per-host service browsing."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import tkinter as tk
from .window_policy import AppWindow, single_pending
from tkinter import ttk
from .window_policy import messagebox
import uuid

from .restart_templates import (all_connections, new_template, resolve_targets, service_check,
                                target_fingerprint, validate_library, validate_template, MODE_LABELS)
from .ui_components import fit_window_to_parent, install_context_help
from .workers import run_worker
from .restart_passwords import seal, unseal, passwords_for_run


def modal(window, parent, title, width=820, height=520, *, blocking=True):
    """Legacy layout helper; every window is now independently usable."""
    window.title(title)
    fit_window_to_parent(window, parent, width, height)


class SaveTemplateChoice(AppWindow):
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


class ConnectionPicker(AppWindow):
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


class ServicePicker(AppWindow):
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
                   self.load_failed)

    def load_failed(self, error):
        from .ssh_failures import SshQueryError
        detail = str(error) if isinstance(error, SshQueryError) else "Dienste konnten nicht gelesen werden. SSH-Benutzer, Zugang und systemd prüfen."
        self.status.set(detail)
        messagebox.showerror("Dienste nicht gelesen", detail, parent=self)

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
    """Service names come exclusively from the server browser."""
    def __init__(self, parent, checks, on_browse):
        super().__init__(parent)
        self.fields = []
        self.on_browse = on_browse
        self.columnconfigure(0, weight=1)
        self.addrow = ttk.Button(self, text="Dienste auswählen…", command=on_browse)
        self.addrow.grid(row=0, column=0, sticky="ew", pady=3)
        for check in checks:
            self.add(check["unit"], check["expected"])

    def add(self, name, expected="active"):
        row = ttk.Frame(self)
        row.grid(row=len(self.fields), column=0, sticky="ew", pady=2)
        row.columnconfigure(0, weight=1)
        unit, want = tk.StringVar(value=name), tk.StringVar(value="aktiv" if expected == "active" else "inaktiv")
        label = ttk.Label(row, textvariable=unit, width=25, cursor="hand2", padding=(4, 5))
        label.grid(row=0, column=0, sticky="ew")
        label.bind("<Button-1>", lambda _: self.on_browse())
        ttk.Combobox(row, textvariable=want, values=("aktiv", "inaktiv"), state="readonly", width=7).grid(row=0, column=1, padx=4)
        field = (row, unit, want)
        ttk.Button(row, text="×", width=3, command=lambda: self.remove(field)).grid(row=0, column=2)
        self.fields.append(field)
        self.addrow.grid_configure(row=len(self.fields))

    def remove(self, field):
        self.fields.remove(field)
        field[0].destroy()
        for i, (row, _, _) in enumerate(self.fields):
            row.grid_configure(row=i)
        self.addrow.grid_configure(row=len(self.fields))

    def values(self):
        return [service_check(unit.get(), "active" if want.get() == "aktiv" else "inactive") for _, unit, want in self.fields]


class RestartPreview(AppWindow):
    def __init__(self, parent, template, targets):
        super().__init__(parent)
        self.result = None
        per_connection = template.get("password_per_connection", False)
        self.password = tk.StringVar(value="" if per_connection else unseal(template.get("password_protected", "")))
        self._password_var = self.password
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=template["name"], style="DialogTitle.TLabel").pack(anchor="w")
        mode = (MODE_LABELS[template["mode"]] if template["mode"] != "parallel"
                else f"maximal {template['max_parallel']} gleichzeitig")
        policy = {"pause": "pausieren und nachfragen", "stop": "weitere Neustarts stoppen", "continue": "weiterlaufen"}[template["on_error"]]
        admission = f"{len(targets)} Server · {mode}" + (" · ohne Fehlerpause" if template["mode"] == "all_parallel" else f" · Bei Fehlern: {policy}")
        ttk.Label(frame, text=admission + "\n"
                  f"Neustart/SSH: {template['reboot_timeout']} s · danach Services: {template['service_timeout']} s", wraplength=780).pack(anchor="w", pady=8)
        from tkinter.scrolledtext import ScrolledText
        text = ScrolledText(frame, wrap="word", height=15)
        text.pack(fill="both", expand=True)
        for i, (session, user, checks) in enumerate(targets, 1):
            text.insert("end", f"{i}. {session.display_name} · {session.hostname}:{session.port} · Benutzer: {user}\n")
            if per_connection:
                stored = next(t for t in template["targets"] if t["key"] == session.key)
                text.insert("end", "    sudo-Passwort: " + ("hinterlegt" if stored.get("password_protected") else "leer (ohne Passwort)") + "\n")
            text.insert("end", "\n".join(f"    {c['unit']} → {'aktiv' if c['expected'] == 'active' else 'inaktiv'}" for c in checks) or "    Nur Neustartbestätigung und SSH")
            text.insert("end", "\n\n")
        text.configure(state="disabled")
        if per_connection:
            ttk.Label(frame, text="sudo-Passwörter je Verbindung aus der Vorlage · Leere Felder: ohne Passwort",
                      wraplength=780).pack(anchor="w", pady=(12, 4))
        else:
            ttk.Label(frame, text="Gemeinsames sudo-Passwort (Änderung hier nur für diesen Lauf):").pack(anchor="w", pady=(12, 4))
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


class RestartTemplatesDialog(AppWindow):
    def __init__(self, app, selection, *, status_only=False):
        super().__init__(app)
        self.status_only = status_only
        self.app, self.selection = app, list(selection)
        self.template = None
        self.original = None
        self.rows = []
        self.password_fields = []
        try:
            self.library = validate_library(deepcopy(app._initial_toolbar_search_texts.get("restart_templates", {"schema": 1, "items": []})))
        except ValueError as error:
            messagebox.showerror("Neustart-Vorlagen", str(error) + "\nGespeicherte Daten bleiben unverändert.", parent=app)
            self.destroy()
            return
        install_context_help(self, "restart_templates")
        self.notebook = ttk.Notebook(self, style="Restart.TNotebook")
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
        modal(self, app, "Massendienststatus" if status_only else "Massen-Neustarts", 1150, 800, blocking=False)
        if selection:
            self.create(selection)
        else:
            ttk.Label(self.editor, text="Eine Vorlage öffnen oder aus ausgewählten Servern erstellen.").pack(pady=30)

    def _build_library(self):
        ttk.Label(self.library_frame, text="Gemeinsame Vorlagen für Neustarts und Dienststatus öffnen.", style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 10))
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
                values=(len(item["targets"]), MODE_LABELS[item["mode"]]))

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

    def clear_passwords(self):
        for variable in getattr(self, "password_fields", []):
            variable.set("")
        if hasattr(self, "common_password"):
            self.common_password.set("")

    def destroy(self):
        self.clear_passwords()
        super().destroy()

    def create(self, selection=None):
        selected = list(selection) if selection is not None else self.app._tree.get_selected_sessions()
        if not selected:
            messagebox.showinfo("Server auswählen", "Links im Hauptfenster Server anhaken und Massen-Neustarts erneut öffnen. Alternativ eine gespeicherte Vorlage öffnen.", parent=self)
            return
        if self.discard_ok():
            self.load(new_template(selected), existing=False)

    def open_selected(self):
        selected = self.list.selection()
        if selected and self.discard_ok():
            try:
                self.library = self.current_library()
                current = next((i for i in self.library["items"] if i["id"] == selected[0]), None)
                self.refresh_library()
                if current is None:
                    raise ValueError("Vorlage wurde in einem anderen Fenster gelöscht.")
                self.load(current)
            except ValueError as error:
                messagebox.showwarning("Vorlage neu öffnen", str(error), parent=self)

    def load(self, template, existing=True):
        self.template = deepcopy(template)
        self.original = deepcopy(template) if existing else None
        self.build_editor()
        self.notebook.select(self.editor)

    def build_editor(self):
        self.clear_passwords()
        for child in self.editor.winfo_children():
            child.destroy()
        self.rows = []
        self.password_fields = []
        self.password_widgets = []
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
        passwords = ttk.Frame(self.editor)
        if not self.status_only:
            passwords.pack(fill="x", pady=(0, 10))
        self.password_per_connection = tk.BooleanVar(value=self.template.get("password_per_connection", False))
        ttk.Checkbutton(passwords, text="Passwort je Verbindung", variable=self.password_per_connection,
                        command=self.toggle_password_mode).pack(side="left", padx=(0, 12))
        ttk.Label(passwords, text="sudo-Passwort:").pack(side="left")
        self.common_password = self.password_variable(self.template.get("password_protected", ""))
        ttk.Entry(passwords, textvariable=self.common_password, show="•", width=22).pack(side="left", padx=8)
        self.fill_password_button = ttk.Button(passwords, text="Leere Passwörter füllen", command=self.fill_passwords)
        self.fill_password_button.pack(side="left")
        hint = ("Dienststatus: einmalige lesende Prüfung aller Dienste parallel. Keine sudo-Passwörter erforderlich."
                if self.status_only else "Passwörter werden mit der Vorlage verschlüsselt für dein Windows-Konto gespeichert. Leere Felder: ohne sudo-Passwort.")
        ttk.Label(self.editor, text=hint, style="Muted.TLabel", wraplength=1000).pack(anchor="w", pady=(0, 6))
        if self.common_password._unreadable and not self.status_only:
            ttk.Label(self.editor, text="Gemeinsames Passwort nicht lesbar – neu eingeben oder Feld bearbeiten, um es zu leeren.",
                      style="Error.TLabel").pack(anchor="w")
        ttk.Label(self.editor, text="Dienste per Klick auswählen · Sollzustand je Dienst wählen · Durchsuchen liest nur diesen Server",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        scroll = ttk.Frame(self.editor)
        scroll.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(scroll, highlightthickness=0, yscrollincrement=1)
        vertical = ttk.Scrollbar(scroll, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(scroll, orient="horizontal", command=self.canvas.xview)
        vertical.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table = ttk.Frame(self.canvas)
        window = self.canvas.create_window((0, 0), window=table, anchor="nw")
        # Coalesce geometry bursts and avoid configuring an unchanged window width.
        canvas = self.canvas
        pending_fit = None
        def fit_table():
            nonlocal pending_fit
            pending_fit = None
            width = max(canvas.winfo_width(), table.winfo_reqwidth())
            if int(float(canvas.itemcget(window, "width"))) != width:
                canvas.itemconfigure(window, width=width)
            canvas.configure(scrollregion=canvas.bbox("all"))
        def schedule_fit(_event=None):
            nonlocal pending_fit
            if pending_fit is None:
                pending_fit = canvas.after_idle(fit_table)
        def cleanup_fit(event):
            if event.widget is canvas and pending_fit is not None:
                canvas.after_cancel(pending_fit)
        canvas.bind("<Destroy>", cleanup_fit)
        table.bind("<Configure>", schedule_fit)
        canvas.bind("<Configure>", schedule_fit)
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
            details = f"{session.hostname}:{session.port}" if session else "Verbindung mehrdeutig – entfernen und neu hinzufügen" if matches else "Verbindung fehlt – entfernen und neu hinzufügen"
            server = ttk.Frame(table, padding=(6, 8))
            server.grid(row=i*2+1, column=0, sticky="nw")
            ttk.Label(server, text=f"{i+1}. {label}").pack(anchor="w")
            ttk.Label(server, text=details, wraplength=220, style="Muted.TLabel" if session else "Error.TLabel").pack(anchor="w")
            user = tk.StringVar(value=target["user"])
            credentials = ttk.Frame(table)
            credentials.grid(row=i*2+1, column=1, sticky="new", padx=6, pady=8)
            ttk.Combobox(credentials, textvariable=user, values=list(self.app.settings.quick_users), width=18).pack(fill="x")
            password = self.password_variable(target.get("password_protected", ""))
            self.password_fields.append(password)
            password_frame = ttk.Frame(credentials)
            password_frame.pack(fill="x", pady=(6, 0))
            ttk.Label(password_frame, text="sudo-Passwort" + (" · nicht lesbar" if password._unreadable else ""),
                      style="Error.TLabel" if password._unreadable else "Muted.TLabel").pack(anchor="w")
            ttk.Entry(password_frame, textvariable=password, show="•", width=18).pack(fill="x")
            self.password_widgets.append(password_frame)
            checks = ServiceChecks(table, target["checks"], lambda index=i: self.browse(index))
            checks.grid(row=i*2+1, column=2, sticky="new", padx=6, pady=6)
            actions = ttk.Frame(table, padding=4)
            actions.grid(row=i*2+1, column=3, sticky="ne")
            ttk.Button(actions, text="Server entfernen", command=lambda index=i: self.remove_target(index)).grid(row=0, column=0, sticky="ew", pady=3)
            if i < len(self.template["targets"]) - 1:
                ttk.Frame(table, height=1, style="RestartDivider.TFrame").grid(row=i*2+2, column=0, columnspan=4, sticky="ew", pady=5)
            self.rows.append((user, checks))
        self._bind_scroll(self.canvas)
        self.toggle_password_mode()
        options = ttk.LabelFrame(self.editor, text="Ablauf", padding=8)
        if not self.status_only:
            options.pack(fill="x", pady=10)
        self.options = {}
        self.option_widgets = {}
        fields = (("mode", "Ablauf", tuple(MODE_LABELS.values())), ("max_parallel", "Max. gleichzeitig", None),
                  ("on_error", "Bei Fehlern", ("pausieren und nachfragen", "weitere stoppen", "weiterlaufen")),
                  ("reboot_timeout", "Neustart / SSH (s)", None), ("service_timeout", "Danach Services (s)", None))
        for col, (key, title, values) in enumerate(fields):
            options.columnconfigure(col, weight=1)
            ttk.Label(options, text=title).grid(row=0, column=col, sticky="w", padx=4)
            value = self.template[key]
            if key == "mode":
                value = MODE_LABELS[value]
            if key == "on_error":
                value = {"pause": "pausieren und nachfragen", "stop": "weitere stoppen", "continue": "weiterlaufen"}[value]
            var = tk.StringVar(value=str(value))
            self.options[key] = var
            if values:
                widget = ttk.Combobox(options, textvariable=var, values=values, state="readonly", width=23 if key == "on_error" else 27)
            else:
                widget = ttk.Spinbox(options, textvariable=var, from_=1, to=128 if key == "max_parallel" else 3600, width=7)
            widget.grid(row=1, column=col, sticky="ew", padx=4, pady=4)
            self.option_widgets[key] = widget
        self.options["mode"].trace_add("write", lambda *_: self.update_execution_mode())
        self.update_execution_mode()
        footer = ttk.Frame(self.editor)
        footer.pack(fill="x")
        ttk.Button(footer, text="Speichern…", command=self.save).pack(side="right", padx=6)
        if not self.status_only:
            ttk.Button(footer, text="Vorschau und starten…", command=self.preview, style="Accent.TButton").pack(side="right")
        ttk.Button(footer, text="Dienststatus prüfen", command=self.check_status,
                   style="Accent.TButton" if self.status_only else "TButton").pack(side="left")

    def update_execution_mode(self):
        mode = self.options["mode"].get()
        self.option_widgets["max_parallel"].configure(state="normal" if mode == MODE_LABELS["parallel"] else "disabled")
        self.option_widgets["on_error"].configure(state="disabled" if mode == MODE_LABELS["all_parallel"] else "readonly")

    def _bind_scroll(self, widget):
        # One binding tag per canvas: adding services never duplicates callbacks.
        tag = "RestartWheel" + str(self.canvas)
        if not self.canvas.bind_class(tag, "<MouseWheel>"):
            canvas = self.canvas
            pending = None
            pixels = 0.0
            def flush():
                nonlocal pending, pixels
                pending = None
                step = int(pixels)
                pixels -= step
                canvas.yview_scroll(step, "units")
            def wheel(event):
                nonlocal pending, pixels
                pixels -= event.delta * 48 / 120
                if pending is None:
                    pending = canvas.after(16, flush)
                return "break"
            binding = canvas.bind_class(tag, "<MouseWheel>", wheel)
            def cleanup(event):
                if event.widget is canvas:
                    if pending is not None:
                        canvas.after_cancel(pending)
                    canvas.unbind_class(tag, "<MouseWheel>")
                    canvas._root().deletecommand(binding)
            canvas.bind("<Destroy>", cleanup, add="+")
        tags = widget.bindtags()
        if tag not in tags:
            widget.bindtags((tag,) + tags)
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

    def password_variable(self, protected):
        try:
            value, unreadable = ("" if self.status_only else unseal(protected)), False
        except ValueError:
            value, unreadable = "", True
        variable = tk.StringVar(self, value=value)
        variable._sealed, variable._unreadable, variable._edited = protected, unreadable, False
        variable._readonly = self.status_only
        variable.trace_add("write", lambda *_: setattr(variable, "_edited", True))
        return variable

    @staticmethod
    def collect_password(variable):
        if variable._readonly:
            return variable._sealed
        if variable._unreadable and not variable._edited:
            return variable._sealed  # Never silently erase an unreadable imported credential.
        variable._sealed = seal(variable.get(), variable._sealed)
        variable._unreadable = False
        return variable._sealed

    def toggle_password_mode(self):
        enabled = self.password_per_connection.get() and not self.status_only
        for widget in self.password_widgets:
            if enabled:
                widget.pack(fill="x", pady=(6, 0))
            else:
                widget.pack_forget()
        self.fill_password_button.configure(state="normal" if enabled else "disabled")

    def fill_passwords(self):
        if not self.password_per_connection.get():
            return
        if self.common_password._unreadable and not self.common_password._edited:
            messagebox.showwarning("Passwort", "Gemeinsames Passwort nicht lesbar. Bitte neu eingeben.", parent=self)
            return
        password = self.common_password.get()
        for variable in self.password_fields:
            if not variable.get() and not (variable._unreadable and not variable._edited):
                variable.set(password)

    def collect(self):
        item = deepcopy(self.template)
        item["name"] = self.name.get().strip()
        item["password_per_connection"] = self.password_per_connection.get()
        item["password_protected"] = self.collect_password(self.common_password)
        for target, password in zip(item["targets"], self.password_fields):
            target["password_protected"] = self.collect_password(password)
        for target, (user, checks) in zip(item["targets"], self.rows):
            target["user"], target["checks"] = user.get().strip(), checks.values()
        item["mode"] = next(key for key, label in MODE_LABELS.items() if label == self.options["mode"].get())
        item["on_error"] = {"pausieren und nachfragen": "pause", "weitere stoppen": "stop", "weiterlaufen": "continue"}[self.options["on_error"].get()]
        for key in ("max_parallel", "reboot_timeout", "service_timeout"):
            if key == "max_parallel" and item["mode"] != "parallel":
                try:
                    value = int(self.options[key].get())
                    if 1 <= value <= 128:
                        item[key] = value
                except ValueError:
                    pass  # Disabled fields do not block the selected mode.
                continue
            try:
                item[key] = int(self.options[key].get())
            except ValueError as error:
                raise ValueError("Parallelität und Wartezeiten müssen ganze Zahlen sein.") from error
        return item

    @single_pending
    def check_status(self):
        if not self.save():
            return
        try:
            template = validate_template(self.template, runnable=True)
            targets = resolve_targets(template, all_connections(self.app))
            from .service_status import run_service_status
            run_service_status(self.app, template["name"], targets, max_parallel=0)
        except ValueError as error:
            messagebox.showwarning("Dienststatus nicht gestartet", str(error), parent=self)

    def mutate(self, callback):
        try:
            self.template = self.collect()
        except ValueError as error:
            messagebox.showwarning("Vorlage", str(error), parent=self)
            return
        position = self.canvas.yview()[0]
        callback()
        self.build_editor()
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(position)

    def remove_target(self, index):
        self.mutate(lambda: self.template["targets"].pop(index))

    def pick(self, multiple=False):
        picker = ConnectionPicker(self, all_connections(self.app), multiple)
        self.wait_window(picker)
        return picker.result

    @single_pending
    def add_targets(self):
        selected = self.pick(multiple=True)
        if selected:
            def add():
                known = {t["key"] for t in self.template["targets"]}
                self.template["targets"].extend(t for t in new_template(selected)["targets"] if t["key"] not in known)
            self.mutate(add)

    @single_pending
    def browse(self, index):
        target = self.template["targets"][index]
        user, checks = self.rows[index]
        matches = [s for s in all_connections(self.app) if s.key == target["key"]]
        if len(matches) != 1 or not user.get().strip():
            messagebox.showwarning("Servicebrowser", "Zuerst eindeutige aktuelle Verbindung und Benutzer festlegen.", parent=self)
            return
        session = matches[0]
        requested_user = user.get().strip()
        def apply(names):
            if not checks.winfo_exists() or user.get().strip() != requested_user:
                messagebox.showwarning("Dienstauswahl verworfen", "Vorlage, Server oder Benutzer wurde während der Abfrage geändert. Bitte Dienste erneut auswählen.", parent=self)
                return
            existing = {unit.get() for _, unit, _ in checks.fields}
            for name in names:
                if name not in existing:
                    checks.add(name)
            self._bind_scroll(checks)
        picker = ServicePicker(self, session, user.get().strip(), apply)
        self.wait_window(picker)

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

    def current_library(self):
        return validate_library(deepcopy(self.app._initial_toolbar_search_texts.get("restart_templates", {"schema": 1, "items": []})))

    @single_pending
    def save(self):
        try:
            baseline = deepcopy(self.original)
            library = self.current_library()
            if self.original is not None:
                current = next((i for i in library["items"] if i["id"] == self.original["id"]), None)
                if current != self.original:
                    raise ValueError("Vorlage wurde in einem anderen Fenster geändert oder gelöscht. Bitte unter Vorlagen erneut öffnen; lokale Änderungen zuvor bei Bedarf separat übernehmen.")
            item = validate_template(self.collect())
            editor_item = deepcopy(item)
            if item == self.original:
                return True
            if self.original is not None:
                choice = SaveTemplateChoice(self, item["name"])
                self.wait_window(choice)
                if choice.result is None:
                    return False
                mode, name = choice.result
                if mode == "new":
                    item["id"], item["name"] = uuid.uuid4().hex, name
            # The save-choice window does not block any other manager. Merge
            # against the current library only after that question has closed.
            if not self.winfo_exists():
                return False
            if self.original != baseline or validate_template(self.collect()) != editor_item:
                raise ValueError("Der Editor wurde während der Speicherauswahl geändert. Bitte die aktuelle Vorlage erneut speichern.")
            library = self.current_library()
            if self.original is not None:
                current = next((i for i in library["items"] if i["id"] == self.original["id"]), None)
                if current != self.original:
                    raise ValueError("Vorlage wurde in einem anderen Fenster geändert oder gelöscht. Bitte unter Vorlagen erneut öffnen.")
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

    @single_pending
    def delete_template(self):
        selected = self.list.selection()
        if not selected:
            return
        try:
            baseline = deepcopy(next((i for i in self.current_library()["items"] if i["id"] == selected[0]), None))
            if baseline is None or not messagebox.askyesno("Vorlage löschen", "Diese Neustart-Vorlage wirklich löschen?", parent=self):
                return
            if not self.winfo_exists():
                return
            library = self.current_library()
            current = next((i for i in library["items"] if i["id"] == selected[0]), None)
            if self.list.selection() != selected or current != baseline:
                raise ValueError("Auswahl oder Vorlage wurde während der Rückfrage geändert. Bitte erneut öffnen.")
            library["items"] = [i for i in library["items"] if i["id"] != selected[0]]
            self.persist(library)
            if self.template and self.template["id"] == selected[0]:
                self.template = self.original = None
                self.clear_passwords()
                for child in self.editor.winfo_children():
                    child.destroy()
        except (ValueError, OSError) as error:
            messagebox.showerror("Löschen fehlgeschlagen", str(error), parent=self)

    @single_pending
    def preview(self):
        if not self.save():
            return
        try:
            template = validate_template(self.template, runnable=True)
            targets = resolve_targets(template, all_connections(self.app))
            passwords_for_run(template, targets, unseal(template.get("password_protected", ""))
                              if not template.get("password_per_connection", False) else "")
            fingerprint = target_fingerprint(targets)
        except ValueError as error:
            messagebox.showwarning("Vorlage prüfen", str(error), parent=self)
            return
        preview = RestartPreview(self, template, targets)
        self.wait_window(preview)
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
