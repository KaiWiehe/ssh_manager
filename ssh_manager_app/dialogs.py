from __future__ import annotations

import tkinter as tk
import uuid
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk
from typing import Optional, Callable

from . import DEFAULT_USER, QUICK_USERS, Session, WindowsTerminalSettings
from .constants import _APP_PREFIX, _SSH_ALIAS_PREFIX, _SSH_CONFIG_FILE

_USERNAME_RE = __import__("re").compile(r"^[A-Za-z0-9._-]+$")

class UserDialog(tk.Toplevel):
    """
    Modaler Dialog zur Benutzernamen-Auswahl.
    Nach Schließen: self.result = gewählter Username (str) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, title: str = "Benutzername auswählen", quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: Optional[str] = None
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        # Modal machen
        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        # Tastaturkürzel
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        quick_count = max(len(self._quick_users), 1)
        ttk.Label(frame, text="Quickselect:").grid(
            row=0, column=0, columnspan=quick_count, sticky="w", pady=(0, 4)
        )

        self._user_var = tk.StringVar(value=self._default_user)

        # Quickselect-Buttons
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=1, column=col, padx=2, pady=(0, 8))

        # Freitext-Eingabe
        ttk.Label(frame, text="Benutzername:").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=3, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.select_range(0, "end")
        entry.focus()

        # OK / Abbrechen
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(
            side="left", padx=4
        )

    def _on_ok(self) -> None:
        user = self._user_var.get().strip()
        if not user:
            return  # Leeres Feld: Dialog bleibt offen
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = user
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


class JumpHostDialog(tk.Toplevel):
    """Dialog zum temporären Öffnen einer Session über ProxyJump."""

    def __init__(self, parent: tk.Tk, target_session: Session, sessions: list[Session], open_folders_getter: Callable[[], set[str]] | None = None):
        super().__init__(parent)
        self.title("Über Jumphost öffnen")
        self.resizable(True, True)
        self.minsize(760, 520)
        self.result: tuple[str, str, int, str | None] | None = None
        self.save_result: tuple[str, str, int, str, str] | None = None
        self._target_session = target_session
        self._sessions = sessions
        self._open_folders_getter = open_folders_getter

        self.transient(parent)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build()
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)

        target_label = f"Ziel: {self._target_session.display_name} ({self._target_session.hostname})"
        ttk.Label(frame, text=target_label, font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

        help_text = (
            "Jumphost frei eingeben oder unten im Baum eine bestehende Verbindung auswählen.\n"
            "Aus einer Verbindung werden Host, User und Port übernommen, wenn vorhanden."
        )
        ttk.Label(frame, text=help_text, foreground="#555555", justify="left").grid(row=1, column=0, sticky="w", pady=(0, 10))

        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._jump_host_var = tk.StringVar()
        default_user = getattr(parent, "get_default_user", lambda: DEFAULT_USER)()
        self._jump_user_var = tk.StringVar(value=default_user)
        self._jump_port_var = tk.StringVar(value="22")
        self._filter_var = tk.StringVar()

        ttk.Label(form, text="Jumphost:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        host_entry = ttk.Entry(form, textvariable=self._jump_host_var)
        host_entry.grid(row=0, column=1, sticky="ew", pady=4)
        host_entry.focus()

        ttk.Label(form, text="Jumphost-User:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(form, textvariable=self._jump_user_var).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Jumphost-Port:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(form, textvariable=self._jump_port_var, width=8).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(form, text="Filter:").grid(row=3, column=0, sticky="w", pady=(10, 4), padx=(0, 8))
        filter_entry = ttk.Entry(form, textvariable=self._filter_var)
        filter_entry.grid(row=3, column=1, sticky="ew", pady=(10, 4))
        self._filter_var.trace_add("write", lambda *_: self._rebuild_tree())

        tree_frame = ttk.Frame(frame)
        tree_frame.grid(row=4, column=0, sticky="nsew", pady=(8, 8))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(tree_frame, columns=("host",), show="tree headings", selectmode="browse")
        self._tree.heading("#0", text="Verbindungen")
        self._tree.heading("host", text="Host")
        self._tree.column("#0", width=320, stretch=True)
        self._tree.column("host", width=280, stretch=True)
        self._tree.grid(row=0, column=0, sticky="nsew")
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-Button-1>", lambda _: self._on_open())

        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=scroll.set)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, sticky="e", pady=(6, 0))
        ttk.Button(btn_frame, text="Als SSH-Config speichern…", command=self._on_save).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Öffnen", command=self._on_open).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel).pack(side="left", padx=4)

        self._session_by_item: dict[str, Session] = {}
        self._rebuild_tree()

    def _matches_filter(self, session: Session, query: str) -> bool:
        if not query:
            return True
        hay = f"{session.folder_key} {session.display_name} {session.hostname}".lower()
        return query in hay

    def _ensure_folder(self, folder_key: str, folder_map: dict[str, str]) -> str:
        if not folder_key:
            return ""
        parts = folder_key.split("/")
        current = ""
        parent = ""
        for part in parts:
            current = part if not current else f"{current}/{part}"
            if current not in folder_map:
                folder_map[current] = self._tree.insert(parent, "end", text=part, values=("",), open=False)
            parent = folder_map[current]
        return folder_map[current]

    def _rebuild_tree(self) -> None:
        query = self._filter_var.get().strip().lower()
        open_folders = self._open_folders_getter() if self._open_folders_getter else set()
        self._tree.delete(*self._tree.get_children())
        self._session_by_item.clear()
        folder_map: dict[str, str] = {}
        for session in sorted(self._sessions, key=lambda s: (s.folder_key.lower(), s.display_name.lower())):
            if session.key == self._target_session.key:
                continue
            if not self._matches_filter(session, query):
                continue
            parent = self._ensure_folder(session.folder_key, folder_map)
            item = self._tree.insert(parent, "end", text=session.display_name, values=(session.hostname,))
            self._session_by_item[item] = session
        for folder_key, iid in folder_map.items():
            self._tree.item(iid, open=(folder_key in open_folders) or not query)

    def _on_tree_select(self, _event=None) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        session = self._session_by_item.get(selected[0])
        if not session:
            return
        self._jump_host_var.set(session.hostname or session.display_name)
        self._jump_user_var.set(session.username or "")
        self._jump_port_var.set(str(session.port or 22))

    def _validate(self) -> tuple[str, str, int] | None:
        jump_host = self._jump_host_var.get().strip()
        if not jump_host:
            messagebox.showwarning("Kein Jumphost", "Bitte einen Jumphost eingeben oder auswählen.", parent=self)
            return None
        if not _HOSTNAME_RE.match(jump_host):
            messagebox.showwarning("Ungültiger Jumphost", "Nur Buchstaben, Ziffern, Punkte, Doppelpunkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return None
        jump_user = self._jump_user_var.get().strip()
        if jump_user and not _USERNAME_RE.match(jump_user):
            messagebox.showwarning("Ungültiger Benutzername", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return None
        try:
            jump_port = int(self._jump_port_var.get().strip() or "22")
        except ValueError:
            messagebox.showwarning("Ungültiger Port", "Jumphost-Port muss eine Zahl sein.", parent=self)
            return None
        if not 1 <= jump_port <= 65535:
            messagebox.showwarning("Ungültiger Port", "Jumphost-Port muss zwischen 1 und 65535 liegen.", parent=self)
            return None
        return jump_host, jump_user, jump_port

    def _on_open(self) -> None:
        validated = self._validate()
        if not validated:
            return
        self.result = validated
        self.destroy()

    def _on_save(self) -> None:
        validated = self._validate()
        if not validated:
            return
        alias = simpledialog.askstring("SSH-Config speichern", "Name für den neuen SSH-Config-Host:", parent=self)
        if alias is None:
            return
        alias = alias.strip()
        if not alias:
            messagebox.showwarning("Kein Name", "Bitte einen Namen für den SSH-Config-Host eingeben.", parent=self)
            return
        jump_host, jump_user, jump_port = validated
        self.save_result = (alias, jump_host, jump_port, jump_user, self._target_session.key)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.save_result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = min(max(self.winfo_reqwidth(), 760), max(pw - 40, 760))
        h = min(max(self.winfo_reqheight(), 520), max(ph - 40, 520))
        x = px + max((pw - w) // 2, 0)
        y = py + max((ph - h) // 2, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")


# ---------------------------------------------------------------------------
# SshCopyIdDialog
# ---------------------------------------------------------------------------
class SshCopyIdDialog(tk.Toplevel):
    """
    Modaler Dialog zur Auswahl von SSH Public Key und Benutzername für ssh-copy-id.
    Nach Schließen: self.result = (key_filename, user) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, target_count: int = 1, quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title("SSH Key übertragen")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self._target_count = target_count
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        # Info bei mehreren Zielen
        if self._target_count > 1:
            ttk.Label(
                frame,
                text=f"Key wird auf {self._target_count} Host(s) übertragen.",
                foreground="#555555",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        # Key-Auswahl
        ttk.Label(frame, text="Public Key:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        pub_keys = sorted(p.name for p in (_SSH_CONFIG_FILE.parent).glob("*.pub"))
        self._key_var = tk.StringVar(value=pub_keys[0] if pub_keys else "")
        key_cb = ttk.Combobox(
            frame, textvariable=self._key_var, values=pub_keys, width=30, state="readonly" if pub_keys else "normal"
        )
        key_cb.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        if not pub_keys:
            ttk.Label(frame, text="Keine *.pub-Dateien in ~/.ssh gefunden.", foreground="red").grid(
                row=2, column=0, columnspan=2, sticky="w"
            )

        # Benutzer
        ttk.Label(frame, text="Quickselect:").grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=4, column=col, padx=2, pady=(0, 8))

        ttk.Label(frame, text="Benutzername:").grid(row=5, column=0, sticky="w", pady=(0, 4))
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=6, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.focus()

        # OK / Abbrechen
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        key = self._key_var.get().strip()
        if not key:
            messagebox.showwarning("Kein Key", "Bitte einen Public Key auswählen.", parent=self)
            return
        user = self._user_var.get().strip()
        if not user:
            return
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (key, user)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# SshRemoveKeyDialog
# ---------------------------------------------------------------------------
class SshRemoveKeyDialog(tk.Toplevel):
    """
    Modaler Dialog zur Auswahl von SSH Public Key und Benutzername zum Entfernen
    des Keys aus authorized_keys auf Remote-Hosts.
    Nach Schließen: self.result = (key_filename, user) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, target_count: int = 1, quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title("SSH Key entfernen")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self._target_count = target_count
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        if self._target_count > 1:
            ttk.Label(
                frame,
                text=f"Key wird von {self._target_count} Host(s) entfernt.",
                foreground="#555555",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Public Key:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        pub_keys = sorted(p.name for p in (_SSH_CONFIG_FILE.parent).glob("*.pub"))
        self._key_var = tk.StringVar(value=pub_keys[0] if pub_keys else "")
        key_cb = ttk.Combobox(
            frame, textvariable=self._key_var, values=pub_keys, width=30, state="readonly" if pub_keys else "normal"
        )
        key_cb.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        if not pub_keys:
            ttk.Label(frame, text="Keine *.pub-Dateien in ~/.ssh gefunden.", foreground="red").grid(
                row=2, column=0, columnspan=2, sticky="w"
            )

        ttk.Label(frame, text="Quickselect:").grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=4, column=col, padx=2, pady=(0, 8))

        ttk.Label(frame, text="Benutzername:").grid(row=5, column=0, sticky="w", pady=(0, 4))
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=6, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.focus()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        key = self._key_var.get().strip()
        if not key:
            messagebox.showwarning("Kein Key", "Bitte einen Public Key auswählen.", parent=self)
            return
        user = self._user_var.get().strip()
        if not user:
            return
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (key, user)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")




class RemoteCommandDialog(tk.Toplevel):
    """Dialog für Remote-Befehl und Ausführungsoptionen."""

    def __init__(self, parent: tk.Tk, target_count: int, last_command: str = "", quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title("Befehl ausführen")
        self.geometry("720x480")
        self.minsize(620, 420)
        self.result: tuple[str, str, bool] | None = None
        self._last_command = last_command
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        self.transient(parent)
        self.grab_set()
        self._build(target_count)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, target_count: int) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(
            frame,
            text=f"Remote-Befehl für {target_count} Host(s)",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            frame,
            text="Der Befehl wird als mehrzeiliges Remote-Script per SSH ausgeführt.",
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        mode_frame = ttk.LabelFrame(frame, text="Benutzer-Auswahl", padding=12)
        mode_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        mode_frame.columnconfigure(0, weight=1)
        self._user_mode = tk.StringVar(value="all")
        ttk.Radiobutton(
            mode_frame,
            text="Ein Benutzer für alle Hosts",
            variable=self._user_mode,
            value="all",
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Benutzer pro Host auswählen",
            variable=self._user_mode,
            value="per_host",
        ).grid(row=1, column=0, sticky="w", pady=(4, 8))

        ttk.Label(mode_frame, text="Quickselect:").grid(row=2, column=0, sticky="w", pady=(0, 4))
        quick_frame = ttk.Frame(mode_frame)
        quick_frame.grid(row=3, column=0, sticky="w")
        self._user_var = tk.StringVar(value=self._default_user)
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                quick_frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=0, column=col, padx=2, pady=(0, 6))

        user_entry_frame = ttk.Frame(mode_frame)
        user_entry_frame.grid(row=4, column=0, sticky="ew")
        user_entry_frame.columnconfigure(1, weight=1)
        ttk.Label(user_entry_frame, text="Benutzername:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(user_entry_frame, textvariable=self._user_var).grid(row=0, column=1, sticky="ew")

        script_frame = ttk.LabelFrame(frame, text="Remote-Befehl", padding=8)
        script_frame.grid(row=3, column=0, sticky="nsew")
        script_frame.columnconfigure(0, weight=1)
        script_frame.rowconfigure(0, weight=1)
        self._command_text = scrolledtext.ScrolledText(script_frame, wrap="word", height=12)
        self._command_text.grid(row=0, column=0, sticky="nsew")
        if self._last_command:
            self._command_text.insert("1.0", self._last_command)
        self._command_text.focus()

        options = ttk.Frame(frame)
        options.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self._close_on_success = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options,
            text="Tab direkt schließen, wenn der Befehl erfolgreich war",
            variable=self._close_on_success,
        ).pack(anchor="w")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, pady=(14, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        command = self._command_text.get("1.0", "end").strip()
        if not command:
            messagebox.showwarning("Kein Befehl", "Bitte einen Befehl eingeben.", parent=self)
            return
        user_value = self._user_var.get().strip()
        if self._user_mode.get() == "all":
            if not user_value:
                messagebox.showwarning("Kein Benutzername", "Bitte einen Benutzernamen eingeben oder per Quickselect wählen.", parent=self)
                return
            if not _USERNAME_RE.match(user_value):
                messagebox.showwarning("Ungültiger Benutzername", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
                return
        self.result = (self._user_mode.get(), command, self._close_on_success.get())
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


class RemoteCommandConfirmDialog(tk.Toplevel):
    """Bestätigungsdialog für Remote-Befehle."""

    def __init__(self, parent: tk.Tk, command: str, session_users: list[tuple[Session, str]], close_on_success: bool):
        super().__init__(parent)
        self.title("Remote-Befehl bestätigen")
        self.geometry("760x520")
        self.minsize(680, 420)
        self.result = False

        self.transient(parent)
        self.grab_set()
        self._build(command, session_users, close_on_success)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, command: str, session_users: list[tuple[Session, str]], close_on_success: bool) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(
            frame,
            text=f"Befehl auf {len(session_users)} Host(s) ausführen?",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        behavior = "Tabs schließen sich bei Erfolg direkt." if close_on_success else "Tabs bleiben nach dem Befehl offen."
        ttk.Label(frame, text=behavior, foreground="#666666").grid(row=1, column=0, sticky="w", pady=(0, 12))

        hosts_frame = ttk.LabelFrame(frame, text="Hosts", padding=8)
        hosts_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        hosts_frame.columnconfigure(0, weight=1)
        hosts_frame.rowconfigure(0, weight=1)
        hosts_text = scrolledtext.ScrolledText(hosts_frame, wrap="word", height=10)
        hosts_text.grid(row=0, column=0, sticky="nsew")
        hosts_text.insert(
            "1.0",
            "\n".join(
                f"- {session.display_name} ({session.hostname})  User: {user}"
                for session, user in session_users
            ),
        )
        hosts_text.configure(state="disabled")

        cmd_frame = ttk.LabelFrame(frame, text="Befehl", padding=8)
        cmd_frame.grid(row=3, column=0, sticky="nsew")
        cmd_frame.columnconfigure(0, weight=1)
        cmd_frame.rowconfigure(0, weight=1)
        cmd_text = scrolledtext.ScrolledText(cmd_frame, wrap="word", height=8)
        cmd_text.grid(row=0, column=0, sticky="nsew")
        cmd_text.insert("1.0", command)
        cmd_text.configure(state="disabled")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, pady=(14, 0))
        ttk.Button(btn_frame, text="Ausführen", command=self._on_ok, width=12).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

# ---------------------------------------------------------------------------
# SshTunnelDialog
# ---------------------------------------------------------------------------
class SshTunnelDialog(tk.Toplevel):
    """
    Modaler Dialog für SSH Local Port Forwarding (-N -L).
    Nach Schließen: self.result = (ssh_server, local_port, remote_host, remote_port, user) oder None.
    remote_host ist 'localhost' wenn kein Jumphost-Ziel angegeben wurde (direkter Tunnel).
    """

    def __init__(self, parent: tk.Tk, session: Session | None = None, quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title("Tunnel öffnen")
        self.resizable(False, False)
        self.result: tuple[str, int, str, int, str] | None = None
        self._session = session
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        self.transient(parent)
        self.grab_set()
        self._build()
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        # Erklärung
        ttk.Label(
            frame,
            text="SSH verbindet sich zum Server und leitet einen lokalen Port weiter.\nDirekt (kein Jumphost) oder zu einem internen Server dahinter.",
            foreground="#555555",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        # SSH-Server
        ttk.Label(frame, text="SSH-Server:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        prefill = self._session.hostname if self._session else ""
        self._jumphost_var = tk.StringVar(value=prefill)
        ttk.Entry(frame, textvariable=self._jumphost_var, width=30).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(frame, text="Server, zu dem SSH sich verbindet.", foreground="#888888").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Separator(frame, orient="horizontal").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Port Forwarding
        ttk.Label(frame, text="Lokaler Port:").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self._local_port_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._local_port_var, width=10).grid(
            row=4, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(frame, text="Port auf deinem PC (z. B. 3306).", foreground="#888888").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Label(frame, text="Zielserver: (optional)").grid(row=6, column=0, sticky="w", pady=(0, 4))
        self._remote_host_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._remote_host_var, width=30).grid(
            row=6, column=1, sticky="ew", padx=(8, 0), pady=(0, 4)
        )

        ttk.Label(frame, text="Zielport:").grid(row=7, column=0, sticky="w", pady=(0, 4))
        self._remote_port_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._remote_port_var, width=10).grid(
            row=7, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(
            frame,
            text="Leer lassen = direkter Tunnel (Port des SSH-Servers selbst).\nFür Jumphost-Tunnel: z. B. db.intern / 3306",
            foreground="#888888",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Separator(frame, orient="horizontal").grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Benutzer
        ttk.Label(frame, text="Quickselect:").grid(row=10, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=11, column=col, padx=2, pady=(0, 8))

        ttk.Label(frame, text="Benutzername:").grid(row=12, column=0, sticky="w", pady=(0, 4))
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=13, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.focus()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=14, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _parse_port(self, var: tk.StringVar, label: str) -> int | None:
        try:
            port = int(var.get().strip())
        except ValueError:
            messagebox.showwarning("Ungültiger Port", f"{label} muss eine Zahl sein.", parent=self)
            return None
        if not 1 <= port <= 65535:
            messagebox.showwarning("Ungültiger Port", f"{label} muss zwischen 1 und 65535 liegen.", parent=self)
            return None
        return port

    def _on_ok(self) -> None:
        ssh_server = self._jumphost_var.get().strip()
        if not ssh_server:
            messagebox.showwarning("Kein SSH-Server", "Bitte einen SSH-Server eingeben.", parent=self)
            return
        if not _HOSTNAME_RE.match(ssh_server):
            messagebox.showwarning("Ungültiger SSH-Server", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return
        local_port = self._parse_port(self._local_port_var, "Lokaler Port")
        if local_port is None:
            return
        remote_host = self._remote_host_var.get().strip() or "localhost"
        if not _HOSTNAME_RE.match(remote_host):
            messagebox.showwarning("Ungültiger Zielserver", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return
        remote_port = self._parse_port(self._remote_port_var, "Zielport")
        if remote_port is None:
            return
        user = self._user_var.get().strip()
        if not user:
            return
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (ssh_server, local_port, remote_host, remote_port, user)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# SessionEditDialog
# ---------------------------------------------------------------------------
class SessionEditDialog(tk.Toplevel):
    """
    Modaler Dialog zum Anlegen oder Bearbeiten einer eigenen Session.
    Unterstützt zwei Modi: 'Eigene Verbindung' (Hostname/Port/User) und
    'SSH-Alias' (Alias aus ~/.ssh/config + Ordner).
    Nach Schließen: self.result = Session oder None (Abbrechen).
    """

    def __init__(
        self,
        parent: tk.Tk,
        existing_folders: list[str],
        ssh_aliases: list[str] | None = None,
        session: Optional[Session] = None,
        folder_preset: str = "",
        alias_preset: str = "",
        duplicate: bool = False,
        note: str = "",
    ):
        super().__init__(parent)
        self._existing_session = session
        self._duplicate = duplicate
        self._existing_folders = existing_folders
        self._ssh_aliases = ssh_aliases or []
        self._alias_preset = alias_preset
        self.note_result = note

        # Startmodus: Alias-Modus wenn Preset gesetzt oder bestehende ssh_alias Session
        if (session and session.is_ssh_alias_copy) or alias_preset:
            self._initial_mode = "alias"
        else:
            self._initial_mode = "verbindung"

        if duplicate:
            self.title("Verbindung duplizieren")
        elif session:
            self.title("Verbindung bearbeiten")
        else:
            self.title("Neue Verbindung")
        self.resizable(False, False)
        self.result: Optional[Session] = None

        self.transient(parent)
        self.grab_set()

        self._build(folder_preset)
        self._center_on_parent(parent)

        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, folder_preset: str) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self._mode_var = tk.StringVar(value=self._initial_mode)
        content_row = 0

        # Modus-Auswahl (nur wenn Aliases vorhanden und kein Bearbeitungsmodus)
        can_switch = bool(self._ssh_aliases) and not self._existing_session
        if can_switch:
            mode_frame = ttk.Frame(frame)
            mode_frame.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
            ttk.Radiobutton(
                mode_frame, text="Eigene Verbindung",
                variable=self._mode_var, value="verbindung",
                command=self._on_mode_changed,
            ).pack(side="left", padx=(0, 12))
            ttk.Radiobutton(
                mode_frame, text="SSH-Alias",
                variable=self._mode_var, value="alias",
                command=self._on_mode_changed,
            ).pack(side="left")
            content_row = 1

        s = self._existing_session

        # --- SSH-Alias Frame ---
        self._alias_frame = ttk.Frame(frame)
        self._alias_frame.columnconfigure(1, weight=1)
        self._alias_frame.grid(row=content_row, column=0, columnspan=2, sticky="ew")

        ttk.Label(self._alias_frame, text="Alias:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        alias_val = self._alias_preset or (s.display_name if s and s.is_ssh_alias_copy else "")
        self._alias_var = tk.StringVar(value=alias_val)
        alias_cb_state = "readonly" if self._alias_preset else "normal"
        ttk.Combobox(
            self._alias_frame, textvariable=self._alias_var,
            values=self._ssh_aliases, width=30, state=alias_cb_state,
        ).grid(row=0, column=1, sticky="ew")

        ttk.Label(self._alias_frame, text="Ordner:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        alias_folder_val = (s.folder_key if s and s.is_ssh_alias_copy else folder_preset)
        self._alias_folder_var = tk.StringVar(value=alias_folder_val)
        ttk.Combobox(
            self._alias_frame, textvariable=self._alias_folder_var,
            values=self._existing_folders, width=30,
        ).grid(row=1, column=1, sticky="ew")

        # --- Eigene Verbindung Frame ---
        self._verbindung_frame = ttk.Frame(frame)
        self._verbindung_frame.columnconfigure(1, weight=1)
        self._verbindung_frame.grid(row=content_row, column=0, columnspan=2, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        if s and self._duplicate:
            name_val = "Kopie von " + s.display_name
        elif s and s.is_app_session:
            name_val = s.display_name
        else:
            name_val = ""
        self._name_var = tk.StringVar(value=name_val)
        ttk.Entry(self._verbindung_frame, textvariable=self._name_var, width=32).grid(row=0, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Ordner:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self._folder_var = tk.StringVar(value=s.folder_key if (s and s.is_app_session) else folder_preset)
        ttk.Combobox(
            self._verbindung_frame, textvariable=self._folder_var,
            values=self._existing_folders, width=30,
        ).grid(row=1, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Hostname:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        self._host_var = tk.StringVar(value=s.hostname if (s and s.is_app_session) else "")
        ttk.Entry(self._verbindung_frame, textvariable=self._host_var, width=32).grid(row=2, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Benutzername:").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        self._user_var = tk.StringVar(value=s.username if (s and s.is_app_session) else "")
        ttk.Entry(self._verbindung_frame, textvariable=self._user_var, width=32).grid(row=3, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Port:").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        self._port_var = tk.StringVar(value=str(s.port) if (s and s.is_app_session) else "22")
        ttk.Entry(self._verbindung_frame, textvariable=self._port_var, width=8).grid(row=4, column=1, sticky="w")

        ttk.Label(self._verbindung_frame, text="Notizen:").grid(row=5, column=0, sticky="nw", pady=4, padx=(0, 8))
        self._note_text = tk.Text(self._verbindung_frame, width=32, height=4)
        self._note_text.grid(row=5, column=1, sticky="ew", pady=4)
        if self.note_result:
            self._note_text.insert("1.0", self.note_result)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=content_row + 1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

        # Initialen Zustand: inaktiven Frame ausblenden
        if self._initial_mode == "alias":
            self._verbindung_frame.grid_remove()
        else:
            self._alias_frame.grid_remove()

    def _on_mode_changed(self) -> None:
        """Zeigt den aktiven Frame, versteckt den anderen."""
        if self._mode_var.get() == "alias":
            self._verbindung_frame.grid_remove()
            self._alias_frame.grid()
        else:
            self._alias_frame.grid_remove()
            self._verbindung_frame.grid()

    def _on_ok(self) -> None:
        if self._mode_var.get() == "alias":
            self._on_ok_alias()
        else:
            self._on_ok_verbindung()

    def _on_ok_alias(self) -> None:
        alias = self._alias_var.get().strip()
        folder_str = self._alias_folder_var.get().strip()
        if not alias:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Alias auswählen.", parent=self)
            return
        folder_path = [p for p in folder_str.split("/") if p]
        if not folder_path:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Ordner eingeben.", parent=self)
            return
        if self._existing_session and self._existing_session.is_ssh_alias_copy:
            session_key = self._existing_session.key
        else:
            session_key = _SSH_ALIAS_PREFIX + str(uuid.uuid4())
        self.result = Session(
            key=session_key,
            display_name=alias,
            folder_path=folder_path,
            hostname=alias,
            username="",
            port=22,
            source="ssh_alias",
        )
        self.destroy()

    def _on_ok_verbindung(self) -> None:
        name = self._name_var.get().strip()
        hostname = self._host_var.get().strip()
        username = self._user_var.get().strip()
        folder_str = self._folder_var.get().strip()
        port_str = self._port_var.get().strip()

        if not name:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Namen eingeben.", parent=self)
            return
        if not hostname:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Hostnamen eingeben.", parent=self)
            return
        if not _HOSTNAME_RE.match(hostname):
            messagebox.showwarning(
                "Ungültiger Hostname",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche, Unterstriche und Doppelpunkte erlaubt.",
                parent=self,
            )
            return
        if username and not _USERNAME_RE.match(username):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Ungültiger Port", "Port muss eine Zahl zwischen 1 und 65535 sein.", parent=self)
            return

        folder_path = [p for p in folder_str.split("/") if p]
        session_key = (
            self._existing_session.key
            if self._existing_session and not self._duplicate
            else _APP_PREFIX + str(uuid.uuid4())
        )
        self.result = Session(
            key=session_key,
            display_name=name,
            folder_path=folder_path,
            hostname=hostname,
            username=username,
            port=port,
            source="app",
        )
        self.note_result = self._note_text.get("1.0", "end").strip()
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# SshConfigInspectDialog
# ---------------------------------------------------------------------------
class SshConfigInspectDialog(tk.Toplevel):
    """
    Modaler Dialog der die effektive SSH-Konfiguration eines Alias anzeigt (ssh -G <alias>).
    """

    def __init__(self, parent: tk.Tk, alias: str):
        super().__init__(parent)
        self.title(f"SSH-Konfiguration: {alias}")
        self.resizable(True, True)
        self.geometry("600x450")
        self.transient(parent)
        self.grab_set()
        self._build(alias)
        self._center_on_parent(parent)

    def _build(self, alias: str) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        txt_frame = ttk.Frame(self, padding=(8, 8, 8, 4))
        txt_frame.grid(row=0, column=0, sticky="nsew")
        txt_frame.columnconfigure(0, weight=1)
        txt_frame.rowconfigure(0, weight=1)

        txt = tk.Text(txt_frame, wrap="none", font=("Consolas", 9))
        vsb = ttk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(txt_frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        try:
            result = subprocess.run(
                ["ssh", "-G", alias],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout or result.stderr or "(keine Ausgabe)"
        except Exception as exc:
            output = f"Fehler: {exc}"

        txt.insert("1.0", output)
        txt.configure(state="disabled")

        btn_frame = ttk.Frame(self, padding=(8, 4, 8, 8))
        btn_frame.grid(row=1, column=0)
        ttk.Button(btn_frame, text="Schließen", command=self.destroy, width=12).pack()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# MoveFolderDialog
# ---------------------------------------------------------------------------
class MoveFolderDialog(tk.Toplevel):
    """
    Minimaler modaler Dialog zum Verschieben einer Session in einen anderen Ordner.
    Nach Schließen: self.result = Ordner-String oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, existing_folders: list[str], current_folder: str):
        super().__init__(parent)
        self.title("In Ordner verschieben")
        self.resizable(False, False)
        self.result: Optional[str] = None
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER
        self.transient(parent)
        self.grab_set()
        self._build(existing_folders, current_folder)
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, existing_folders: list[str], current_folder: str) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Ordner:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        self._folder_var = tk.StringVar(value=current_folder)
        ttk.Combobox(
            frame, textvariable=self._folder_var,
            values=existing_folders, width=30,
        ).grid(row=0, column=1, sticky="ew")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Ordner eingeben.", parent=self)
            return
        self.result = folder
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# ToastNotification
# ---------------------------------------------------------------------------
class ToastNotification(tk.Toplevel):
    """Kleines unauffälliges Toast oben rechts."""

    def __init__(self, parent: tk.Tk, message: str, duration_ms: int = 2200):
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        frame = ttk.Frame(self, padding=(12, 8), style="Toast.TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=message, style="Toast.TLabel").pack()

        self.update_idletasks()
        parent.update_idletasks()

        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        x = parent.winfo_rootx() + parent.winfo_width() - width - 16
        y = parent.winfo_rooty() + 16
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.after(duration_ms, self.destroy)


# ---------------------------------------------------------------------------
# SSHManagerApp
# ---------------------------------------------------------------------------
class SettingsView(ttk.Frame):
    """Einstellungsansicht im Hauptfenster."""

    STARTUP_LABELS = {
        "remember": "Letzten Ordnerzustand merken",
        "expanded": "Alle Ordner ausgeklappt starten",
        "collapsed": "Alle Ordner eingeklappt starten",
    }
    TITLE_MODE_LABELS = {
        "default": "Wie bisher",
        "name": "Nur Session-Name",
        "host": "Nur Hostname",
        "user_host": "Benutzer@Host",
        "name_host": "Name (Host)",
    }

    def __init__(self, parent: tk.Widget, app: "SSHManagerApp"):
        super().__init__(parent, padding=0)
        self._app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._default_user_var = tk.StringVar()
        self._host_timeout_var = tk.StringVar()
        self._startup_expand_var = tk.StringVar()
        self._profile_name_var = tk.StringVar()
        self._title_mode_var = tk.StringVar()
        self._toolbar_vars: dict[str, tk.BooleanVar] = {}
        self._source_visibility_vars: dict[str, tk.BooleanVar] = {}
        self._use_tab_color_var = tk.BooleanVar()
        self._section_frames: dict[str, ttk.Frame] = {}
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._active_section = "general"
        self._build()
        self.load_from_app()

    def _build(self) -> None:
        self.configure(style="SettingsRoot.TFrame")
        root = ttk.Frame(self, style="SettingsRoot.TFrame", padding=0)
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        self._root = root

        nav = ttk.Frame(root, style="SettingsNav.TFrame", padding=(16, 20))
        nav.grid(row=0, column=0, sticky="nsw")
        nav.columnconfigure(0, weight=1)
        self._nav = nav

        content_wrap = ttk.Frame(root, style="SettingsContent.TFrame", padding=(28, 22, 28, 16))
        content_wrap.grid(row=0, column=1, sticky="nsew")
        content_wrap.columnconfigure(0, weight=1)
        content_wrap.rowconfigure(1, weight=1)

        header = ttk.Frame(content_wrap, style="SettingsContent.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Einstellungen", style="SettingsTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Direkt im Hauptfenster, optimiert für Fullscreen.", style="SettingsSubtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        self._content_host = ttk.Frame(content_wrap, style="SettingsContent.TFrame")
        self._content_host.grid(row=1, column=0, sticky="nsew")
        self._content_host.columnconfigure(0, weight=1)
        self._content_host.rowconfigure(0, weight=1)

        actions = ttk.Frame(content_wrap, style="SettingsActions.TFrame", padding=(0, 16, 0, 0))
        actions.grid(row=2, column=0, sticky="ew")
        ttk.Separator(actions, orient="horizontal").pack(fill="x", pady=(0, 14))
        ttk.Button(actions, text="Speichern", command=self._save).pack(side="left")
        ttk.Button(actions, text="Zurück", command=self._app.show_main_view).pack(side="left", padx=(8, 0))

        sections = [
            ("general", "Allgemein"),
            ("sources", "Quellen / Ansicht"),
            ("users", "Schnellauswahl-Benutzer"),
            ("toolbar", "Toolbar"),
            ("terminal", "Windows Terminal"),
            ("transfer", "Export / Import"),
            ("reset", "Zurücksetzen"),
        ]
        ttk.Label(nav, text="Bereiche", style="SettingsNavTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        for idx, (key, label) in enumerate(sections, start=1):
            btn = ttk.Button(nav, text=f"  {label}", command=lambda k=key: self._show_section(k), style="SettingsNav.TButton")
            btn.grid(row=idx, column=0, sticky="ew", pady=4)
            self._nav_buttons[key] = btn

        self._section_frames["general"] = self._build_general_section()
        self._section_frames["sources"] = self._build_sources_section()
        self._section_frames["users"] = self._build_users_section()
        self._section_frames["toolbar"] = self._build_toolbar_section()
        self._section_frames["terminal"] = self._build_terminal_section()
        self._section_frames["transfer"] = self._build_transfer_section()
        self._section_frames["reset"] = self._build_reset_section()
        self._show_section(self._active_section)

    def _build_section_frame(self, title: str, description: str) -> ttk.Frame:
        frame = ttk.Frame(self._content_host, style="SettingsPanel.TFrame", padding=22)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="SettingsSectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, style="SettingsHint.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 18))
        return frame

    def _build_general_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Allgemein", "Globale Vorgaben für Auswahl, Host-Checks und Baumzustand.")
        form = ttk.Frame(frame, style="SettingsPanel.TFrame")
        form.grid(row=2, column=0, sticky="nw")
        form.columnconfigure(0, minsize=220)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Standardbenutzer:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        self._default_user_combo = ttk.Combobox(form, textvariable=self._default_user_var, state="readonly", width=32)
        self._default_user_combo.grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Hosts prüfen Timeout (s):").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(form, textvariable=self._host_timeout_var, width=10).grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(form, text="Ordner beim Start:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 12))
        self._startup_expand_combo = ttk.Combobox(form, textvariable=self._startup_expand_var, values=list(self.STARTUP_LABELS.values()), state="readonly", width=32)
        self._startup_expand_combo.grid(row=2, column=1, sticky="ew", pady=6)
        return frame

    def _build_sources_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Quellen / Ansicht", "Steuert nur, was in der Hauptansicht angezeigt wird. Nichts davon löscht Verbindungen.")
        items = [
            ("show_winscp", "WinSCP", "Standardmäßig an"),
            ("show_ssh_config", "SSH Config", "Standardmäßig an"),
            ("show_filezilla_config", "FileZilla Config", "Neuer Weg, standardmäßig aus"),
            ("show_app_connections", "Eigene App-Verbindungen", "Standardmäßig an"),
        ]
        grid = ttk.Frame(frame, style="SettingsPanel.TFrame")
        grid.grid(row=2, column=0, sticky="nw")
        for row, (key, label, hint) in enumerate(items):
            var = tk.BooleanVar()
            self._source_visibility_vars[key] = var
            ttk.Checkbutton(grid, text=label, variable=var, command=self._on_source_visibility_changed).grid(row=row * 2, column=0, sticky="w", pady=(0, 2))
            ttk.Label(grid, text=hint, style="SettingsHint.TLabel").grid(row=row * 2 + 1, column=0, sticky="w", pady=(0, 8), padx=(24, 0))
        return frame

    def _build_users_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Schnellauswahl-Benutzer", "Ein Benutzer pro Zeile. Reihenfolge bleibt erhalten und wird in den Dialogen genutzt.")
        self._quick_users_text = scrolledtext.ScrolledText(frame, wrap="word", height=18)
        self._quick_users_text.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(2, weight=1)
        return frame

    def _build_toolbar_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Toolbar", "Lege fest, welche Buttons oben sichtbar sind. Änderungen wirken direkt.")
        grid = ttk.Frame(frame, style="SettingsPanel.TFrame")
        grid.grid(row=2, column=0, sticky="nw")
        grid.columnconfigure(0, minsize=260)
        grid.columnconfigure(1, minsize=260)
        toolbar_items = [
            ("show_select_all", "Alle auswählen"),
            ("show_deselect_all", "Alle abwählen"),
            ("show_expand_all", "Ausklappen"),
            ("show_collapse_all", "Einklappen"),
            ("show_add_connection", "+ Verbindung"),
            ("show_reload", "Neu laden"),
            ("show_open_tunnel", "Tunnel öffnen…"),
            ("show_check_hosts", "Hosts prüfen"),
            ("show_hostname_column", "Spalte Hostname"),
            ("show_port_column", "Spalte Port"),
            ("show_notes_column", "Spalte Notizen"),
        ]
        for idx, (key, label) in enumerate(toolbar_items):
            var = tk.BooleanVar()
            self._toolbar_vars[key] = var
            ttk.Checkbutton(grid, text=label, variable=var, command=self._on_toolbar_changed).grid(row=idx // 2, column=idx % 2, sticky="w", padx=(0, 28), pady=6)

        order_frame = ttk.Frame(frame, style="SettingsPanel.TFrame")
        order_frame.grid(row=3, column=0, sticky="nw", pady=(18, 0))
        ttk.Label(order_frame, text="Spalten-Reihenfolge (ohne Name):", style="SettingsValue.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self._column_order_list = tk.Listbox(order_frame, height=3, exportselection=False)
        self._column_order_list.grid(row=1, column=0, rowspan=2, sticky="w")
        btns = ttk.Frame(order_frame, style="SettingsPanel.TFrame")
        btns.grid(row=1, column=1, sticky="nw", padx=(10, 0))
        ttk.Button(btns, text="Hoch", command=lambda: self._move_column_order(-1), width=10).pack(anchor="w")
        ttk.Button(btns, text="Runter", command=lambda: self._move_column_order(1), width=10).pack(anchor="w", pady=(6, 0))
        return frame

    def _build_terminal_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Windows Terminal", "Nur optische Übergaben an Windows Terminal, keine SSH-Logik.")
        form = ttk.Frame(frame, style="SettingsPanel.TFrame")
        form.grid(row=2, column=0, sticky="nw")
        form.columnconfigure(0, minsize=220)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Profilname:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(form, textvariable=self._profile_name_var, width=32).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(form, text="Tab-Farben an Windows Terminal übergeben", variable=self._use_tab_color_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(form, text="Tab-Titel:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 12))
        self._title_mode_combo = ttk.Combobox(form, textvariable=self._title_mode_var, values=list(self.TITLE_MODE_LABELS.values()), state="readonly", width=32)
        self._title_mode_combo.grid(row=2, column=1, sticky="ew", pady=6)
        return frame

    def _build_transfer_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Export / Import", "Speichere deine Einstellungen separat oder lade sie aus einer JSON-Datei wieder ein.")
        ttk.Button(frame, text="Einstellungen exportieren…", command=self._export_settings).grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Button(frame, text="Einstellungen importieren…", command=self._import_settings).grid(row=3, column=0, sticky="w")
        return frame

    def _build_reset_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Zurücksetzen", "Trenne dauerhaft gespeicherte Einstellungen sauber vom aktuellen Ansichts-Zustand.")
        ttk.Button(frame, text="Einstellungen zurücksetzen", command=self._reset_settings).grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Button(frame, text="Farben und Ordner auf Startzustand zurücksetzen", command=self._reset_view_state).grid(row=3, column=0, sticky="w")
        return frame

    def _export_settings(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Einstellungen exportieren",
            defaultextension=".json",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
            initialfile="ssh-manager-settings.json",
        )
        if not path:
            return
        settings = self._collect_settings()
        try:
            Path(path).write_text(__import__("json").dumps(settings_to_dict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Export fehlgeschlagen", f"Datei konnte nicht gespeichert werden:\n{e}", parent=self)
            return
        ToastNotification(self._app, "Einstellungen exportiert")

    def _import_settings(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Einstellungen importieren",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            settings = load_settings_from_path(Path(path))
        except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
            messagebox.showerror("Import fehlgeschlagen", f"Datei konnte nicht gelesen werden:\n{e}", parent=self)
            return
        self._app.apply_settings(settings)
        self.load_from_app()
        ToastNotification(self._app, "Einstellungen importiert")

    def _show_section(self, key: str) -> None:
        self._active_section = key
        labels = {
            "general": "Allgemein",
            "sources": "Quellen / Ansicht",
            "users": "Schnellauswahl-Benutzer",
            "toolbar": "Toolbar",
            "terminal": "Windows Terminal",
            "transfer": "Export / Import",
            "reset": "Zurücksetzen",
        }
        for section_key, frame in self._section_frames.items():
            if section_key == key:
                frame.tkraise()
        for section_key, button in self._nav_buttons.items():
            prefix = "▸" if section_key == key else " "
            button.configure(text=f"{prefix} {labels[section_key]}")

    def load_from_app(self) -> None:
        settings = self._app.settings
        self._quick_users_text.delete("1.0", "end")
        self._quick_users_text.insert("1.0", "\n".join(settings.quick_users))
        self._default_user_combo.configure(values=settings.quick_users)
        self._default_user_var.set(settings.default_user)
        self._host_timeout_var.set(str(settings.host_check_timeout_seconds))
        self._startup_expand_var.set(self.STARTUP_LABELS.get(settings.startup_expand_mode, self.STARTUP_LABELS["remember"]))
        for key, var in self._toolbar_vars.items():
            var.set(bool(getattr(settings.toolbar, key)))
        self._column_order_list.delete(0, "end")
        for col in settings.toolbar.column_order:
            self._column_order_list.insert("end", self._column_label(col))
        for key, var in self._source_visibility_vars.items():
            var.set(bool(getattr(settings.source_visibility, key)))
        self._profile_name_var.set(settings.windows_terminal.profile_name)
        self._use_tab_color_var.set(settings.windows_terminal.use_tab_color)
        self._title_mode_var.set(self.TITLE_MODE_LABELS.get(settings.windows_terminal.title_mode, self.TITLE_MODE_LABELS["default"]))

    def _on_toolbar_changed(self) -> None:
        self._app.preview_toolbar_visibility(self._collect_toolbar_settings())

    def _column_label(self, key: str) -> str:
        return {
            "notes": "Notiz",
            "hostname": "Hostname",
            "port": "Port",
        }[key]

    def _column_key_from_label(self, label: str) -> str:
        return {
            "Notiz": "notes",
            "Hostname": "hostname",
            "Port": "port",
        }[label]

    def _move_column_order(self, direction: int) -> None:
        selection = self._column_order_list.curselection()
        if not selection:
            return
        idx = selection[0]
        new_idx = idx + direction
        if not (0 <= new_idx < self._column_order_list.size()):
            return
        value = self._column_order_list.get(idx)
        self._column_order_list.delete(idx)
        self._column_order_list.insert(new_idx, value)
        self._column_order_list.selection_set(new_idx)
        self._on_toolbar_changed()

    def _collect_toolbar_settings(self) -> ToolbarSettings:
        data = {key: var.get() for key, var in self._toolbar_vars.items()}
        data["column_order"] = [self._column_key_from_label(self._column_order_list.get(i)) for i in range(self._column_order_list.size())]
        return ToolbarSettings(**data)

    def _collect_source_visibility_settings(self) -> SourceVisibilitySettings:
        return SourceVisibilitySettings(**{key: var.get() for key, var in self._source_visibility_vars.items()})

    def _on_source_visibility_changed(self) -> None:
        self._app.preview_source_visibility(self._collect_source_visibility_settings())

    def _collect_settings(self) -> AppSettings:
        quick_users = [line.strip() for line in self._quick_users_text.get("1.0", "end").splitlines() if line.strip()]
        if not quick_users:
            raise ValueError("Mindestens ein Quick-User ist erforderlich.")
        default_user = self._default_user_var.get().strip() or quick_users[0]
        if default_user not in quick_users:
            default_user = quick_users[0]
        try:
            timeout = max(1, int(self._host_timeout_var.get().strip()))
        except ValueError as e:
            raise ValueError("Timeout muss eine ganze Zahl >= 1 sein.") from e
        startup_expand_mode = next((key for key, label in self.STARTUP_LABELS.items() if label == self._startup_expand_var.get()), "remember")
        title_mode = next((key for key, label in self.TITLE_MODE_LABELS.items() if label == self._title_mode_var.get()), "default")
        return AppSettings(
            quick_users=quick_users,
            default_user=default_user,
            toolbar=self._collect_toolbar_settings(),
            host_check_timeout_seconds=timeout,
            startup_expand_mode=startup_expand_mode,
            windows_terminal=WindowsTerminalSettings(
                profile_name=self._profile_name_var.get().strip() or "Git Bash",
                use_tab_color=self._use_tab_color_var.get(),
                title_mode=title_mode,
            ),
            source_visibility=self._collect_source_visibility_settings(),
        )

    def _save(self) -> None:
        try:
            settings = self._collect_settings()
        except ValueError as e:
            messagebox.showwarning("Einstellungen", str(e), parent=self)
            return
        self._app.apply_settings(settings)
        self._app.show_main_view()

    def _reset_settings(self) -> None:
        self._app.reset_settings()
        self.load_from_app()

    def _reset_view_state(self) -> None:
        self._app.reset_view_state()


