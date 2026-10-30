"""Per-run concurrency choice: zero means every selected target, never a hidden cap."""
import tkinter as tk
from .window_policy import AppWindow
from tkinter import ttk
from .window_policy import messagebox


def worker_count(total, limit=8):
    if type(limit) is not int or limit < 0:
        raise ValueError("Parallelität: positive ganze Zahl oder 0 für alle.")
    return max(1, min(total, limit) if limit else total)


class ParallelismControl(ttk.Frame):
    def __init__(self, parent, default=8, unit="Server"):
        super().__init__(parent)
        self.limited = tk.BooleanVar(self, value=True)
        self.value = tk.StringVar(self, value=str(default))
        self.check = ttk.Checkbutton(self, text="Parallelität begrenzen", variable=self.limited, command=self.update_state)
        self.check.pack(side="left")
        self.entry = ttk.Spinbox(self, from_=1, to=1000000, textvariable=self.value, width=6)
        self.entry.pack(side="left", padx=6)
        info = ttk.Label(self, text=f"{unit} gleichzeitig · ohne Häkchen: alle parallel", wraplength=300, justify="left")
        info.pack(side="left", fill="x", expand=True)
        self.bind("<Configure>", lambda e: info.configure(wraplength=max(100, e.width - self.check.winfo_reqwidth() - self.entry.winfo_reqwidth() - 18)))

    def update_state(self):
        self.entry.configure(state="normal" if self.limited.get() else "disabled")

    def get(self):
        if not self.limited.get():
            return 0
        try:
            value = int(self.value.get())
            if value < 1:
                raise ValueError
            return value
        except ValueError:
            raise ValueError("Parallelität: eine positive ganze Zahl eingeben oder Begrenzung ausschalten.") from None

    def set_running(self, running):
        self.check.configure(state="disabled" if running else "normal")
        self.entry.configure(state="disabled" if running or not self.limited.get() else "normal")


def choose_parallelism(parent, count, default=8, title="Prüfung starten"):
    from .ui_components import fit_window_to_parent
    window = AppWindow(parent)
    window.title(title)
    window.result = None
    body = ttk.Frame(window, padding=16)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=f"{count} Ziel(e) für diesen Lauf").pack(anchor="w", pady=(0, 10))
    control = ParallelismControl(body, default)
    control.pack(fill="x")
    def accept():
        try:
            window.result = control.get()
        except ValueError as error:
            messagebox.showwarning("Parallelität", str(error), parent=window)
            return
        window.destroy()
    actions = ttk.Frame(body)
    actions.pack(fill="x", pady=(16, 0))
    ttk.Button(actions, text="Prüfung starten", command=accept).pack(side="right")
    ttk.Button(actions, text="Abbrechen", command=window.destroy).pack(side="right", padx=8)
    window.bind("<Escape>", lambda _: window.destroy())
    fit_window_to_parent(window, parent, 700, 210)
    parent.wait_window(window)
    return window.result
