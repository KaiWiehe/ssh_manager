"""Modeless, destination-grouped remote port checks and destination picker."""
from __future__ import annotations

from copy import deepcopy
import queue
import tkinter as tk
from .window_policy import AppWindow, single_pending
from tkinter import ttk
from .window_policy import messagebox

from .port_checks import (NEGATIVE, STATE_KEY, STATUS, PortCheckJob, ProbeResult,
                          resolve_destination, targets, validate_library)
from .restart_templates import all_connections
from .result_table import ResultTableTools
from .ui_components import fit_window_to_parent, install_context_help
from .workers import run_worker
from .dialogs_base import _build_quickselect_buttons


class DestinationPicker(AppWindow):
    def __init__(self, owner, app, accept):
        super().__init__(owner)
        self.title("Zielserver suchen")
        self.accept, self.owner = accept, owner
        self.connections = all_connections(app)
        self.query = tk.StringVar()
        self.message = tk.StringVar(value="Verbindung auswählen; der Zielport bleibt unverändert.")
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Name, Host/IP oder Ordner suchen").pack(anchor="w")
        entry = ttk.Entry(frame, textvariable=self.query)
        entry.pack(fill="x", pady=(4, 10))
        self.tree = ttk.Treeview(frame, columns=("host", "folder", "source"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Verbindung")
        self.tree.column("#0", width=190)
        for col, label in (("host", "Zielhost / IP"), ("folder", "Ordner"), ("source", "Quelle")):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=170)
        self.tree.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        ttk.Label(frame, textvariable=self.message, wraplength=730).pack(anchor="w", pady=8)
        bar = ttk.Frame(frame)
        bar.pack(fill="x")
        self.accept_button = ttk.Button(bar, text="Übernehmen", command=self.choose)
        self.accept_button.pack(side="right")
        ttk.Button(bar, text="Abbrechen", command=self.destroy).pack(side="right", padx=8)
        self.tree.bind("<Double-1>", lambda _: self.choose())
        self.tree.bind("<Return>", lambda _: self.choose())
        self.query.trace_add("write", self.refresh)
        self.refresh()
        # A picker is temporary input; the working window itself stays modeless.
        fit_window_to_parent(self, owner, 820, 430)
        entry.focus_set()

    def refresh(self, *_):
        query = self.query.get().casefold().strip()
        self.tree.delete(*self.tree.get_children())
        for index, s in enumerate(self.connections):
            if query in " ".join((s.display_name, s.hostname, s.folder_key, s.source)).casefold():
                self.tree.insert("", "end", iid=str(index), text=s.display_name,
                                 values=(s.hostname, s.folder_key, s.source))

    def choose(self):
        selected = self.tree.selection()
        if not selected or str(self.accept_button["state"]) == "disabled":
            return
        session = deepcopy(self.connections[int(selected[0])])
        self.accept_button.configure(state="disabled")
        self.message.set("Zieladresse ermitteln… (SSH-Aliase über lokale Konfiguration)")

        def done(host):
            if not self.owner.winfo_exists():
                return
            self.accept(host)
            self.destroy()

        def failed(_error):
            self.message.set("Zieladresse nicht eindeutig auswertbar. Bitte Ziel-IP/Hostname manuell eingeben.")
            self.accept_button.configure(state="normal")

        run_worker(self, lambda: resolve_destination(session), done, failed)


class PortResultTools(ResultTableTools):
    def __init__(self, dialog, parent):
        self.dialog = dialog
        super().__init__(dialog, dialog.results, parent, lambda: ())

    def snapshot(self, mode):
        dialog = self.dialog
        selected = set(dialog.results.selection())
        rows = []
        for index, (key, result) in enumerate(dialog.values.items()):
            source, destination = key
            group = dialog.group_id(destination)
            if mode == "selection" and f"r{index}" not in selected and group not in selected:
                continue
            if mode == "errors" and result.status not in NEGATIVE:
                continue
            session = dialog.run_sources[source]
            rows.append((session.display_name, session.hostname, session.folder_key, dialog.source_user(session),
                         destination[0], destination[1], STATUS[result.status], result.addresses,
                         result.checked_at, result.detail))
        return ("Quellserver", "Quellhost (SSH)", "Ordner", "Benutzer", "Ziel", "TCP-Port", "Ergebnis",
                "Aufgelöste Ziel-IP(s)", "Zeitpunkt", "Details"), rows

    def select_all(self, _event=None):
        self.tree.selection_set([child for group in self.tree.get_children() for child in self.tree.get_children(group)])
        return "break"


class PortCheckDialog(AppWindow):
    def __init__(self, app, sessions):
        super().__init__(app)
        self.app, self.sources = app, deepcopy(list(sessions))
        self.title("Portfreigabe prüfen – Server → Ziel")
        self.fields, self.values, self.run_sources = [], {}, {}
        self.destinations, self.job, self.timer = (), None, None
        self.preview_timer = None
        self.is_preview = True
        self.run_timeout, self.run_user = 3, ""
        self.library = {"schema": 1, "items": []}
        raw = app._initial_toolbar_search_texts.get(STATE_KEY)
        self.library_warning = ""
        if raw is not None:
            try:
                self.library = validate_library(raw)
            except ValueError:
                self.library_warning = "Gespeicherte Portprüfvorlagen sind ungültig; vor dem Speichern prüfen."
        self.name, self.timeout = tk.StringVar(), tk.StringVar(value="3")
        self.user = tk.StringVar(value=app.settings.default_user)
        self.filter = tk.StringVar(value="Alle")
        self.status = tk.StringVar(value=self.library_warning or "Bereit. Noch keine Prüfung gestartet.")
        self.summary = tk.StringVar()
        self.edit_widgets = []
        install_context_help(self, "port_checks")
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        preset = ttk.Frame(frame)
        preset.pack(fill="x")
        ttk.Label(preset, text="Prüfvorlage").pack(side="left")
        self.presets = ttk.Combobox(preset, textvariable=self.name, values=self.template_names(), width=27)
        self.presets.configure(postcommand=self.refresh_templates)
        self.presets.pack(side="left", padx=8)
        for label, command in (("Laden", self.load_template), ("Speichern…", self.save_template), ("Löschen…", self.delete_template)):
            button = ttk.Button(preset, text=label, command=command)
            button.pack(side="left", padx=3)
            self.edit_widgets.append(button)
        self.edit_widgets.append(self.presets)
        ttk.Label(frame, text="Ziel-IP / Hostname · Jeder Quellserver prüft jede Zielzeile", style="Section.TLabel").pack(anchor="w", pady=(12, 4))
        target_area = ttk.Frame(frame)
        target_area.pack(fill="x")
        background = ttk.Style(self).lookup("TFrame", "background") or self.cget("background")
        self.canvas = tk.Canvas(target_area, height=100, highlightthickness=0, background=background, yscrollincrement=24)
        self.canvas.pack(side="left", fill="x", expand=True)
        scroll = ttk.Scrollbar(target_area, orient="vertical", command=self.canvas.yview)
        scroll.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.target_frame = ttk.Frame(self.canvas)
        embedded = self.canvas.create_window((0, 0), window=self.target_frame, anchor="nw")
        self.target_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(embedded, width=e.width))
        self.target_frame.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.bind_target_wheel(self.canvas)
        self.bind_target_wheel(self.target_frame)
        self.add_button = ttk.Button(frame, text="+ Ziel hinzufügen", command=self.add_target)
        self.add_button.pack(anchor="w", pady=5)
        self.edit_widgets.append(self.add_button)
        self.add_target()
        options = ttk.Frame(frame)
        options.pack(fill="x", pady=6)
        ttk.Label(options, text="Fallback-Benutzer").pack(side="left")
        user_entry = ttk.Entry(options, textvariable=self.user, width=16)
        user_entry.pack(side="left", padx=6)
        ttk.Label(options, text="TCP-Timeout (1–30 s)").pack(side="left", padx=(10, 0))
        timeout_entry = ttk.Spinbox(options, from_=1, to=30, textvariable=self.timeout, width=4)
        timeout_entry.pack(side="left", padx=6)
        self.edit_widgets.extend((user_entry, timeout_entry))
        ttk.Label(frame, text="Quick-Access-Benutzer", style="Muted.TLabel").pack(anchor="w")
        self.quick_users = _build_quickselect_buttons(frame, list(app.settings.quick_users), self.user)
        self.quick_users.pack(fill="x", pady=(2, 4))
        self.edit_widgets.extend(self.quick_users.winfo_children())
        self.user.trace_add("write", self.schedule_preview)
        from .parallelism import ParallelismControl
        self.parallelism = ParallelismControl(frame, unit="Quellserver")
        self.parallelism.pack(fill="x", pady=4)
        ttk.Label(frame, text="Feste Benutzer und SSH-Konfiguration haben Vorrang · Schlüssel/Agent",
                  style="Muted.TLabel").pack(anchor="w")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=8)
        ttk.Label(actions, textvariable=self.summary).pack(side="left")
        self.start_button = ttk.Button(actions, text="Prüfung starten", style="Accent.TButton", command=self.start)
        self.start_button.pack(side="right")
        self.stop_button = ttk.Button(actions, text="Abbrechen", command=self.stop, state="disabled")
        self.stop_button.pack(side="right", padx=6)
        self.retry_button = ttk.Button(actions, text="Negative erneut prüfen", command=self.retry, state="disabled")
        self.retry_button.pack(side="right", padx=6)
        self.progress = ttk.Progressbar(frame)
        self.progress.pack(fill="x", pady=(0, 5))
        filterbar = ttk.Frame(frame)
        filterbar.pack(fill="x", pady=3)
        ttk.Label(filterbar, text="Ergebnisse nach Ziel · Anzeigen:").pack(side="left")
        filterbox = ttk.Combobox(filterbar, textvariable=self.filter, state="readonly", width=19,
                                values=("Alle", "Nicht erreichbar", "Nicht geprüft", "Erreichbar"))
        self.result_filter = filterbox
        filterbox.pack(side="left", padx=8)
        filterbox.bind("<<ComboboxSelected>>", lambda _: self.render_results())
        ttk.Label(frame, textvariable=self.status, wraplength=1000).pack(anchor="w", pady=3)
        result_frame = ttk.Frame(frame)
        result_frame.pack(fill="both", expand=True)
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)
        columns = ("source", "user", "status", "ip", "time")
        self.results = ttk.Treeview(result_frame, columns=columns, show="tree headings", height=8)
        self.results.heading("#0", text="Ziel / Quellserver")
        self.results.column("#0", width=240)
        for col, title, width in (("source", "Quellhost (SSH)", 170), ("user", "Benutzer", 130), ("status", "Ergebnis", 160),
                                  ("ip", "Ziel-IP(s)", 180), ("time", "Zeitpunkt", 175)):
            self.results.heading(col, text=title)
            self.results.column(col, width=width)
        self.results.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(result_frame, command=self.results.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.results.configure(yscrollcommand=bar.set)
        horizontal = ttk.Scrollbar(result_frame, orient="horizontal", command=self.results.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.results.configure(xscrollcommand=horizontal.set)
        tools_frame = ttk.Frame(frame)
        # Reserve copy/details controls before the expanding results table.
        tools_frame.pack(side="bottom", fill="x", before=result_frame)
        self.tools = PortResultTools(self, tools_frame)
        self.tools.text.configure(height=3)
        self.bind("<Destroy>", self.on_destroy, add="+")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.update_summary()
        self.refresh_preview()
        fit_window_to_parent(self, app, 1100, 850, min_width=820, min_height=650)
        # Deliberately no transient, grab or wait_window for this working window.

    def template_names(self):
        return [item["name"] for item in self.library["items"]]

    def current_library(self):
        # Other modeless windows and backup restore may update the shared state.
        return validate_library(self.app._initial_toolbar_search_texts.get(STATE_KEY, {"schema": 1, "items": []}))

    def refresh_templates(self):
        try:
            self.library = self.current_library()
            self.presets.configure(values=self.template_names())
        except ValueError as error:
            self.status.set(str(error))

    def update_summary(self, *_):
        self.summary.set(f"{len(self.sources)} Quellserver × {len(self.fields)} Zielzeilen")

    def bind_target_wheel(self, widget):
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, self.scroll_targets, add="+")

    def scroll_targets(self, event):
        delta = getattr(event, "delta", 0)
        number = getattr(event, "num", None)
        if delta or number in (4, 5):
            steps = -max(1, abs(int(delta)) // 120) if delta > 0 or number == 4 else max(1, abs(int(delta)) // 120)
            self.canvas.yview_scroll(steps, "units")
        return "break"

    def source_user(self, session):
        if session.is_ssh_config_session:
            return session.ssh_user_override or "SSH-Konfiguration"
        return session.username or (self.user.get().strip() if self.is_preview else self.run_user)

    def schedule_preview(self, *_):
        if not hasattr(self, "results") or self.job is not None:
            return
        if self.preview_timer is not None:
            self.after_cancel(self.preview_timer)
        self.preview_timer = self.after_idle(self.refresh_preview)

    def refresh_preview(self):
        if self.preview_timer is not None:
            self.after_cancel(self.preview_timer)
            self.preview_timer = None
        if self.job is not None:
            return
        self.is_preview = True
        self.filter.set("Alle")
        self.result_filter.configure(state="disabled")
        self.run_sources = {s.key: deepcopy(s) for s in self.sources}
        planned = []
        for _, host, port in self.fields:
            try:
                destination = targets([(host.get(), port.get())])[0]
            except ValueError:
                destination = (host.get().strip() or "Ziel-IP / Hostname eingeben", port.get().strip() or "?")
            if destination not in planned:
                planned.append(destination)
        self.destinations = tuple(planned)
        self.values = {(s.key, t): ProbeResult("planned", "Vorschau – noch nicht geprüft. Erst Prüfung starten führt SSH-/TCP-Tests aus.")
                       for s in self.sources for t in planned}
        self.progress.configure(value=0)
        self.retry_button.configure(state="disabled")
        self.render_results()
        self.tools.show_selection()
        self.status.set(self.library_warning or f"Vorschau · {len(self.values)} Kombination(en) · noch nicht geprüft.")

    def add_target(self, host="", port="443"):
        if len(self.fields) >= 100:
            self.status.set("Maximal 100 Zielzeilen.")
            return
        row = ttk.Frame(self.target_frame)
        row.grid(row=len(self.fields), column=0, sticky="ew", pady=3)
        row.columnconfigure(0, weight=1)
        host_var, port_var = tk.StringVar(value=host), tk.StringVar(value=str(port))
        entry = ttk.Entry(row, textvariable=host_var)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        search = ttk.Button(row, text="Server suchen…", command=lambda: self.pick_destination(host_var))
        search.grid(row=0, column=1, padx=5)
        ttk.Label(row, text="TCP-Port").grid(row=0, column=2, padx=5)
        port_entry = ttk.Entry(row, textvariable=port_var, width=7)
        port_entry.grid(row=0, column=3, padx=5)
        field = (row, host_var, port_var)
        remove = ttk.Button(row, text="Entfernen", style="Danger.TButton", command=lambda: self.remove_target(field))
        from .ui import _decorate
        _decorate(remove, icon="trash")
        remove.grid(row=0, column=4, padx=(5, 0))
        self.fields.append(field)
        for widget in (row, *row.winfo_children()):
            self.bind_target_wheel(widget)
        host_var.trace_add("write", self.schedule_preview)
        port_var.trace_add("write", self.schedule_preview)
        self.update_summary()
        self.schedule_preview()
        return field

    def remove_target(self, field):
        self.fields.remove(field)
        field[0].destroy()
        for index, (row, _, _) in enumerate(self.fields):
            row.grid_configure(row=index)
        self.update_summary()
        self.schedule_preview()

    def pick_destination(self, host_var):
        return DestinationPicker(self, self.app, host_var.set)

    def destinations_from_fields(self):
        return targets([(h.get(), p.get()) for _, h, p in self.fields])

    def load_template(self):
        try:
            self.library = self.current_library()
        except ValueError as error:
            messagebox.showerror("Prüfvorlage", str(error), parent=self)
            return
        item = next((i for i in self.library["items"] if i["name"] == self.name.get()), None)
        if item is None:
            self.status.set("Eine gespeicherte Vorlage auswählen und Laden anklicken.")
            return
        for field in list(self.fields):
            self.remove_target(field)
        for host, port in item["targets"]:
            self.add_target(host, port)
        self.status.set("Zielliste geladen. Prüfung noch nicht gestartet.")

    def persist_library(self, items):
        library = validate_library({"schema": 1, "items": items})
        state = self.app._initial_toolbar_search_texts
        previous = state.get(STATE_KEY)
        state[STATE_KEY] = library
        try:
            from .actions_ui import persist_ui_state
            persist_ui_state(self.app)
        except (OSError, ValueError):
            if previous is None:
                state.pop(STATE_KEY, None)
            else:
                state[STATE_KEY] = previous
            raise
        self.library = library
        self.presets.configure(values=self.template_names())

    @single_pending
    def save_template(self):
        try:
            library = self.current_library()
            item = {"name": self.name.get().strip(), "targets": self.destinations_from_fields()}
            key = item["name"].casefold()
            existing = next((i for i in library["items"] if i["name"].casefold() == key), None)
            baseline = deepcopy(existing)
            validate_library({"schema": 1, "items": [item]})
            if existing and not messagebox.askyesno("Prüfvorlage überschreiben", f"„{existing['name']}“ überschreiben?", parent=self):
                return
            if not self.winfo_exists():
                return
            if item != {"name": self.name.get().strip(), "targets": self.destinations_from_fields()}:
                raise ValueError("Die Zielliste wurde während der Rückfrage geändert. Bitte erneut speichern.")
            library = self.current_library()
            current = next((i for i in library["items"] if i["name"].casefold() == key), None)
            if current != baseline:
                raise ValueError("Prüfvorlage wurde in einem anderen Fenster geändert oder gelöscht. Bitte erneut laden.")
            self.persist_library([i for i in library["items"] if i["name"].casefold() != key] + [item])
            self.status.set("Prüfvorlage gespeichert; enthält nur Ziele, keine Quellserver.")
        except (ValueError, OSError) as error:
            messagebox.showerror("Prüfvorlage", str(error), parent=self)

    @single_pending
    def delete_template(self):
        try:
            library = self.current_library()
            selected_name = self.name.get()
            selected = deepcopy(next((i for i in library["items"] if i["name"] == selected_name), None))
            if not selected or not messagebox.askyesno("Prüfvorlage löschen", f"„{selected['name']}“ löschen?", parent=self):
                return
            if not self.winfo_exists():
                return
            library = self.current_library()
            current = next((i for i in library["items"] if i["name"] == selected_name), None)
            if self.name.get() != selected_name or current != selected:
                raise ValueError("Auswahl oder Prüfvorlage wurde während der Rückfrage geändert. Bitte erneut laden.")
            self.persist_library([i for i in library["items"] if i["name"] != selected_name])
            self.name.set("")
            self.status.set("Prüfvorlage gelöscht; aktuelle Zielliste bleibt erhalten.")
        except (OSError, ValueError) as error:
            messagebox.showerror("Prüfvorlage", str(error), parent=self)

    def set_running(self, running):
        self.parallelism.set_running(running)
        for widget in self.edit_widgets:
            widget.configure(state="disabled" if running else "normal")
        for row, _, _ in self.fields:
            for widget in row.winfo_children():
                if isinstance(widget, (ttk.Button, ttk.Entry)):
                    widget.configure(state="disabled" if running else "normal")
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.retry_button.configure(state="normal" if not running and any(r.status in NEGATIVE for r in self.values.values()) else "disabled")

    def start(self):
        if self.job is not None:
            return
        try:
            destinations = self.destinations_from_fields()
            timeout = int(self.timeout.get())
            max_parallel = self.parallelism.get()
            if not 1 <= timeout <= 30:
                raise ValueError("TCP-Timeout: 1 bis 30 Sekunden.")
        except ValueError as error:
            messagebox.showwarning("Portprüfung", str(error), parent=self)
            return
        if self.preview_timer is not None:
            self.after_cancel(self.preview_timer)
            self.preview_timer = None
        self.is_preview = False
        self.result_filter.configure(state="readonly")
        self.destinations = tuple(destinations)
        self.run_sources = {s.key: deepcopy(s) for s in self.sources}
        self.run_timeout, self.run_user = timeout, self.user.get().strip()
        self.run_parallel = max_parallel
        self.values = {(s.key, t): ProbeResult("pending", "Noch nicht geprüft.") for s in self.sources for t in destinations}
        self.launch()

    def retry(self):
        pairs = {key for key, value in self.values.items() if value.status in NEGATIVE}
        if not pairs:
            return
        if not messagebox.askyesno("Negative Prüfungen wiederholen", f"{len(pairs)} negative Kombination(en) mit den ursprünglichen Zielen und Benutzern erneut prüfen?", parent=self):
            return
        for key in pairs:
            self.values[key] = ProbeResult("pending", "Erneute Prüfung ausstehend.")
        self.launch(pairs)

    def launch(self, pairs=None):
        if self.job is not None:
            return
        self.set_running(True)
        self.progress.configure(maximum=max(1, len(self.values)), value=0)
        self.status.set("Prüft von den Quellservern aus. Ein Timeout beweist keine fehlende Firewallfreigabe.")
        self.job = PortCheckJob(list(self.run_sources.values()), self.destinations, self.run_user, self.run_timeout,
                                pairs=pairs, max_parallel=self.run_parallel).start()
        self.render_results()
        self.timer = self.after(60, self.pump)

    def stop(self):
        if self.job is not None:
            self.job.cancel.set()
            self.stop_button.configure(state="disabled")
            self.status.set("Abbruch angefordert; laufende SSH-Prozesse werden beendet.")

    def pump(self):
        self.timer = None
        done = False
        for _ in range(250):
            try:
                kind, source, destination, value = self.job.events.get_nowait()
            except queue.Empty:
                break
            if kind == "done":
                done = True
                break
            self.values[(source, destination)] = value if kind == "result" else ProbeResult("running", "Prüfung läuft.")
        self.render_results()
        complete = sum(r.status not in ("pending", "running") for r in self.values.values())
        self.progress.configure(maximum=max(1, len(self.values)), value=complete)
        if done:
            cancelled = self.job.cancel.is_set()
            self.job = None
            self.set_running(False)
            self.status.set(("Abgebrochen · Teilergebnis" if cancelled else "Prüfung abgeschlossen") +
                            f" · {complete}/{len(self.values)} abgeschlossen · " +
                            f"{sum(r.status in NEGATIVE for r in self.values.values())} nicht erreichbar · " +
                            f"{sum(r.status not in NEGATIVE | {'open'} for r in self.values.values())} ohne bestätigten TCP-Test")
        else:
            self.status.set(f"{'Abbruch läuft' if self.job.cancel.is_set() else 'Prüft'} · {complete}/{len(self.values)} abgeschlossen")
            self.timer = self.after(60, self.pump)

    def group_id(self, destination):
        return f"g{self.destinations.index(destination)}"

    def render_results(self):
        opened = {iid: self.results.item(iid, "open") for iid in self.results.get_children()}
        selected = self.results.selection()
        focused = self.results.focus()
        yview = self.results.yview()
        self.results.delete(*self.results.get_children())
        mode = self.filter.get()
        if self.is_preview:
            mode = "Alle"
        for index, ((source, destination), result) in enumerate(self.values.items()):
            if (mode == "Nicht erreichbar" and result.status not in NEGATIVE
                    or mode == "Nicht geprüft" and result.status in NEGATIVE | {"open"}
                    or mode == "Erreichbar" and result.status != "open"):
                continue
            group = self.group_id(destination)
            if not self.results.exists(group):
                host, port = destination
                label = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
                self.results.insert("", "end", iid=group, text=label, open=opened.get(group, True))
            session = self.run_sources[source]
            self.results.insert(group, "end", iid=f"r{index}", text=session.display_name,
                                values=(session.hostname, self.source_user(session), STATUS[result.status], result.addresses, result.checked_at))
        self.results.selection_set([iid for iid in selected if self.results.exists(iid)])
        if focused and self.results.exists(focused):
            self.results.focus(focused)
        if yview:
            self.results.yview_moveto(yview[0])

    def on_destroy(self, event):
        if event.widget is self:
            if self.preview_timer is not None:
                self.after_cancel(self.preview_timer)
                self.preview_timer = None
            if self.job is not None:
                self.job.cancel.set()
            if self.timer is not None:
                self.after_cancel(self.timer)
                self.timer = None


def open_port_checks(app, sessions=None):
    sources = list(sessions) if sessions is not None else app._tree.get_selected_sessions()
    sources = list({s.key: s for s in sources}.values())
    if not sources:
        messagebox.showinfo("Portfreigabe prüfen", "Mindestens einen Quellserver anhaken.", parent=app)
        return
    return PortCheckDialog(app, sources)
