"""Explicit ownership and access policy for newly deployed certificate files."""
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .dialogs_base import _USERNAME_RE, _build_quickselect_buttons
from .certificate_permissions import CERTIFICATE_MODES
from .ui_components import build_dialog_actions, build_dialog_header, fit_window_to_parent


class CertificatePermissionsDialog(tk.Toplevel):
    def __init__(self, parent, session_users, files, quick_users, default_user, previous=None):
        super().__init__(parent)
        self.title("Dateibesitzer und Rechte")
        self.result = None
        self._sessions = session_users
        previous = previous or {}
        self._mode = tk.StringVar(value="all")
        self._all_owner = tk.StringVar(value=next(iter(previous.get("owners", {}).values()), default_user))
        self._owners = {session.key: tk.StringVar(value=previous.get("owners", {}).get(session.key, user or default_user))
                        for session, user in session_users}
        self._file_modes = {path: tk.StringVar(value=previous.get("file_modes", {}).get(path, "0600")) for path in files}
        self._existing = tk.BooleanVar(value=previous.get("apply_to_existing", False))
        if len(set(value.get() for value in self._owners.values())) > 1:
            self._mode.set("each")
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(5, weight=1)
        build_dialog_header(root, "Dateibesitzer und Rechte", "Der Dateibesitzer ist der Dienstbenutzer, der die Dateien lesen muss. Er ist unabhängig vom SSH-Anmeldebenutzer.")
        controls = ttk.Frame(root)
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Radiobutton(controls, text="Ein Besitzer für alle Server", variable=self._mode, value="all", command=self._toggle).pack(side="left")
        ttk.Radiobutton(controls, text="Besitzer je Server", variable=self._mode, value="each", command=self._toggle).pack(side="left", padx=12)
        self._all_entry = ttk.Combobox(root, textvariable=self._all_owner, values=quick_users)
        self._all_entry.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self._quick = _build_quickselect_buttons(root, quick_users, self._all_owner)
        self._quick.grid(row=3, column=0, sticky="ew", pady=(4, 6))
        ttk.Label(root, text="Gruppe: primäre Gruppe des gewählten Benutzers. 0600: nur Besitzer; 0640: zusätzlich Gruppe; 0644: alle dürfen lesen.\nPrivate Keys/Keystores bei 0600 lassen; 0644 nur für öffentliche Zertifikate wählen.",
                  wraplength=650, style="Muted.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 8))
        container = ttk.Frame(root)
        container.grid(row=5, column=0, sticky="nsew")
        canvas = tk.Canvas(container, highlightthickness=0, height=250)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        body.columnconfigure(1, weight=1)
        self._host_entries = []
        self._host_labels = []
        row = 0
        for session, _user in session_users:
            label = ttk.Label(body, text=f"{session.display_name} ({session.hostname})", wraplength=350)
            label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            self._host_labels.append(label)
            entry = ttk.Combobox(body, textvariable=self._owners[session.key], values=quick_users)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self._host_entries.append(entry)
            row += 1
        ttk.Separator(body).grid(row=row, column=0, columnspan=2, sticky="ew", pady=10)
        row += 1
        for path, variable in self._file_modes.items():
            ttk.Label(body, text=Path(path).name, wraplength=350).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            ttk.Combobox(body, textvariable=variable, values=CERTIFICATE_MODES, state="readonly", width=8).grid(row=row, column=1, sticky="w", pady=3)
            row += 1
        ttk.Checkbutton(root, text="Gewählten Besitzer und Rechte auch auf vorhandene Dateien anwenden", variable=self._existing).grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Label(root, text="Ohne Haken behalten vorhandene Dateien ihre Besitzer und Rechte. Neue Dateien erhalten die gewählte Regel.",
                  wraplength=650, style="Muted.TLabel").grid(row=7, column=0, sticky="w", pady=(4, 0))
        build_dialog_actions(root, row=8, primary_text="Übernehmen", primary_command=self._ok, cancel_command=self._cancel)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _: self._cancel())
        self._toggle()
        fit_window_to_parent(self, parent, 720, 650, min_width=580, min_height=500)

    def _toggle(self):
        shared = self._mode.get() == "all"
        self._all_entry.configure(state="normal" if shared else "disabled")
        for entry in self._host_entries:
            entry.configure(state="disabled" if shared else "normal")
        for widget in self._host_entries + self._host_labels:
            if shared:
                widget.grid_remove()
            else:
                widget.grid()
        for button in self._quick.winfo_children():
            button.configure(state="normal" if shared else "disabled")

    def _ok(self):
        owners = {key: (self._all_owner.get() if self._mode.get() == "all" else value.get()).strip() for key, value in self._owners.items()}
        if not owners or any(not _USERNAME_RE.fullmatch(value) for value in owners.values()):
            messagebox.showwarning("Dateibesitzer", "Bitte für jeden Server einen gültigen Benutzernamen wählen oder eingeben.", parent=self)
            return
        self.result = {"owners": owners, "file_modes": {path: value.get() for path, value in self._file_modes.items()}, "apply_to_existing": self._existing.get()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
