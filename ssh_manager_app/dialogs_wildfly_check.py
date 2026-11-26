"""Configure and test one WildFly instance for a restart-template service."""
from __future__ import annotations

from threading import Event
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .ui_components import fit_window_to_parent
from .wildfly_deployments import validate_wildfly_settings
from .window_policy import AppWindow
from .workers import run_worker


class WildFlyCheckDialog(AppWindow):
    _blocks_app_shortcuts = True

    def __init__(self, parent, unit, existing, make_probe):
        super().__init__(parent)
        self.saved = False
        self.result = None
        self.cancel = Event()
        self.running = False
        self.make_probe = make_probe
        existing = existing or {}
        self.title("WildFly-Deployment-Prüfung")
        self.bind("<Escape>", lambda _: self.destroy())
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(9, weight=1)
        ttk.Label(body, text=unit, style="DialogTitle.TLabel").grid(row=0, columnspan=2, sticky="w", pady=(0, 7))
        self.enabled = tk.BooleanVar(self, value=True)
        self.enable_button = ttk.Checkbutton(body, text="WildFly-Deployments prüfen", variable=self.enabled,
                                             command=self.update_controls)
        self.enable_button.grid(row=1, columnspan=2, sticky="w", pady=(0, 6))
        self.inputs = []
        self.fields = {}
        for row, (key, caption, default) in enumerate((
            ("cli_path", "Pfad zu jboss-cli.sh", ""),
            ("base_dir", "Basisverzeichnis der Unit", ""),
            ("address", "Lokale Management-IP", "127.0.0.1"),
            ("port", "Management-Port", 9990),
        ), 2):
            ttk.Label(body, text=caption).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            value = self.fields[key] = tk.StringVar(self, value=existing.get(key, default))
            entry = ttk.Entry(body, textvariable=value)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self.inputs.append(entry)
        self.https = tk.BooleanVar(self, value=existing.get("https", False))
        transport = ttk.Checkbutton(body, text="Management über HTTPS", variable=self.https)
        transport.grid(row=6, column=1, sticky="w", pady=3)
        self.inputs.append(transport)
        self.lists = {}
        for row, (key, caption) in enumerate((
            ("expected", "Soll-Deployments\nje Zeile ein Name"),
            ("scanner_dirs", "Scanner-Verzeichnisse\nje Zeile ein Pfad"),
        ), 7):
            ttk.Label(body, text=caption).grid(row=row, column=0, sticky="nw", pady=4, padx=(0, 10))
            area = ScrolledText(body, wrap="none", height=2, width=28)
            area.grid(row=row, column=1, sticky="ew", pady=4)
            area.insert("1.0", "\n".join(existing.get(key, [])))
            self.lists[key] = area
            self.inputs.append(area)
        self.output = ScrolledText(body, wrap="word", height=5, width=40, state="disabled")
        self.output.grid(row=9, columnspan=2, sticky="nsew", pady=(6, 9))
        buttons = ttk.Frame(body)
        buttons.grid(row=10, columnspan=2, sticky="ew")
        self.test_button = ttk.Button(buttons, text="Deployment-Prüfung testen", command=self.test)
        self.test_button.pack(side="left")
        self.save_button = ttk.Button(buttons, text="Übernehmen", command=self.save)
        self.save_button.pack(side="right")
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right", padx=6)
        self.show("Bei Scanner-Verzeichnissen auch die erwarteten Deployments angeben.")
        self.update_controls()
        fit_window_to_parent(self, parent, 735, 590)

    def update_controls(self):
        enabled = self.enabled.get()
        for widget in self.inputs:
            widget.configure(state="normal" if enabled and not self.running else "disabled")
        self.test_button.configure(state="normal" if enabled and not self.running else "disabled")
        for button in (self.enable_button, self.save_button):
            button.configure(state="disabled" if self.running else "normal")

    def collect(self):
        values = {name: variable.get() for name, variable in self.fields.items()}
        try:
            values["port"] = int(values["port"])
        except ValueError:
            raise ValueError("WildFly: gültigen Management-Port angeben.") from None
        values["https"] = self.https.get()
        for name, widget in self.lists.items():
            values[name] = [line.strip() for line in widget.get("1.0", "end-1c").splitlines() if line.strip()]
        return validate_wildfly_settings(values)

    def show(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def test(self):
        if self.running or not self.enabled.get():
            return
        try:
            work = self.make_probe(self.collect())
        except ValueError as error:
            self.show(str(error))
            return
        self.running = True
        self.update_controls()
        self.show("Lesende Deployment-Abfrage läuft …")
        labels = {"ok": "Erfolgreich", "mismatch": "Abweichung", "error": "Prüfung fehlgeschlagen"}

        def finish(result):
            outcome, state, detail = result
            self.running = False
            self.update_controls()
            self.show(f"{labels[outcome]} · systemd {state}\n{detail}")

        run_worker(self, lambda: work(self.cancel), finish,
                   lambda _: finish(("error", "nicht geprüft", "Hintergrundabfrage konnte nicht abgeschlossen werden.")))

    def save(self):
        if self.running:
            return
        try:
            self.result = self.collect() if self.enabled.get() else None
        except ValueError as error:
            self.show(str(error))
            return
        self.saved = True
        self.destroy()

    def destroy(self):
        self.cancel.set()
        super().destroy()
