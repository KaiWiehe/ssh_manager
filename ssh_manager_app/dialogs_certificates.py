from __future__ import annotations

import tkinter as tk
import posixpath
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .models import Session


def _shell_single_quote(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _ssh_folder_list_command(session: Session, user: str, path: str, sudo_password: str) -> tuple[list[tuple[str, str]], str]:
    """Read direct child entries over SSH without exposing the password in args."""
    if session.is_ssh_config_session:
        command = ["ssh", "-o", "BatchMode=yes", session.display_name, "bash", "-s"]
    else:
        command = ["ssh", "-o", "BatchMode=yes"]
        if session.port != 22:
            command.extend(["-p", str(session.port)])
        command.extend([f"{user}@{session.hostname}", "bash", "-s"])

    script = ["set -u"]
    if sudo_password:
        script.extend([
            f"SSH_MANAGER_SUDO_PASSWORD={_shell_single_quote(sudo_password)}",
            "sudo() { printf '%s\\n' \"$SSH_MANAGER_SUDO_PASSWORD\" | command sudo -S -p '' \"$@\"; }",
        ])
    script.extend([
        f"path={_shell_single_quote(path)}",
        "if [ -d \"$path\" ] && [ -r \"$path\" ] && [ -x \"$path\" ]; then",
        "  find \"$path\" -mindepth 1 -maxdepth 1 -printf '%y\\t%p\\n' | sort -t $'\\t' -k2",
        "else",
        "  sudo find \"$path\" -mindepth 1 -maxdepth 1 -printf '%y\\t%p\\n' | sort -t $'\\t' -k2",
        "fi",
    ])
    remote_input = ("\n".join(script) + "\n").encode("utf-8")
    try:
        completed = subprocess.run(
            command,
            input=remote_input,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], str(exc)
    if completed.returncode != 0:
        output = completed.stderr or completed.stdout or b"Ordner konnten nicht abgefragt werden."
        error = output.decode("utf-8", errors="replace").strip() if isinstance(output, bytes) else str(output).strip()
        return [], error
    output = completed.stdout.decode("utf-8", errors="replace") if isinstance(completed.stdout, bytes) else str(completed.stdout)
    entries: list[tuple[str, str]] = []
    for line in output.splitlines():
        entry_type, separator, entry_path = line.partition("\t")
        if separator and entry_path.strip():
            entries.append((entry_type, entry_path.strip()))
    return entries, ""


class RemoteFolderBrowserDialog(tk.Toplevel):
    """Browse direct remote subdirectories on one selected reference host."""

    def __init__(self, parent: tk.Toplevel, session_users: list[tuple[Session, str]], initial_path: str, sudo_password: str):
        super().__init__(parent)
        self.title("Ordner auf Server durchsuchen")
        self.geometry("680x470")
        self.minsize(580, 390)
        self.result: str | None = None
        self._session_users = session_users
        self._sudo_password = sudo_password
        self._host_var = tk.StringVar(value=self._host_label(session_users[0]))
        self._path_var = tk.StringVar(value=initial_path or "/")
        self._status_var = tk.StringVar(value="Ordner werden geladen …")
        self._entries: list[tuple[str, str]] = []

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build()
        self._center_on_parent(parent)
        self._load()

    @staticmethod
    def _host_label(item: tuple[Session, str]) -> str:
        session, user = item
        return f"{session.display_name} ({user}@{session.hostname})"

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)
        ttk.Label(root, text="Referenz-Host:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._host_combo = ttk.Combobox(root, state="readonly", textvariable=self._host_var, values=[self._host_label(item) for item in self._session_users])
        self._host_combo.grid(row=0, column=1, sticky="ew")
        self._host_combo.bind("<<ComboboxSelected>>", lambda _event: self._load())
        ttk.Label(root, text="Aktueller Ordner:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(10, 0))
        self._path_entry = ttk.Entry(root, textvariable=self._path_var)
        self._path_entry.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        self._path_entry.bind("<Return>", lambda _event: self._load())
        self._folders = tk.Listbox(root, height=12)
        self._folders.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        self._folders.bind("<Double-Button-1>", lambda _event: self._open_selected())
        ttk.Label(root, textvariable=self._status_var, foreground="#666666", wraplength=620).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        controls = ttk.Frame(root)
        controls.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(controls, text="Eine Ebene hoch", command=self._up).pack(side="left")
        ttk.Button(controls, text="Aktualisieren", command=self._load).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Abbrechen", command=self._on_cancel).pack(side="right")
        ttk.Button(controls, text="Diesen Ordner verwenden", command=self._use_current).pack(side="right", padx=(0, 8))

    def _selected_session_user(self) -> tuple[Session, str]:
        index = max(0, self._host_combo.current())
        return self._session_users[index]

    def _load(self) -> None:
        path = self._path_var.get().strip() or "/"
        if not path.startswith("/"):
            self._status_var.set("Bitte einen absoluten Linux-Pfad angeben.")
            return
        self._path_var.set(path.rstrip("/") or "/")
        self._folders.delete(0, "end")
        self._status_var.set("Ordner werden geladen …")
        self._host_combo.configure(state="disabled")
        session, user = self._selected_session_user()
        threading.Thread(target=self._load_worker, args=(session, user, self._path_var.get(), self._sudo_password), daemon=True).start()

    def _load_worker(self, session: Session, user: str, path: str, sudo_password: str) -> None:
        folders, error = _ssh_folder_list_command(session, user, path, sudo_password)
        self.after(0, lambda: self._show_folders(folders, error))

    def _show_folders(self, entries: list[tuple[str, str]], error: str) -> None:
        self._host_combo.configure(state="readonly")
        if error:
            self._status_var.set(f"Abfrage fehlgeschlagen: {error}")
            return
        self._entries = entries
        folder_count = 0
        file_count = 0
        for entry_type, entry_path in entries:
            if entry_type == "d":
                prefix = "📁"
                folder_count += 1
            elif entry_type == "f":
                prefix = "📄"
                file_count += 1
            elif entry_type == "l":
                prefix = "🔗"
                file_count += 1
            else:
                prefix = "•"
                file_count += 1
            self._folders.insert("end", f"{prefix}  {entry_path}")
        self._status_var.set(f"{folder_count} Ordner und {file_count} Dateien/Einträge gefunden. Doppelklick öffnet nur Ordner.")

    def _open_selected(self) -> None:
        selected = self._folders.curselection()
        if not selected:
            return
        entry_type, entry_path = self._entries[selected[0]]
        if entry_type != "d":
            self._status_var.set("Dateien dienen nur als Kontext. Bitte einen Ordner auswählen.")
            return
        self._path_var.set(entry_path)
        self._load()

    def _up(self) -> None:
        current = self._path_var.get().rstrip("/") or "/"
        parent = posixpath.dirname(current)
        self._path_var.set(parent or "/")
        self._load()

    def _use_current(self) -> None:
        self.result = self._path_var.get().strip() or "/"
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Toplevel) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")


class CertificateDeployDialog(tk.Toplevel):
    """Collects one certificate deployment without persisting sensitive data."""

    def __init__(self, parent: tk.Tk, target_count: int, reference_sessions: list[tuple[Session, str]] | None = None, favorites: list[dict] | None = None):
        super().__init__(parent)
        self.title("Dateien übertragen")
        self.geometry("760x590")
        self.minsize(680, 520)
        self.result: dict | None = None
        self._files: list[str] = []
        self._reference_sessions = reference_sessions or []
        self._favorites = [item for item in (favorites or []) if item.get("mode", "command") == "command" and str(item.get("command", "")).strip()]
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

        ttk.Label(root, text=f"Dateien für {target_count} Host(s)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Dateien werden zuerst nach /tmp hochgeladen und erst danach per sudo in den Zielordner kopiert.", foreground="#666666").grid(row=1, column=0, sticky="w", pady=(2, 10))

        files_frame = ttk.LabelFrame(root, text="Lokale Dateien", padding=10)
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
        self._browse_button = ttk.Button(destination, text="Auf Server durchsuchen…", command=self._browse_remote_folders)
        self._browse_button.grid(row=0, column=2, padx=(8, 0))
        if not self._reference_sessions:
            self._browse_button.configure(state="disabled")
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
        favorite_bar = ttk.Frame(after)
        favorite_bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        favorite_bar.columnconfigure(1, weight=1)
        ttk.Label(favorite_bar, text="Favorit:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._favorite_var = tk.StringVar()
        favorite_labels = [self._favorite_label(item) for item in self._favorites]
        self._favorite_combo = ttk.Combobox(favorite_bar, state="readonly", textvariable=self._favorite_var, values=favorite_labels)
        self._favorite_combo.grid(row=0, column=1, sticky="ew")
        self._favorite_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_favorite())
        if not self._favorites:
            self._favorite_combo.configure(state="disabled")
            ttk.Label(favorite_bar, text="Keine Befehl-Favoriten vorhanden.", foreground="#666666").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self._post_command = scrolledtext.ScrolledText(after, wrap="word", height=4)
        self._post_command.grid(row=1, column=0, sticky="ew")

        options = ttk.Frame(root)
        options.grid(row=6, column=0, sticky="w", pady=(10, 0))
        self._close_on_success_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Terminal-Tab nach erfolgreicher Übertragung schließen", variable=self._close_on_success_var).pack(side="left")
        ttk.Label(options, text="Standard: offen lassen für eine interaktive Bash-Konsole.", foreground="#666666").pack(side="left", padx=(10, 0))

        actions = ttk.Frame(root)
        actions.grid(row=7, column=0, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Abbrechen", command=self._on_cancel, width=11).pack(side="right")
        ttk.Button(actions, text="Übertragen", command=self._on_ok, width=12).pack(side="right", padx=(0, 8))

    def _choose_files(self) -> None:
        paths = filedialog.askopenfilenames(parent=self, title="Dateien auswählen")
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

    @staticmethod
    def _favorite_label(item: dict) -> str:
        return str(item.get("name") or item.get("label") or str(item.get("command", "")).splitlines()[0])

    def _apply_favorite(self) -> None:
        selected = self._favorite_combo.current()
        if selected < 0:
            return
        command = str(self._favorites[selected].get("command", "")).strip()
        self._post_command.delete("1.0", "end")
        self._post_command.insert("1.0", command)

    def _browse_remote_folders(self) -> None:
        dialog = RemoteFolderBrowserDialog(
            self,
            self._reference_sessions,
            self._target_dir_var.get().strip() or "/",
            self._sudo_password_var.get(),
        )
        self.wait_window(dialog)
        if dialog.result:
            self._target_dir_var.set(dialog.result)

    def _on_ok(self) -> None:
        if not self._files:
            messagebox.showwarning("Keine Dateien", "Bitte mindestens eine Datei auswählen.", parent=self)
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
            "close_on_success": self._close_on_success_var.get(),
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
