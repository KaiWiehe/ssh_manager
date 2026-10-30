"""Application file selectors which leave every other Tk window usable.

The small filedialog-compatible API deliberately uses no native modal dialog,
grab, transient ownership or repeated focus/lift calls. ``wait_window`` runs Tk's
event loop while the calling action waits for its selection.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from .window_policy import owner_alive

from .workers import run_worker


def _patterns(value):
    return tuple(value.split()) if isinstance(value, str) else tuple(value)


def _matches(name, patterns):
    return any(pattern in ("*", "*.*") or fnmatch.fnmatchcase(name.casefold(), pattern.casefold())
               for pattern in patterns)


def _target(directory, name, extension=""):
    path = Path(os.path.expandvars(name)).expanduser()
    if not path.is_absolute():
        path = directory / path
    if extension and not path.suffix and not path.is_dir():
        path = path.with_name(path.name + (extension if extension.startswith(".") else "." + extension))
    return path.absolute()


class FilePicker(tk.Toplevel):
    """Independent file browser; errors and overwrite confirmation stay inline."""

    def __init__(self, parent=None, *, save=False, multiple=False, title=None,
                 filetypes=(), initialdir=None, initialfile="", defaultextension="",
                 confirmoverwrite=True):
        # Use the root as master so closing a settings/dialog window does not
        # destroy the independent browser that was opened from it.
        master = parent._root() if parent is not None else None
        super().__init__(master)
        self.withdraw()
        self.title(title or ("Datei speichern" if save else "Datei auswählen"))
        self.geometry("760x520")
        self.minsize(520, 340)
        self.save = save
        self.multiple = multiple and not save
        self.extension = defaultextension
        self.confirmoverwrite = confirmoverwrite
        self.result = () if self.multiple else ""
        self._overwrite_path = None
        self._paths = {}
        self._listing_generation = 0
        self._loading = False
        self._types = tuple(filetypes) or (("Alle Dateien", "*"),)
        self._directory = Path(initialdir or Path.home()).expanduser().absolute()
        self.path_text = tk.StringVar(self, str(self._directory))
        self.name_text = tk.StringVar(self, initialfile)
        self.status_text = tk.StringVar(self)
        self.type_text = tk.StringVar(self)

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        nav = ttk.Frame(outer)
        nav.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        nav.columnconfigure(1, weight=1)
        ttk.Button(nav, text="↑", width=3, command=lambda: self._navigate(self._directory.parent)).grid(row=0, column=0, padx=(0, 6))
        path_entry = ttk.Entry(nav, textvariable=self.path_text)
        path_entry.grid(row=0, column=1, sticky="ew")
        path_entry.bind("<Return>", self._go_path)
        ttk.Button(nav, text="Öffnen", command=self._go_path).grid(row=0, column=2, padx=(6, 0))

        listing = ttk.Frame(outer)
        listing.grid(row=1, column=0, sticky="nsew")
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(listing, columns=("kind",), selectmode="extended" if self.multiple else "browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("kind", text="Typ")
        self.tree.column("kind", width=90, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(listing, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.tree.bind("<Double-1>", self._activate)
        self.tree.bind("<Return>", self._activate)

        form = ttk.Frame(outer)
        form.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Dateiname:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.name_entry = ttk.Entry(form, textvariable=self.name_text)
        self.name_entry.grid(row=0, column=1, sticky="ew")
        self.name_entry.bind("<Return>", self._accept)
        ttk.Label(form, text="Dateityp:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.type_box = ttk.Combobox(form, textvariable=self.type_text, state="readonly",
                                     values=[f"{label} ({' '.join(_patterns(pattern))})" for label, pattern, *_rest in self._types])
        self.type_box.grid(row=1, column=1, sticky="ew", pady=(6, 0))
        self.type_box.current(0)
        self.type_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        ttk.Label(outer, textvariable=self.status_text, wraplength=690).grid(row=3, column=0, sticky="w", pady=(8, 0))
        buttons = ttk.Frame(outer)
        buttons.grid(row=4, column=0, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="left", padx=(0, 8))
        self.accept_button = ttk.Button(buttons, text="Speichern" if save else "Auswählen", command=self._accept)
        self.accept_button.pack(side="left")
        self.name_text.trace_add("write", self._reset_confirmation)
        self.bind("<Escape>", lambda _event: self.destroy())
        self._refresh()
        self.deiconify()
        self.name_entry.focus_set()

    def _reset_confirmation(self, *_args):
        self._overwrite_path = None
        self.accept_button.configure(text="Speichern" if self.save else "Auswählen")
        self.status_text.set("")

    def _go_path(self, _event=None):
        self._navigate(_target(self._directory, self.path_text.get()))
        return "break"

    def _navigate(self, path):
        self._directory = path
        self.path_text.set(str(path))
        if not self.save:
            self.name_text.set("")
        self._refresh()

    def _refresh(self):
        self._listing_generation += 1
        generation = self._listing_generation
        directory = self._directory
        self._loading = True
        self.tree.delete(*self.tree.get_children())
        self._paths.clear()
        patterns = _patterns(self._types[max(0, self.type_box.current())][1])
        self._reset_confirmation()
        self.status_text.set("Ordner wird gelesen …")

        def read_directory():
            rows = [(path, path.is_dir()) for path in directory.iterdir()]
            return sorted(rows, key=lambda row: (not row[1], row[0].name.casefold()))

        def loaded(rows):
            if generation != self._listing_generation:
                return
            self._loading = False
            self.status_text.set("")
            for path, is_dir in rows:
                if not (is_dir or _matches(path.name, patterns)):
                    continue
                item = self.tree.insert("", "end", text=path.name, values=("Ordner" if is_dir else "Datei",))
                self._paths[item] = path

        def failed(_error):
            if generation == self._listing_generation:
                self._loading = False
                self.status_text.set("Der Ordner konnte nicht gelesen werden. Pfad und Zugriffsrechte prüfen.")

        run_worker(self, read_directory, loaded, failed)

    def _selected(self, _event=None):
        paths = [self._paths[item] for item in self.tree.selection() if item in self._paths]
        files = [path.name for path in paths if path.is_file()]
        if files:
            # Tcl list quoting preserves spaces/braces in multiple filenames.
            if self.multiple:
                self.name_entry.delete(0, "end")
                self.name_entry.insert(0, self.tk.call("list", *files))
            else:
                self.name_text.set(files[0])

    def _activate(self, _event=None):
        item = self.tree.focus()
        path = self._paths.get(item)
        if path is not None and path.is_dir():
            self._navigate(path)
        else:
            self._accept()
        return "break"

    def _accept(self, _event=None):
        raw = self.name_text.get().strip()
        if not raw:
            self.status_text.set("Bitte eine Datei auswählen oder einen Dateinamen eingeben.")
            return "break"
        try:
            names = self.tk.splitlist(raw) if self.multiple else (raw,)
            paths = tuple(_target(self._directory, name, self.extension if self.save else "") for name in names)
            if len(paths) == 1 and paths[0].is_dir():
                self._navigate(paths[0])
                return "break"
            if self.save:
                path = paths[0]
                if not path.parent.is_dir():
                    self.status_text.set("Der Zielordner ist nicht vorhanden.")
                    return "break"
                if path.exists() and not path.is_file():
                    self.status_text.set("Das Ziel ist keine reguläre Datei.")
                    return "break"
                if path.exists() and self.confirmoverwrite and self._overwrite_path != path:
                    self._overwrite_path = path
                    self.status_text.set(f"Die Datei {path.name} ist vorhanden. Mit 'Überschreiben' bestätigen.")
                    self.accept_button.configure(text="Überschreiben")
                    return "break"
            elif not paths or any(not path.is_file() for path in paths):
                self.status_text.set("Bitte ausschließlich vorhandene Dateien auswählen.")
                return "break"
        except (OSError, ValueError, tk.TclError):
            self.status_text.set("Der Dateipfad ist ungültig oder nicht zugänglich.")
            return "break"
        self.result = tuple(str(path) for path in paths) if self.multiple else str(paths[0])
        self.destroy()
        return "break"


def _ask(**options):
    picker = FilePicker(**options)
    parent = options.get("parent")
    def owner_closed(event):
        if event.widget is parent and owner_alive(picker):
            picker.destroy()
    binding = parent.bind("<Destroy>", owner_closed, add="+") if parent is not None else None
    try:
        picker.wait_window()
        if parent is not None and not owner_alive(parent):
            return () if options.get("multiple") else ""
        return picker.result
    finally:
        if binding and owner_alive(parent):
            parent.unbind("<Destroy>", binding)


def askopenfilename(**options):
    return _ask(**options)


def askopenfilenames(**options):
    return _ask(multiple=True, **options)


def asksaveasfilename(**options):
    return _ask(save=True, **options)
