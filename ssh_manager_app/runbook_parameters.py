from __future__ import annotations

from copy import deepcopy
import re
import shlex
import tkinter as tk
from tkinter import ttk, messagebox

from .ui_components import install_context_help, fit_window_to_parent

PARAMETER_TYPES = ("text", "integer", "port", "path", "choice")


def validate_definitions(parameters):
    if not isinstance(parameters, list) or len(parameters) > 20:
        raise ValueError("Maximal 20 Parameter pro Runbook.")
    seen = set()
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise ValueError("Ungültiger Parameter.")
        name = parameter.get("name", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", name) or name in seen:
            raise ValueError("Variablennamen: eindeutige Großbuchstaben, Ziffern und Unterstriche.")
        seen.add(name)
        if parameter.get("type", "text") not in PARAMETER_TYPES:
            raise ValueError("Unbekannter Parametertyp.")
        for key in ("label", "default"):
            if not isinstance(parameter.get(key, ""), str):
                raise ValueError("Beschriftung und Standardwert müssen Text sein.")
        if parameter.get("secret") and parameter.get("default"):
            raise ValueError("Geheimfelder dürfen keinen gespeicherten Standardwert haben.")
        for key in ("required", "secret"):
            if key in parameter and not isinstance(parameter[key], bool):
                raise ValueError("Pflichtfeld und Geheimfeld müssen Ja/Nein sein.")
        if parameter.get("secret") and parameter.get("type") == "choice":
            raise ValueError("Geheimwerte als Eingabefeld definieren, nicht als gespeicherte Auswahl.")
        choices = parameter.get("choices", [])
        if not isinstance(choices, list) or not all(isinstance(v, str) for v in choices):
            raise ValueError("Ungültige Auswahlwerte.")
        if parameter.get("type") == "choice" and not choices:
            raise ValueError("Mindestens einen Auswahlwert angeben.")


def validate_values(parameters, values):
    validate_definitions(parameters)
    if not isinstance(values, dict) or set(values) != {p["name"] for p in parameters}:
        raise ValueError("Parameter fehlen oder sind unbekannt.")
    for parameter in parameters:
        value = values[parameter["name"]]
        if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
            raise ValueError("Parameterwert ungültig oder zu lang.")
        if not value:
            if parameter.get("required", True):
                raise ValueError(f"{parameter.get('label') or parameter['name']}: Eingabe erforderlich.")
            continue
        kind = parameter.get("type", "text")
        if kind in ("integer", "port") and not re.fullmatch(r"-?\d+", value):
            raise ValueError("Eine ganze Zahl eingeben.")
        if kind == "port" and not 1 <= int(value) <= 65535:
            raise ValueError("Port muss zwischen 1 und 65535 liegen.")
        if kind == "path" and (not value.startswith("/") or "\n" in value or "\r" in value):
            raise ValueError("Einen absoluten Linux-Pfad eingeben.")
        if kind == "choice" and value not in parameter["choices"]:
            raise ValueError("Einen vorgegebenen Auswahlwert verwenden.")


def prepare_parameter_spec(spec, values, *, redact=False):
    parameters = spec.get("parameters", [])
    validate_values(parameters, values)
    exports = []
    for parameter in parameters:
        value = "<verborgen>" if redact and parameter.get("secret") else values[parameter["name"]]
        exports.append(f"export RUNBOOK_{parameter['name']}={shlex.quote(value)}")
    updated = deepcopy(spec)
    key = "command" if spec.get("mode", "command") == "command" else "before_command"
    updated[key] = "\n".join(exports + [spec.get(key, "")])
    return updated


class RunbookParametersDialog(tk.Toplevel):
    def __init__(self, parent, parameters):
        validate_definitions(parameters)
        super().__init__(parent)
        install_context_help(self, "parameters")
        self.title("Runbook-Eingaben")
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.parameters = parameters
        self.variables = {}
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text="Eingaben gelten nur für diesen Lauf. Geheimwerte werden nicht gespeichert.", wraplength=520).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        canvas = tk.Canvas(frame, highlightthickness=0, height=300)
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        form = ttk.Frame(canvas)
        form.columnconfigure(1, weight=1)
        window = canvas.create_window(0, 0, window=form, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        form.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        for row, parameter in enumerate(parameters, 1):
            name = parameter["name"]
            self.variables[name] = tk.StringVar(value="" if parameter.get("secret") else parameter.get("default", ""))
            ttk.Label(form, text=(parameter.get("label") or name) + (" *" if parameter.get("required", True) else "")).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            if parameter.get("type") == "choice":
                field = ttk.Combobox(form, textvariable=self.variables[name], values=parameter["choices"], state="readonly")
            else:
                field = ttk.Entry(form, textvariable=self.variables[name], show="•" if parameter.get("secret") else "")
            field.grid(row=row, column=1, sticky="ew", pady=3)
            field.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Abbrechen", command=self.cancel).pack(side="left", padx=5)
        ttk.Button(actions, text="Übernehmen", command=self.confirm).pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda _: self.cancel())
        fit_window_to_parent(self, parent, 580, min(750, 150 + len(parameters) * 34))

    def clear(self):
        for variable in self.variables.values():
            variable.set("")

    def cancel(self):
        self.result = None
        self.clear()
        self.destroy()

    def confirm(self):
        values = {name: variable.get() for name, variable in self.variables.items()}
        try:
            validate_values(self.parameters, values)
        except ValueError as exc:
            messagebox.showwarning("Eingaben prüfen", str(exc), parent=self)
            return
        self.result = values
        self.clear()
        self.destroy()


