"""Folder tree and organization controls for the shared restart library."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .restart_runtime import MODE_LABELS
from .restart_templates import TEMPLATE_COLORS, folder_paths
from .ui_components import fit_window_to_parent
from .window_policy import AppWindow


class TemplateLibraryTree(ttk.Treeview):
    def __init__(self, parent):
        super().__init__(parent, columns=("count", "mode"), selectmode="extended")
        for column, label, width in (("#0", "Ordner / Vorlage", 460), ("count", "Server", 75), ("mode", "Ablauf", 205)):
            self.heading(column, text=label)
            self.column(column, width=width, stretch=column == "#0")
        self.folder_rows = {}
        self.swatches = {}
        for color in TEMPLATE_COLORS.values():
            image = tk.PhotoImage(master=self, width=14, height=14)
            if color:
                image.put(color, to=(2, 2, 12, 12))
            self.swatches[color] = image
        style = ttk.Style(self)
        self.tag_configure("folder", background=style.lookup("Treeview.Heading", "background"))

    def refresh(self, library, *, reveal=()):
        selected = [(self.folder_rows.get(row, row), row in self.folder_rows) for row in self.selection()]
        focus, (scroll, _) = self.focus(), self.yview()
        focus_folder = self.folder_rows.get(focus)
        previous_open = {folder_id: bool(self.item(row, "open")) for row, folder_id in self.folder_rows.items()}
        self.delete(*self.get_children())
        folders = {folder["id"]: folder for folder in library.get("folders", [])}
        paths = folder_paths(folders.values())
        # Existing/imported template IDs are kept intact. Reserve a noncolliding folder prefix.
        prefix = "folder:"
        item_ids = {item["id"] for item in library["items"]}
        while any(item_id.startswith(prefix) for item_id in item_ids):
            prefix += ":"
        rows = {folder_id: prefix + folder_id for folder_id in folders}
        self.folder_rows = {row: folder_id for folder_id, row in rows.items()}
        for folder_id in sorted(paths, key=lambda key: paths[key].casefold()):
            folder = folders[folder_id]
            self.insert(rows.get(folder.get("parent"), ""), "end", iid=rows[folder_id],
                        text="Ordner · " + folder["name"], open=previous_open.get(folder_id, True),
                        image=self.swatches[folder.get("color", "")], tags=("folder",))
        for item in sorted(library["items"], key=lambda entry: entry["name"].casefold()):
            self.insert(rows.get(item.get("folder"), ""), "end", iid=item["id"], text=item["name"],
                        image=self.swatches[item.get("color", "")],
                        values=(len(item["targets"]), MODE_LABELS[item["mode"]]))
        kept = [rows.get(key, "") if is_folder else key for key, is_folder in selected]
        kept = [row for row in kept if row and self.exists(row)]
        self.selection_set(kept)
        if focus_folder:
            focus = rows.get(focus_folder, "")
        if focus and self.exists(focus):
            self.focus(focus)
        self.yview_moveto(scroll)
        if reveal:
            visible_rows = [rows[key] if is_folder else key for key, is_folder in reveal]
            for row in visible_rows:
                self.see(row)
            self.selection_set(visible_rows)
            self.focus(visible_rows[-1])


class TemplateOrganizationDialog(AppWindow):
    _blocks_app_shortcuts = True

    def __init__(self, parent, folders, *, folder=None, templates=()):
        super().__init__(parent)
        self.result = None
        is_folder = folder is not None
        multiple = len(templates) > 1
        item = folder if is_folder else templates[0]
        field = "parent" if is_folder else "folder"
        paths = folder_paths(folders)
        folder_path = paths.get(item["id"]) if is_folder else None
        allowed = [(key, path) for key, path in paths.items() if
                   folder_path is None or (path != folder_path and not path.startswith(folder_path + " / "))]
        allowed.sort(key=lambda option: option[1].casefold())
        self.destinations = [("", "Ohne Ordner")] + [(key, "📁 " + path) for key, path in allowed]
        title = "Ordner bearbeiten" if is_folder and item["id"] in paths else "Neuer Ordner"
        if not is_folder:
            title = f"{len(templates)} Vorlagen verschieben" if multiple else "Vorlage organisieren"
        self.title(title)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        if is_folder:
            ttk.Label(frame, text="Ordnername").pack(anchor="w")
            self.name = tk.StringVar(self, value=item["name"])
            entry = ttk.Entry(frame, textvariable=self.name)
            entry.pack(fill="x", pady=(4, 10))
            entry.focus_set()
            entry.selection_range(0, "end")
        elif not multiple:
            ttk.Label(frame, text=item["name"], wraplength=565).pack(anchor="w", pady=(0, 10))
        ttk.Label(frame, text="Übergeordneter Ordner" if is_folder else "Ordner").pack(anchor="w")
        self.destination = ttk.Combobox(frame, state="readonly", values=[label for _, label in self.destinations])
        self.destination.pack(fill="x", pady=(4, 10))
        current_folder = item.get(field, "")
        if multiple and any(template.get(field, "") != current_folder for template in templates):
            self.destination.set("Ordner auswählen")
        else:
            self.destination.current(next(i for i, (key, _label) in enumerate(self.destinations) if key == current_folder))
        self.color = None
        if not multiple:
            ttk.Label(frame, text="Farbe").pack(anchor="w")
            self.color = ttk.Combobox(frame, state="readonly", values=list(TEMPLATE_COLORS))
            self.color.pack(fill="x", pady=(4, 10))
            self.color.set(next(label for label, color in TEMPLATE_COLORS.items() if color == item.get("color", "")))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        apply_button = ttk.Button(buttons, text="Verschieben" if multiple else "Speichern",
                                  command=lambda: self.accept(field))
        apply_button.pack(side="right")
        if self.destination.current() < 0:
            apply_button.state(["disabled"])
            self.destination.bind("<<ComboboxSelected>>", lambda _: apply_button.state(["!disabled"]))
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _: self.destroy())
        fit_window_to_parent(self, parent, 610, 300)

    def accept(self, field):
        index = self.destination.current()
        if index < 0:
            return
        self.result = {field: self.destinations[index][0]}
        if hasattr(self, "name"):
            self.result["name"] = self.name.get()
        if self.color is not None:
            self.result["color"] = TEMPLATE_COLORS[self.color.get()]
        self.destroy()
