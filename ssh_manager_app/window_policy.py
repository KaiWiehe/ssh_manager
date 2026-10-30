"""Independent app windows and confirmation dialogs without Tk/OS modality.

Waiting for an answer still pumps Tk events, so the main window stays usable.
No tkinter module is patched: callers explicitly import the local adapters.
"""
from __future__ import annotations

from functools import wraps
from inspect import signature

import tkinter as tk
from tkinter import ttk


class AppWindow(tk.Toplevel):
    """A normal owned window; activate once on first mapping, never pin it."""

    activate_on_open = True

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._activated_once = False
        self.bind("<Map>", self._activate_once, add="+")

    def _activate_once(self, event):
        if event.widget is not self or self._activated_once:
            return
        self._activated_once = True
        if self.activate_on_open:
            # Respect an entry already selected by the dialog's constructor.
            focused = self.focus_get()
            if focused is None or focused.winfo_toplevel() is not self:
                self.focus_set()


def _exists(widget):
    try:
        return widget is not None and bool(widget.winfo_exists())
    except tk.TclError:
        return False


class AnswerDialog(AppWindow):
    """A locally awaited question with conservative cancel/close semantics."""

    _blocks_app_shortcuts = True

    def __init__(self, parent, title, message, choices, *, initialvalue=None,
                 show=None, default=None):
        super().__init__(parent)
        self.result = None
        self.title(title or "SSH Manager")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=message or "", wraplength=640, justify="left").pack(fill="x")
        self.entry = None
        if initialvalue is not None:
            self.value = tk.StringVar(self, value=initialvalue)
            self.entry = ttk.Entry(body, textvariable=self.value, width=55,
                                   show=show or "")
            self.entry.pack(fill="x", pady=(14, 0))
            self.entry.selection_range(0, "end")
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(20, 0))
        self.buttons = {}
        for label, value in choices:
            button = ttk.Button(buttons, text=label,
                                command=lambda answer=value: self.choose(answer))
            button.pack(side="left", padx=(0, 8))
            self.buttons[value] = button
        default_button = self.buttons.get(default)
        if self.entry is not None:
            self.entry.focus_set()
            self.bind("<Return>", lambda _event: self.choose("input"))
        elif default_button is not None:
            default_button.focus_set()
            self.bind("<Return>", lambda _event: self.choose(default))
        self.update_idletasks()
        if _exists(parent):
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_reqwidth()) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_reqheight()) // 2)
            self.geometry(f"+{x}+{y}")

    def choose(self, answer):
        self.result = self.value.get() if answer == "input" else answer
        self.destroy()


_pending = {}


def _ask(title, message, choices, *, parent=None, cancel=None, default=None,
         initialvalue=None, show=None, **_options):
    parent = parent or tk._default_root
    if not _exists(parent):
        return cancel
    # A second click on the same initiating command cannot stack confirmations
    # or authorize a second execution while its first question is pending.
    key = (str(parent), title, message)
    if key in _pending:
        return cancel
    dialog = AnswerDialog(parent, title, message, choices, initialvalue=initialvalue,
                          show=show, default=default)
    _pending[key] = dialog
    try:
        dialog.wait_window()
        return dialog.result if _exists(parent) and dialog.result is not None else cancel
    finally:
        _pending.pop(key, None)


class _Messages:
    def showinfo(self, title=None, message=None, **options):
        return _ask(title, message, [("OK", "ok")], cancel="ok", default="ok", **options)

    showwarning = showinfo
    showerror = showinfo

    def askyesno(self, title=None, message=None, **options):
        return _ask(title, message, [("Ja", True), ("Nein", False)], cancel=False,
                    default=options.pop("default", False), **options)

    def askyesnocancel(self, title=None, message=None, **options):
        return _ask(title, message, [("Ja", True), ("Nein", False), ("Abbrechen", None)],
                    default=options.pop("default", None), **options)


class _Inputs:
    def askstring(self, title, prompt, **options):
        return _ask(title, prompt, [("OK", "input"), ("Abbrechen", None)],
                    initialvalue=options.pop("initialvalue", ""), **options)


messagebox = _Messages()
simpledialog = _Inputs()


def owner_alive(owner):
    """Allow lightweight action owners in tests; real Tk owners must exist."""
    return not hasattr(owner, "winfo_exists") or _exists(owner)


def wait_for_window(owner, dialog):
    try:
        owner.wait_window(dialog)
    except tk.TclError:
        if owner_alive(owner):
            raise
    return owner_alive(owner)


def single_pending(action):
    """Suppress repeated input/start for the same command and resource only."""
    action_signature = signature(action)
    @wraps(action)
    def perform(owner, *args, **kwargs):
        def resource(value):
            if hasattr(value, "key"):
                return value.key
            if isinstance(value, (list, tuple)):
                return tuple(sorted(str(resource(item)) for item in value))
            return str(value)
        bound = action_signature.bind(owner, *args, **kwargs)
        bound.apply_defaults()
        key = (action.__module__, action.__qualname__,
               tuple((name, resource(value)) for name, value in list(bound.arguments.items())[1:]))
        pending = owner.__dict__.setdefault("_pending_actions", set())
        if key in pending or not owner_alive(owner):
            return None
        pending.add(key)
        try:
            return action(owner, *args, **kwargs)
        finally:
            pending.discard(key)
    return perform