class ParameterDefinitionsDialog(tk.Toplevel):
    def __init__(self, parent, parameters):
        super().__init__(parent)
        install_context_help(self, "parameters")
        self.title("Runbook-Parameter definieren")
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.parameters = deepcopy(parameters)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        self.list = tk.Listbox(frame, height=6, exportselection=False)
        self.list.pack(fill="both", expand=True)
        self.list.bind("<<ListboxSelect>>", self.load)
        form = ttk.Frame(frame)
        form.pack(fill="x", pady=8)
        form.columnconfigure(1, weight=1)
        self.fields = {}
        for row, (key, label) in enumerate((("name", "Variable (z. B. SERVICE)"), ("label", "Beschriftung"), ("type", "Typ"), ("default", "Standardwert"), ("choices", "Auswahlwerte (mit | trennen)"))):
            variable = tk.StringVar(value="text" if key == "type" else "")
            self.fields[key] = variable
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            widget = ttk.Combobox(form, textvariable=variable, values=PARAMETER_TYPES, state="readonly") if key == "type" else ttk.Entry(form, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
        self.required = tk.BooleanVar(value=True)
        self.secret = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Pflichtfeld", variable=self.required).grid(row=5, column=0, sticky="w")
        ttk.Checkbutton(form, text="Geheimwert (kein Standardwert)", variable=self.secret).grid(row=5, column=1, sticky="w")
        ttk.Label(frame, text='Im Runbook z. B. "$RUNBOOK_SERVICE" verwenden. Werte werden als Daten übergeben.', wraplength=620).pack(anchor="w", pady=5)
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        for label, command in (("Hinzufügen", lambda: self.store(False)), ("Markierten ändern", lambda: self.store(True)), ("Entfernen", self.remove), ("Speichern", self.confirm), ("Abbrechen", self.destroy)):
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 5))
        self.refresh()
        fit_window_to_parent(self, parent, 730, 520)

    def refresh(self):
        self.list.delete(0, "end")
        for parameter in self.parameters:
            self.list.insert("end", f"{parameter['name']} – {parameter.get('label', '')} ({parameter.get('type', 'text')})")

    def load(self, _event=None):
        selection = self.list.curselection()
        if not selection:
            return
        parameter = self.parameters[selection[0]]
        for key, variable in self.fields.items():
            variable.set("|".join(parameter.get("choices", [])) if key == "choices" else parameter.get(key, "text" if key == "type" else ""))
        self.required.set(parameter.get("required", True))
        self.secret.set(parameter.get("secret", False))

    def store(self, replace):
        selection = self.list.curselection()
        if replace and not selection:
            return
        parameter = {key: var.get().strip() for key, var in self.fields.items()}
        parameter["choices"] = [v.strip() for v in parameter["choices"].split("|") if v.strip()]
        parameter.update(required=self.required.get(), secret=self.secret.get())
        candidate = deepcopy(self.parameters)
        if replace:
            candidate[selection[0]] = parameter
        else:
            candidate.append(parameter)
        try:
            validate_definitions(candidate)
        except ValueError as exc:
            messagebox.showwarning("Parameter prüfen", str(exc), parent=self)
            return
        self.parameters = candidate
        self.refresh()

    def remove(self):
        selection = self.list.curselection()
        if selection:
            self.parameters.pop(selection[0])
            self.refresh()

    def confirm(self):
        self.result = deepcopy(self.parameters)
        self.destroy()
