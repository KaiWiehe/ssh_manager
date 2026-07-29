from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk


class CertificateDeployDialog(tk.Toplevel):
    """Collects one certificate deployment without persisting sensitive data."""

    def __init__(self, parent: tk.Tk, target_count: int):
        super().__init__(parent)
        self.title("Zertifikatsdateien übertragen")
        self.geometry("760x590")
        self.minsize(680, 520)
        self.result: dict | None = None
        self._files: list[str] = []
        self._target_dir_var = tk.StringVar()
        self._overwrite_var = tk.BooleanVar(value=False)
        self._sudo_password_var = tk.StringVar()
        self._show_password_var = tk.BooleanVar(value=False)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build(target_count)
        self._center_on_parent(parent)

    def _build(self, target_count: int) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        ttk.Label(root, text=f"Zertifikatsdateien für {target_count} Host(s)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Dateien werden zuerst nach /tmp hochgeladen und erst danach per sudo in den Zielordner kopiert.", foreground="#666666").grid(row=1, column=0, sticky="w", pady=(2, 10))

        files_frame = ttk.LabelFrame(root, text="Lokale Zertifikatsdateien", padding=10)
        files_frame.grid(row=2, column=0, sticky="nsew")
        files_frame.columnconfigure(0, weight=1)
        files_frame.rowconfigure(0, weight=1)
        self._files_list = tk.Listbox(files_frame, selectmode="extended", height=8)
        self._files_list.grid(row=0, column=0, sticky="nsew")
        buttons = ttk.Frame(files_frame)
        buttons.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(buttons, text="Dateien auswählen…", command=self._choose_files).pack(side="left")
        ttk.Button(buttons, text="Auswahl entfernen", command=self._remove_selected).pack(side="left", padx=(8, 0))

        destination = ttk.LabelFrame(root, text="Ziel", padding=10)
        destination.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        destination.columnconfigure(1, weight=1)
        ttk.Label(destination, text="Zielordner:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(destination, textvariable=self._target_dir_var).grid(row=0, column=1, sticky="ew")
        ttk.Label(destination, text="Alle ausgewählten Dateien behalten ihren Namen.", foreground="#666666").grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Checkbutton(destination, text="Vorhandene Dateien überschreiben", variable=self._overwrite_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        security = ttk.LabelFrame(root, text="sudo", padding=10)
        security.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        security.columnconfigure(1, weight=1)
        ttk.Label(security, text="Passwort (optional):").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._password_entry = ttk.Entry(security, textvariable=self._sudo_password_var, show="•")
        self._password_entry.grid(row=0, column=1, sticky="ew")
        ttk.Checkbutton(security, text="anzeigen", variable=self._show_password_var, command=self._toggle_password).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(security, text="Wird nur für diesen Lauf verwendet und nicht gespeichert.", foreground="#666666").grid(row=1, column=1, sticky="w", pady=(4, 0))

        after = ttk.LabelFrame(root, text="Befehl nach erfolgreichem Upload (optional)", padding=10)
        after.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        after.columnconfigure(0, weight=1)
        self._post_command = scrolledtext.ScrolledText(after, wrap="word", height=4)
        self._post_command.grid(row=0, column=0, sticky="ew")

        actions = ttk.Frame(root)
        actions.grid(row=6, column=0, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Abbrechen", command=self._on_cancel, width=11).pack(side="right")
        ttk.Button(actions, text="Übertragen", command=self._on_ok, width=12).pack(side="right", padx=(0, 8))

    def _choose_files(self) -> None:
        paths = filedialog.askopenfilenames(parent=self, title="Zertifikatsdateien auswählen")
        for path in paths:
            if path and path not in self._files:
                self._files.append(path)
        self._refresh_files()

    def _remove_selected(self) -> None:
        selected = {self._files_list.get(index) for index in self._files_list.curselection()}
        self._files = [path for path in self._files if path not in selected]
        self._refresh_files()

    def _refresh_files(self) -> None:
        self._files_list.delete(0, "end")
        for path in self._files:
            self._files_list.insert("end", path)

    def _toggle_password(self) -> None:
        self._password_entry.configure(show="" if self._show_password_var.get() else "•")

    def _on_ok(self) -> None:
        if not self._files:
            messagebox.showwarning("Keine Dateien", "Bitte mindestens eine Zertifikatsdatei auswählen.", parent=self)
            return
        missing = [path for path in self._files if not Path(path).is_file()]
        if missing:
            messagebox.showwarning("Datei nicht gefunden", f"Diese Datei ist nicht verfügbar:\n{missing[0]}", parent=self)
            return
        names = [Path(path).name for path in self._files]
        if len(names) != len(set(names)):
            messagebox.showwarning("Doppelte Dateinamen", "Die ausgewählten Dateien müssen unterschiedliche Dateinamen haben.", parent=self)
            return
        target_dir = self._target_dir_var.get().strip()
        if not target_dir.startswith("/"):
            messagebox.showwarning("Ungültiger Zielordner", "Bitte einen absoluten Linux-Pfad angeben, z. B. /etc/ssl/private.", parent=self)
            return
        if "\n" in target_dir or "\r" in target_dir:
            messagebox.showwarning("Ungültiger Zielordner", "Der Zielordner darf keinen Zeilenumbruch enthalten.", parent=self)
            return
        self.result = {
            "files": list(self._files),
            "target_dir": target_dir.rstrip("/") or "/",
            "overwrite": self._overwrite_var.get(),
            "sudo_password": self._sudo_password_var.get(),
            "post_command": self._post_command.get("1.0", "end").strip(),
        }
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")
