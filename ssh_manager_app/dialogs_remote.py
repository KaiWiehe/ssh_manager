from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Callable

from .constants import DEFAULT_USER, QUICK_USERS, _SSH_CONFIG_FILE
from .dialogs_base import _HOSTNAME_RE, _USERNAME_RE, _build_quickselect_buttons, resolve_user_dialog_defaults
from .dialogs_toast import ToastNotification
from .secret_scripts import clear_password_fields
from .models import Session
from .ui_components import install_context_help, build_dialog_header, fit_window_to_parent


def _resolve_jump_host_default_user(parent: tk.Tk) -> str:
    settings = getattr(parent, "settings", None)
    default_user = getattr(settings, "default_user", DEFAULT_USER)
    return default_user or DEFAULT_USER


class JumpHostDialog(tk.Toplevel):
    """Dialog zum temporären Öffnen einer Session über ProxyJump."""

    def __init__(self, parent: tk.Tk, target_session: Session, sessions: list[Session], open_folders_getter: Callable[[], set[str]] | None = None):
        super().__init__(parent)
        install_context_help(self, "network", layout="grid")
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
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
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
        ttk.Label(frame, text=help_text, style="Muted.TLabel", justify="left").grid(row=1, column=0, sticky="w", pady=(0, 10))

        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._jump_host_var = tk.StringVar()
        self._jump_user_var = tk.StringVar(value=_resolve_jump_host_default_user(self.master))
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
        if not _HOSTNAME_RE.fullmatch(jump_host):
            messagebox.showwarning("Ungültiger Jumphost", "Nur Buchstaben, Ziffern, Punkte, Doppelpunkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return None
        jump_user = self._jump_user_var.get().strip()
        if jump_user and not _USERNAME_RE.fullmatch(jump_user):
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
        clear_password_fields(self)
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
        clear_password_fields(self)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.save_result = None
        clear_password_fields(self)
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
        install_context_help(self, "sshkeys")
        self.title("SSH Key übertragen")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self._target_count = target_count
        self._quick_users, self._default_user = resolve_user_dialog_defaults(quick_users, default_user)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

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
                style="Muted.TLabel",
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
            ttk.Label(frame, text="Keine *.pub-Dateien in ~/.ssh gefunden.", style="Error.TLabel").grid(
                row=2, column=0, columnspan=2, sticky="w"
            )

        # Benutzer
        ttk.Label(frame, text="Quickselect:").grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        quick_frame = _build_quickselect_buttons(frame, self._quick_users, self._user_var)
        quick_frame.grid(row=4, column=0, columnspan=quick_count, sticky="ew", pady=(0, 8))

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
        if not _USERNAME_RE.fullmatch(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (key, user)
        clear_password_fields(self)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        clear_password_fields(self)
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
        install_context_help(self, "sshkeys")
        self.title("SSH Key entfernen")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self._target_count = target_count
        self._quick_users, self._default_user = resolve_user_dialog_defaults(quick_users, default_user)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

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
                style="Muted.TLabel",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Public Key:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        pub_keys = sorted(p.name for p in (_SSH_CONFIG_FILE.parent).glob("*.pub"))
        self._key_var = tk.StringVar(value=pub_keys[0] if pub_keys else "")
        key_cb = ttk.Combobox(
            frame, textvariable=self._key_var, values=pub_keys, width=30, state="readonly" if pub_keys else "normal"
        )
        key_cb.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        if not pub_keys:
            ttk.Label(frame, text="Keine *.pub-Dateien in ~/.ssh gefunden.", style="Error.TLabel").grid(
                row=2, column=0, columnspan=2, sticky="w"
            )

        ttk.Label(frame, text="Quickselect:").grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        quick_frame = _build_quickselect_buttons(frame, self._quick_users, self._user_var)
        quick_frame.grid(row=4, column=0, columnspan=quick_count, sticky="ew", pady=(0, 8))

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
        if not _USERNAME_RE.fullmatch(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (key, user)
        clear_password_fields(self)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        clear_password_fields(self)
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


class RemoteFavoriteEditDialog(tk.Toplevel):
    """Aufgeräumter Dialog zum Anlegen/Bearbeiten eines Remote-Runner-Favoriten."""

    def __init__(self, parent: tk.Tk, item: dict, title: str = "Favorit bearbeiten"):
        super().__init__(parent)
        install_context_help(self, "runbooks")
        self.title(title)
        self.geometry("560x420")
        self.minsize(500, 360)
        self.result: dict | None = None
        self._item = dict(item)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build()
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(frame, text="Name:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self._name_var = tk.StringVar(value=self._item.get("name") or self._item.get("label") or self._item.get("path") or "")
        name_entry = ttk.Entry(frame, textvariable=self._name_var)
        name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        name_entry.focus()

        self._pinned_var = tk.BooleanVar(value=bool(self._item.get("pinned", False)))
        ttk.Checkbutton(frame, text="Oben anpinnen", variable=self._pinned_var).grid(row=1, column=1, sticky="w", pady=(0, 8))

        summary = self._summary_text(self._item)
        ttk.Label(frame, text="Ausführung:").grid(row=2, column=0, sticky="nw", padx=(0, 8))
        summary_text = scrolledtext.ScrolledText(frame, wrap="word", height=5)
        summary_text.grid(row=2, column=1, sticky="nsew", pady=(0, 10))
        summary_text.insert("1.0", summary)
        summary_text.configure(state="disabled")

        ttk.Label(frame, text="Notiz:").grid(row=3, column=0, sticky="nw", padx=(0, 8))
        self._note_text = scrolledtext.ScrolledText(frame, wrap="word", height=8)
        self._note_text.grid(row=3, column=1, sticky="nsew")
        self._note_text.insert("1.0", self._item.get("note", ""))

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Speichern", command=self._on_ok, width=12).pack(side="left", padx=4)
        ttk.Button(buttons, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=4)

    def _summary_text(self, item: dict) -> str:
        mode = item.get("mode", "command")
        if mode == "command":
            return item.get("command", "") or "Remote-Befehl"
        path = item.get("local_path") or item.get("remote_path") or item.get("path", "")
        parts = ["Lokales Skript" if mode == "local_script" else "Remote-Skript", path]
        if item.get("interpreter"):
            parts.append(f"Interpreter: {item.get('interpreter')}")
        if item.get("arguments"):
            parts.append(f"Argumente: {item.get('arguments')}")
        if item.get("before_command"):
            parts.append("Vor-Befehl: ja")
        if item.get("after_command"):
            parts.append("Nach-Befehl: ja")
        return "\n".join(p for p in parts if p)

    def _on_ok(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Kein Name", "Bitte einen Namen für den Favoriten eingeben.", parent=self)
            return
        item = dict(self._item)
        item["name"] = name
        item["label"] = name
        item["note"] = self._note_text.get("1.0", "end").strip()
        item["pinned"] = self._pinned_var.get()
        self.result = item
        clear_password_fields(self)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        clear_password_fields(self)
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        fit_window_to_parent(self, parent, 560, 420, min_width=460, min_height=340)


class RemoteCommandDialog(tk.Toplevel):
    """Dialog für Remote-Befehl, Skript-Runbooks, Verlauf und Favoriten."""

    def __init__(self, parent: tk.Tk, target_count: int, last_command: str = "", quick_users: list[str] | None = None, default_user: str = DEFAULT_USER, history: list[dict] | None = None, favorites: list[dict] | None = None, run_mode: str | None = None, editing: bool = False, reference_sessions: list[Session] | None = None):
        if run_mode not in (None, "command", "local_script", "remote_script"):
            raise ValueError("Unbekannte Remote-Aufgabe")
        super().__init__(parent)
        install_context_help(self, "remote")
        self._fixed_mode = run_mode
        self._editing = editing
        self._reference_sessions = list(reference_sessions or [])
        self.title({"command": "Befehl ausführen", "local_script": "Lokales Skript ausführen", "remote_script": "Serverskript ausführen"}.get(run_mode, "Befehl/Skript ausführen"))
        self.geometry("980x760")
        self.minsize(860, 660)
        self.result: tuple[str, dict, bool, bool] | None = None
        self._last_command = last_command
        self._history = history or []
        self._favorites = favorites or []
        self._quick_users, self._default_user = resolve_user_dialog_defaults(quick_users, default_user)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build(target_count)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, target_count: int) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        build_dialog_header(
            root,
            f"{self.title()} für {target_count} Host(s)",
            "Eingaben für diese Aufgabe konfigurieren. Gespeicherte Einträge können übernommen werden.",
        )

        body = ttk.PanedWindow(root, orient="horizontal")
        self._body = body
        body.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(body, padding=(0, 0, 10, 0))
        right = ttk.Frame(body)
        self._left, self._right = left, right
        body.add(left, weight=3)
        body.add(right, weight=1)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        mode_frame = ttk.LabelFrame(left, text="Benutzer", padding=10)
        mode_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        mode_frame.columnconfigure(1, weight=1)
        self._user_mode = tk.StringVar(value="all")
        ttk.Label(mode_frame, text="Ein Benutzer für die komplette Befehlskette:").grid(row=0, column=0, sticky="w", columnspan=2)
        self._user_var = tk.StringVar(value=self._default_user)
        ttk.Label(mode_frame, text="Benutzername:").grid(row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 8))
        ttk.Entry(mode_frame, textvariable=self._user_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        _build_quickselect_buttons(mode_frame, self._quick_users, self._user_var).grid(row=2, column=1, sticky="ew", pady=(6, 0))
        if self._editing:
            mode_frame.grid_remove()

        source = ttk.LabelFrame(left, text="Skript / Modus", padding=10)
        self._source_frame = source
        source.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        source.columnconfigure(0, weight=1)

        self._run_mode = tk.StringVar(value=self._fixed_mode or "command")
        mode_row = ttk.Frame(source)
        mode_row.grid(row=0, column=0, sticky="ew")
        ttk.Radiobutton(mode_row, text="Nur Remote-Befehl", variable=self._run_mode, value="command", command=self._update_help).pack(side="left", padx=(0, 18))
        ttk.Radiobutton(mode_row, text="Lokales Skript hochladen", variable=self._run_mode, value="local_script", command=self._update_help).pack(side="left", padx=(0, 18))
        ttk.Radiobutton(mode_row, text="Skript liegt auf Server", variable=self._run_mode, value="remote_script", command=self._update_help).pack(side="left")
        if self._fixed_mode:
            mode_row.grid_remove()
            source.configure(text=self.title())

        self._settings_container = ttk.Frame(source)
        self._settings_container.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._settings_container.columnconfigure(0, weight=1)

        self._command_settings_frame = ttk.LabelFrame(self._settings_container, text="Remote-Befehl", padding=10)
        self._command_settings_frame.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            self._command_settings_frame,
            text="Keine weiteren Einstellungen nötig. Trage den Befehl unten im Feld 'Remote-Befehl' ein.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")

        self._local_settings_frame = ttk.LabelFrame(self._settings_container, text="Lokales Skript", padding=10)
        self._local_settings_frame.columnconfigure(1, weight=1)
        self._local_path_var = tk.StringVar(value="Keine lokale Datei ausgewählt")
        ttk.Label(self._local_settings_frame, text="Datei:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._local_file_label = ttk.Label(self._local_settings_frame, textvariable=self._local_path_var, style="Muted.TLabel", wraplength=520)
        self._local_file_label.grid(row=0, column=1, sticky="w")
        self._file_button = ttk.Button(self._local_settings_frame, text="Lokale Datei…", command=self._choose_file)
        self._file_button.grid(row=0, column=2, sticky="e", padx=(8, 0))

        self._interpreter = tk.StringVar(value="bash")
        ttk.Label(self._local_settings_frame, text="Interpreter:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._local_interpreter_combo = ttk.Combobox(self._local_settings_frame, textvariable=self._interpreter, values=("bash", "sh", "python3", "python", "direct"), width=14, state="readonly")
        self._local_interpreter_combo.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self._arguments_var = tk.StringVar()
        ttk.Label(self._local_settings_frame, text="Argumente:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._local_arguments_entry = ttk.Entry(self._local_settings_frame, textvariable=self._arguments_var)
        self._local_arguments_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(self._local_settings_frame, text="Die Datei wird nach /tmp hochgeladen, ausgeführt und danach gelöscht.", style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._remote_settings_frame = ttk.LabelFrame(self._settings_container, text="Skript auf Server", padding=10)
        self._remote_settings_frame.columnconfigure(1, weight=1)
        self._remote_path_var = tk.StringVar()
        ttk.Label(self._remote_settings_frame, text="Remote-Pfad:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._path_entry = ttk.Entry(self._remote_settings_frame, textvariable=self._remote_path_var)
        self._path_entry.grid(row=0, column=1, sticky="ew")
        if self._fixed_mode == "remote_script":
            self._browse_button = ttk.Button(self._remote_settings_frame, text="Server durchsuchen…", command=self._browse_remote)
            self._browse_button.grid(row=0, column=2, padx=(6, 0))
            if not self._reference_sessions:
                self._browse_button.configure(state="disabled", text="Durchsuchen: zuerst Zielhost auswählen")
        ttk.Label(self._remote_settings_frame, text="Interpreter:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._remote_interpreter_combo = ttk.Combobox(self._remote_settings_frame, textvariable=self._interpreter, values=("bash", "sh", "python3", "python", "direct"), width=14, state="readonly")
        self._remote_interpreter_combo.grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(self._remote_settings_frame, text="Argumente:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._remote_arguments_entry = ttk.Entry(self._remote_settings_frame, textvariable=self._arguments_var)
        self._remote_arguments_entry.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(self._remote_settings_frame, text="Bei mehreren Hosts: derselbe Pfad muss überall dasselbe Skript bezeichnen. Der Browser liest nur den gewählten Referenzhost.", wraplength=460, style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._help_var = tk.StringVar()

        flow = ttk.Frame(left) if self._fixed_mode == "command" else ttk.LabelFrame(left, text="Ablauf", padding=8)
        self._flow_frame = flow
        flow.grid(row=3, column=0, sticky="nsew")
        flow.columnconfigure(0, weight=1)
        flow.rowconfigure(1, weight=1)
        flow.rowconfigure(3, weight=1)
        flow.rowconfigure(5, weight=1)
        self._before_label = ttk.Label(flow, text="1. Vor-Befehl (optional) — läuft vor dem Skript auf dem Zielhost")
        self._before_label.grid(row=0, column=0, sticky="w")
        self._before_text = scrolledtext.ScrolledText(flow, wrap="word", height=3)
        self._before_text.grid(row=1, column=0, sticky="nsew", pady=(2, 8))
        self._command_label = ttk.Label(flow, text="2. Remote-Befehl — nur im Modus 'Nur Remote-Befehl' aktiv")
        self._command_label.grid(row=2, column=0, sticky="w")
        self._command_text = scrolledtext.ScrolledText(flow, wrap="word", height=5)
        self._command_text.grid(row=3, column=0, sticky="nsew", pady=(2, 8))
        if self._last_command:
            self._command_text.insert("1.0", self._last_command)
        self._after_label = ttk.Label(flow, text="3. Nach-Befehl (optional) — läuft nach dem Skript auf dem Zielhost")
        self._after_label.grid(row=4, column=0, sticky="w")
        self._after_text = scrolledtext.ScrolledText(flow, wrap="word", height=3)
        self._after_text.grid(row=5, column=0, sticky="nsew", pady=(2, 0))
        self._advanced_flow = tk.BooleanVar(value=False)
        self._advanced_flow_button = ttk.Checkbutton(left, text="Erweiterter Ablauf: Vor-/Nach-Befehl", variable=self._advanced_flow, command=self._update_help)
        self._advanced_flow_button.grid(row=2, column=0, sticky="w", pady=(0, 8))

        library = ttk.Notebook(right)
        self._library = library
        library.grid(row=0, column=0, sticky="nsew")
        favorites_box = ttk.Frame(library, padding=8)
        history_box = ttk.Frame(library, padding=8)
        library.add(favorites_box, text="Favoriten")
        library.add(history_box, text="Verlauf")
        favorites_box.columnconfigure(0, weight=1); favorites_box.rowconfigure(0, weight=1)
        self._favorites_list = tk.Listbox(favorites_box, height=9)
        self._favorites_list.grid(row=0, column=0, sticky="nsew")
        fav_buttons = ttk.Frame(favorites_box); fav_buttons.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        for column in range(2):
            fav_buttons.columnconfigure(column, weight=1)
        ttk.Button(fav_buttons, text="Übernehmen", command=lambda: self._load_selected(self._favorites_list, self._favorites)).grid(row=0, column=0, sticky="ew", padx=(0, 3), pady=(0, 4))
        ttk.Button(fav_buttons, text="Neu", command=self._add_favorite).grid(row=0, column=1, sticky="ew", padx=(3, 0), pady=(0, 4))
        ttk.Button(fav_buttons, text="Bearbeiten", command=self._edit_selected_favorite).grid(row=1, column=0, sticky="ew", padx=(0, 3), pady=(0, 4))
        ttk.Button(fav_buttons, text="Anpinnen", command=self._toggle_pin_selected_favorite).grid(row=1, column=1, sticky="ew", padx=(3, 0), pady=(0, 4))
        ttk.Button(fav_buttons, text="Löschen", command=self._delete_selected_favorite, style="Danger.TButton").grid(row=2, column=0, columnspan=2, sticky="ew")
        if self._fixed_mode or self._editing:
            for button in fav_buttons.winfo_children():
                if button.cget("text") != "Übernehmen":
                    button.grid_remove()

        history_box.columnconfigure(0, weight=1); history_box.rowconfigure(0, weight=1)
        self._history_list = tk.Listbox(history_box, height=9)
        self._history_list.grid(row=0, column=0, sticky="nsew")
        ttk.Button(history_box, text="Übernehmen", command=lambda: self._load_selected(self._history_list, self._history), style="Accent.TButton").grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self._history_list.bind("<Double-Button-1>", lambda _e: self._load_selected(self._history_list, self._history))
        self._favorites_list.bind("<Double-Button-1>", lambda _e: self._load_selected(self._favorites_list, self._favorites))

        options = ttk.Frame(root)
        options.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        options.columnconfigure(0, weight=1)
        self._close_on_success = tk.BooleanVar(value=False)
        self._save_favorite = tk.BooleanVar(value=False)
        option_checks = ttk.Frame(options)
        option_checks.grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(option_checks, text="Tab bei Erfolg schließen", variable=self._close_on_success).pack(side="left")
        save_favorite_button = ttk.Checkbutton(option_checks, text="Als Favorit speichern", variable=self._save_favorite)
        if not self._fixed_mode and not self._editing:
            save_favorite_button.pack(side="left", padx=(18, 0))
        credentials = ttk.Frame(options)
        credentials.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._sudo_password_var = tk.StringVar()
        self._show_sudo_password = tk.BooleanVar(value=False)
        ttk.Label(credentials, text="sudo-Passwort (optional):").pack(side="left", padx=(0, 6))
        self._sudo_password_entry = ttk.Entry(credentials, textvariable=self._sudo_password_var, show="•", width=18)
        self._sudo_password_entry.pack(side="left")
        ttk.Checkbutton(
            credentials,
            text="anzeigen",
            variable=self._show_sudo_password,
            command=lambda: self._sudo_password_entry.configure(show="" if self._show_sudo_password.get() else "•"),
        ).pack(side="left", padx=(4, 0))
        if self._editing:
            option_checks.grid_remove()
            credentials.grid_remove()
        actions = ttk.Frame(options)
        actions.grid(row=0, column=1, rowspan=2, sticky="se")
        ttk.Button(actions, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left")
        ttk.Button(actions, text="Übernehmen" if self._editing else "Ausführen", command=self._on_ok, width=12, style="Accent.TButton").pack(side="left", padx=(6, 0))

        self._refresh_lists()
        self._update_help()
        if self._fixed_mode == "remote_script":
            self._path_entry.focus_set()
        elif self._fixed_mode == "local_script":
            self._file_button.focus_set()
        else:
            self._command_text.focus()

    def _refresh_lists(self) -> None:
        if hasattr(self, "_favorites_list"):
            self._favorites.sort(key=lambda item: (not bool(item.get("pinned")), str(item.get("name") or item.get("label") or "").lower()))
            self._favorites_list.delete(0, "end")
            for item in self._favorites:
                self._favorites_list.insert("end", self._item_label(item))
        if hasattr(self, "_history_list"):
            self._history_list.delete(0, "end")
            for item in self._history:
                self._history_list.insert("end", self._item_label(item))

    def _item_label(self, item: dict) -> str:
        name = item.get("name") or item.get("label") or item.get("path") or item.get("command", "")
        note = item.get("note", "")
        prefix = "★ " if item.get("pinned") else ""
        return (prefix + (f"{name} — {note}" if note else name))[:100]

    def _choose_file(self) -> None:
        filename = filedialog.askopenfilename(parent=self, title="Skript auswählen", filetypes=(("Skripte", "*.sh *.bash *.py"), ("Alle Dateien", "*.*")))
        if filename:
            self._local_path_var.set(filename)
            if filename.lower().endswith(".py"):
                self._interpreter.set("python3")
            elif filename.lower().endswith((".sh", ".bash")):
                self._interpreter.set("bash")
            self._run_mode.set("local_script")
            self._update_help()

    def _browse_remote(self):
        from .remote_browser import ReferenceBrowser
        import posixpath
        if "_browser" not in self.__dict__:
            path = self._remote_path_var.get().strip()
            self._browser = ReferenceBrowser(self._right, self._reference_sessions, self._remote_path_var.set,
                                            user_getter=self._user_var.get,
                                            initial_path=posixpath.dirname(path) if path.startswith("/") else "/",
                                            on_close=self._close_browser)
        self._library.grid_remove()
        self._browser.grid(row=0, column=0, sticky="nsew")
        self._body.pane(self._left, weight=1)
        self._body.pane(self._right, weight=1)
        fit_window_to_parent(self, self.master, 1100, 720, min_width=860, min_height=600)
        self.update_idletasks()
        self._body.sashpos(0, self._body.winfo_width() // 2)
        self._browser.load()

    def _close_browser(self):
        self._browser.generation += 1
        self._browser.grid_remove()
        self._library.grid()
        self._body.pane(self._left, weight=3)
        self._body.pane(self._right, weight=1)
        self._center_on_parent(self.master)
        self.update_idletasks()
        self._body.sashpos(0, self._body.winfo_width() * 3 // 4)

    def _set_text_state(self, widget: scrolledtext.ScrolledText, enabled: bool) -> None:
        style = ttk.Style(widget)
        background = style.lookup("TEntry", "fieldbackground") or style.lookup("TFrame", "background")
        foreground = style.lookup("TEntry", "foreground") or style.lookup("TLabel", "foreground")
        if not enabled:
            disabled_background = style.lookup("TEntry", "fieldbackground", ("disabled",))
            background = disabled_background or background
        widget.configure(
            state="normal",
            background=background,
            foreground=foreground,
            insertbackground=foreground,
        )
        widget.configure(state="normal" if enabled else "disabled")

    def _update_help(self) -> None:
        if not hasattr(self, "_help_var"):
            return
        mode = self._run_mode.get()
        for frame in (self._command_settings_frame, self._local_settings_frame, self._remote_settings_frame):
            frame.grid_remove()
        if mode == "command":
            self._command_settings_frame.grid(row=0, column=0, sticky="ew")
            self._set_text_state(self._before_text, False)
            self._set_text_state(self._after_text, False)
            self._set_text_state(self._command_text, True)
            self._command_label.configure(text="Remote-Befehl (Pflicht)")
        elif mode == "local_script":
            self._local_settings_frame.grid(row=0, column=0, sticky="ew")
            self._set_text_state(self._before_text, True)
            self._set_text_state(self._after_text, True)
            self._set_text_state(self._command_text, False)
            self._command_label.configure(text="Remote-Befehl — bei Skript-Ausführung deaktiviert")
        else:
            self._remote_settings_frame.grid(row=0, column=0, sticky="ew")
            self._set_text_state(self._before_text, True)
            self._set_text_state(self._after_text, True)
            self._set_text_state(self._command_text, False)
            self._command_label.configure(text="Remote-Befehl — bei Skript-Ausführung deaktiviert")
        # Separate task entries show only relevant fields. The legacy dialog
        # remains available for older integrations and saved specifications.
        if self.__dict__.get("_fixed_mode"):
            script = mode != "command"
            show_advanced = script and self._advanced_flow.get()
            self._source_frame.grid() if script else self._source_frame.grid_remove()
            self._flow_frame.grid() if not script or show_advanced else self._flow_frame.grid_remove()
            self._left.rowconfigure(3, weight=1 if not script or show_advanced else 0)
            for row in (1, 3, 5):
                weight = int((row == 3 and not script) or (row in (1, 5) and show_advanced))
                self._flow_frame.rowconfigure(row, weight=weight, uniform="editors" if weight else "")
            for widget in (self._before_label, self._before_text, self._after_label, self._after_text):
                widget.grid() if show_advanced else widget.grid_remove()
            self._command_label.grid_remove()
            self._command_text.grid_remove() if script else self._command_text.grid()
            self._advanced_flow_button.grid() if script else self._advanced_flow_button.grid_remove()
            compact = script and not show_advanced
            if self.__dict__.get("_compact_flow") != compact:
                self._compact_flow = compact
                browsing = "_browser" in self.__dict__ and bool(self._browser.winfo_manager())
                fit_window_to_parent(self, self.master, 1100 if browsing else 980, 720 if browsing else 520 if compact else 760,
                                     min_width=860, min_height=460 if compact else 660)

    def _current_spec(self, *, include_metadata: bool = False) -> dict:
        mode = self._run_mode.get() if hasattr(self, "_run_mode") else "command"
        command = self._command_text.get("1.0", "end").strip()
        local_path = self._local_path_var.get().strip() if hasattr(self, "_local_path_var") else ""
        if local_path == "Keine lokale Datei ausgewählt":
            local_path = ""
        remote_path = self._remote_path_var.get().strip() if hasattr(self, "_remote_path_var") else ""
        path = local_path if mode == "local_script" else remote_path
        spec = {
            "mode": mode,
            "command": command,
            "before_command": self._before_text.get("1.0", "end").strip() if hasattr(self, "_before_text") else "",
            "after_command": self._after_text.get("1.0", "end").strip() if hasattr(self, "_after_text") else "",
            "interpreter": self._interpreter.get() if hasattr(self, "_interpreter") else "bash",
            "arguments": self._arguments_var.get().strip() if hasattr(self, "_arguments_var") else "",
            "path": path,
        }
        for key in ("parameters", "name", "note", "pinned"):
            if key in self.__dict__.get("_loaded_spec", {}):
                spec[key] = self._loaded_spec[key]
        if mode == "local_script":
            spec["local_path"] = path
        if mode == "remote_script":
            spec["remote_path"] = path
        if self.__dict__.get("_fixed_mode") and mode != "command" and not self._advanced_flow.get():
            spec["before_command"] = spec["after_command"] = ""
        if include_metadata:
            spec.setdefault("name", spec.get("path") or (command.splitlines()[0] if command else "Neuer Favorit"))
            spec.setdefault("note", "")
        return spec

    def _apply_spec(self, item: dict) -> None:
        from .core import validate_run_spec
        try:
            validate_run_spec(item)
        except (ValueError, TypeError):
            messagebox.showwarning("Ungültiges Runbook", "Modus oder Interpreter wird nicht unterstützt. Der gespeicherte Eintrag bleibt unverändert.", parent=self)
            return
        if self.__dict__.get("_fixed_mode") and item.get("mode", "command") != self._fixed_mode:
            messagebox.showinfo("Andere Aufgabe", "Dieses Runbook gehört zu einer anderen Aufgabe. Öffne den passenden Skript- oder Befehl-Einstieg.", parent=self)
            return
        from copy import deepcopy
        self._loaded_spec = deepcopy(item)
        self._run_mode.set(item.get("mode", "command"))
        if self.__dict__.get("_fixed_mode"):
            self._advanced_flow.set(bool(item.get("before_command") or item.get("after_command")))
        self._interpreter.set(item.get("interpreter", "bash"))
        self._arguments_var.set(item.get("arguments", ""))
        local_path = item.get("local_path", "")
        remote_path = item.get("remote_path", "")
        path = item.get("path", "")
        self._local_path_var.set(local_path or (path if item.get("mode") == "local_script" else "") or "Keine lokale Datei ausgewählt")
        self._remote_path_var.set(remote_path or (path if item.get("mode") == "remote_script" else ""))
        for widget, key in ((self._before_text, "before_command"), (self._command_text, "command"), (self._after_text, "after_command")):
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", item.get(key, ""))
        self._update_help()

    def _load_selected(self, listbox: tk.Listbox, items: list[dict]) -> None:
        sel = listbox.curselection()
        if not sel:
            return
        self._apply_spec(items[sel[0]])

    def _prompt_metadata(self, item: dict, title: str = "Favorit bearbeiten") -> dict | None:
        dialog = RemoteFavoriteEditDialog(self, item, title=title)
        self.wait_window(dialog)
        return dialog.result

    def _add_favorite(self) -> None:
        item = self._prompt_metadata(self._current_spec(include_metadata=True), title="Favorit anlegen")
        if item is None:
            return
        self._favorites.insert(0, item)
        self._refresh_lists()

    def _edit_selected_favorite(self) -> None:
        sel = self._favorites_list.curselection()
        if not sel:
            messagebox.showinfo("Kein Favorit", "Bitte zuerst einen Favorit auswählen.", parent=self)
            return
        index = sel[0]
        item = self._prompt_metadata(self._favorites[index], title="Favorit bearbeiten")
        if item is None:
            return
        self._favorites[index] = item
        self._apply_spec(item)
        self._refresh_lists()

    def _delete_selected_favorite(self) -> None:
        sel = self._favorites_list.curselection()
        if not sel:
            messagebox.showinfo("Kein Favorit", "Bitte zuerst einen Favorit auswählen.", parent=self)
            return
        index = sel[0]
        label = self._item_label(self._favorites[index])
        if not messagebox.askyesno("Favorit löschen", f"Favorit wirklich löschen?\n\n{label}", parent=self):
            return
        del self._favorites[index]
        self._refresh_lists()

    def _toggle_pin_selected_favorite(self) -> None:
        sel = self._favorites_list.curselection()
        if not sel:
            messagebox.showinfo("Kein Favorit", "Bitte zuerst einen Favorit auswählen.", parent=self)
            return
        item = self._favorites[sel[0]]
        item["pinned"] = not bool(item.get("pinned"))
        self._refresh_lists()

    def _on_ok(self) -> None:
        legacy_mode = not hasattr(self, "_run_mode")
        if legacy_mode and not self._command_text.get("1.0", "end").strip():
            messagebox.showwarning("Kein Befehl", "Bitte einen Befehl eingeben.", parent=self)
            return
        user_value = self._user_var.get()
        user_value = user_value.strip() if isinstance(user_value, str) else ""
        if self._user_mode.get() == "all" and not self.__dict__.get("_editing", False):
            if not user_value:
                messagebox.showwarning("Kein Benutzername", "Bitte einen Benutzernamen eingeben oder per Quickselect wählen.", parent=self); return
            if not _USERNAME_RE.fullmatch(user_value):
                messagebox.showwarning("Ungültiger Benutzername", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self); return
        if legacy_mode:
            command = self._command_text.get("1.0", "end").strip()
            self.result = (self._user_mode.get(), command, self._close_on_success.get())
            clear_password_fields(self)
            self.destroy()
            return
        spec = self._current_spec()
        mode = spec["mode"]
        if mode == "command" and not spec["command"]:
            messagebox.showwarning("Kein Befehl", "Bitte einen Remote-Befehl eingeben.", parent=self); return
        if mode != "command" and not spec["path"]:
            messagebox.showwarning("Kein Skriptpfad", "Bitte einen lokalen oder Remote-Skriptpfad eingeben.", parent=self); return
        save_favorite = self._save_favorite.get()
        if save_favorite:
            item = self._prompt_metadata({**spec, "name": spec.get("path") or spec.get("command", "")}, title="Favorit speichern")
            if item is None:
                return
            spec.update(item)
        sudo_password = self._sudo_password_var.get()
        self.result = (self._user_mode.get(), spec, self._close_on_success.get(), save_favorite, sudo_password)
        clear_password_fields(self)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        clear_password_fields(self)
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        compact = self.__dict__.get("_compact_flow", False)
        fit_window_to_parent(self, parent, 980, 520 if compact else 760, min_width=720, min_height=460 if compact else 540)


class RemoteCommandConfirmDialog(tk.Toplevel):
    """Bestätigungsdialog für Remote-Befehle."""

    def __init__(self, parent: tk.Tk, command: str | dict, session_users: list[tuple[Session, str]], close_on_success: bool):
        super().__init__(parent)
        install_context_help(self, "remote")
        self.title("Remote-Befehl bestätigen")
        self.geometry("760x520")
        self.minsize(680, 420)
        self.result = False

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build(command, session_users, close_on_success)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, command: str | dict, session_users: list[tuple[Session, str]], close_on_success: bool) -> None:
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
        ttk.Label(frame, text=behavior, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 12))

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

        cmd_frame = ttk.LabelFrame(frame, text="Reihenfolge / Ausführung", padding=8)
        cmd_frame.grid(row=3, column=0, sticky="nsew")
        cmd_frame.columnconfigure(0, weight=1)
        cmd_frame.rowconfigure(0, weight=1)
        cmd_text = scrolledtext.ScrolledText(cmd_frame, wrap="word", height=8)
        cmd_text.grid(row=0, column=0, sticky="nsew")
        cmd_text.insert("1.0", self._format_execution_preview(command))
        cmd_text.configure(state="disabled")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, pady=(14, 0))
        ttk.Button(btn_frame, text="Ausführen", command=self._on_ok, width=12).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=4)


    def _format_execution_preview(self, command: str | dict) -> str:
        if not isinstance(command, dict):
            return str(command)
        mode = command.get("mode", "command")
        lines: list[str] = []
        if mode == "command":
            lines.append("1. Remote-Befehl:")
            lines.append(command.get("command", ""))
            return "\n".join(lines).strip()
        step = 1
        before = command.get("before_command", "").strip()
        if before:
            lines.append(f"{step}. Vor-Befehl:")
            lines.append(before)
            lines.append("")
            step += 1
        if mode == "local_script":
            lines.append(f"{step}. Lokales Skript hochladen und ausführen:")
            lines.append(command.get("local_path") or command.get("path", ""))
        else:
            lines.append(f"{step}. Remote-Skript ausführen:")
            lines.append(command.get("remote_path") or command.get("path", ""))
        interpreter = command.get("interpreter", "")
        arguments = command.get("arguments", "")
        if interpreter:
            lines.append(f"Interpreter: {interpreter}")
        if arguments:
            lines.append(f"Argumente: {arguments}")
        step += 1
        after = command.get("after_command", "").strip()
        if after:
            lines.append("")
            lines.append(f"{step}. Nach-Befehl:")
            lines.append(after)
        return "\n".join(lines).strip()
    def _on_ok(self) -> None:
        self.result = True
        clear_password_fields(self)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        clear_password_fields(self)
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        fit_window_to_parent(self, parent, 760, 520, min_width=620, min_height=380)

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
        install_context_help(self, "tunnels")
        self.title("Tunnel öffnen")
        self.resizable(True, True)
        self.result: tuple[str, int, str, int, str] | None = None
        self._session = session
        self._quick_users, self._default_user = resolve_user_dialog_defaults(quick_users, default_user)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build()
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        buttons = ttk.Frame(self, padding=12)
        buttons.pack(side="bottom", fill="x")
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        frame = ttk.Frame(canvas, padding=16)
        window = canvas.create_window(0, 0, window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        frame.columnconfigure(1, weight=1)

        # Erklärung
        intro = ttk.Frame(frame)
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(
            intro,
            text="Was möchtest du erreichen?",
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w")
        self._tunnel_kind = tk.StringVar(value="direct")
        ttk.Radiobutton(intro, text="Dienst auf dem SSH-Server", variable=self._tunnel_kind, value="direct", command=self._update_tunnel_route).pack(anchor="w")
        ttk.Radiobutton(intro, text="Internen Dienst über den SSH-Server", variable=self._tunnel_kind, value="internal", command=self._update_tunnel_route).pack(anchor="w")
        self._port_preset = tk.StringVar(value="Eigene Ports")
        preset = ttk.Combobox(intro, textvariable=self._port_preset, values=("Eigene Ports", "PostgreSQL", "MySQL", "HTTP", "HTTPS"), state="readonly")
        preset.pack(anchor="w", pady=5)
        preset.bind("<<ComboboxSelected>>", lambda _: self._apply_tunnel_preset())
        self._tunnel_route = tk.StringVar()
        ttk.Label(intro, textvariable=self._tunnel_route, wraplength=560).pack(anchor="w", fill="x", pady=4)

        # SSH-Server
        ttk.Label(frame, text="SSH-Server:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        prefill = self._session.hostname if self._session else ""
        self._jumphost_var = tk.StringVar(value=prefill)
        ttk.Entry(frame, textvariable=self._jumphost_var, width=30).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(frame, text="Server, zu dem SSH sich verbindet.", style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Separator(frame, orient="horizontal").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Port Forwarding
        ttk.Label(frame, text="Lokaler Port:").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self._local_port_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._local_port_var, width=10).grid(
            row=4, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(frame, text="Port auf deinem PC (z. B. 3306).", style="Muted.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        self._remote_host_label = ttk.Label(frame, text="Interner Zielserver:")
        self._remote_host_label.grid(row=6, column=0, sticky="w", pady=(0, 4))
        self._remote_host_var = tk.StringVar()
        self._remote_host_entry = ttk.Entry(frame, textvariable=self._remote_host_var, width=30)
        self._remote_host_entry.grid(row=6, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))

        ttk.Label(frame, text="Zielport:").grid(row=7, column=0, sticky="w", pady=(0, 4))
        self._remote_port_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._remote_port_var, width=10).grid(
            row=7, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(
            frame,
            text="Der Zielport gehört zum gewählten Dienst. Im internen Modus den erreichbaren Zielserver angeben.",
            wraplength=560,
            style="Muted.TLabel",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Separator(frame, orient="horizontal").grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Benutzer
        ttk.Label(frame, text="Quickselect:").grid(row=10, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        quick_frame = _build_quickselect_buttons(frame, self._quick_users, self._user_var)
        quick_frame.grid(row=11, column=0, columnspan=quick_count, sticky="ew", pady=(0, 8))

        ttk.Label(frame, text="Benutzername:").grid(row=12, column=0, sticky="w", pady=(0, 4))
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=13, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.focus()

        ttk.Button(buttons, text="Tunnel öffnen", command=self._on_ok, width=16).pack(side="right", padx=4)
        ttk.Button(buttons, text="Abbrechen", command=self._on_cancel, width=12).pack(side="right", padx=4)
        for variable in (self._jumphost_var, self._local_port_var, self._remote_host_var, self._remote_port_var):
            variable.trace_add("write", lambda *_: self._update_tunnel_route())
        self._update_tunnel_route()

    def _update_tunnel_route(self):
        if "_remote_host_entry" not in self.__dict__:
            return
        direct = self._tunnel_kind.get() == "direct"
        for widget in (self._remote_host_label, self._remote_host_entry):
            widget.grid_remove() if direct else widget.grid()
        target = "localhost" if direct else self._remote_host_var.get() or "interner Zielserver"
        self._tunnel_route.set(f"PC localhost:{self._local_port_var.get() or '…'} → SSH {self._jumphost_var.get() or '…'} → {target}:{self._remote_port_var.get() or '…'}")

    def _apply_tunnel_preset(self):
        ports = {"PostgreSQL": (5432, 5432), "MySQL": (3306, 3306), "HTTP": (8080, 80), "HTTPS": (8443, 443)}
        if self._port_preset.get() in ports:
            local, remote = ports[self._port_preset.get()]
            self._local_port_var.set(str(local))
            self._remote_port_var.set(str(remote))

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
        if not _HOSTNAME_RE.fullmatch(ssh_server):
            messagebox.showwarning("Ungültiger SSH-Server", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return
        local_port = self._parse_port(self._local_port_var, "Lokaler Port")
        if local_port is None:
            return
        remote_host = self._remote_host_var.get().strip() or "localhost"
        if "_tunnel_kind" in self.__dict__:
            if self._tunnel_kind.get() == "direct":
                remote_host = "localhost"
            elif not self._remote_host_var.get().strip():
                messagebox.showwarning("Zielserver fehlt", "Für einen internen Dienst dessen Zielserver angeben.", parent=self)
                return
        if not _HOSTNAME_RE.fullmatch(remote_host):
            messagebox.showwarning("Ungültiger Zielserver", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return
        remote_port = self._parse_port(self._remote_port_var, "Zielport")
        if remote_port is None:
            return
        user = self._user_var.get().strip()
        if not user:
            return
        if not _USERNAME_RE.fullmatch(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (ssh_server, local_port, remote_host, remote_port, user)
        clear_password_fields(self)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        clear_password_fields(self)
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        fit_window_to_parent(self, parent, 660, 690, min_width=500, min_height=380)
