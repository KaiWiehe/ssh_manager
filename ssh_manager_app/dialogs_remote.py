from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Callable

from .constants import DEFAULT_USER, QUICK_USERS, _SSH_CONFIG_FILE
from .dialogs_base import _HOSTNAME_RE, _USERNAME_RE, _build_quickselect_buttons, resolve_user_dialog_defaults
from .dialogs_toast import ToastNotification
from .models import Session


def _resolve_jump_host_default_user(parent: tk.Tk) -> str:
    settings = getattr(parent, "settings", None)
    default_user = getattr(settings, "default_user", DEFAULT_USER)
    return default_user or DEFAULT_USER


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
        self._jump_user_var = tk.StringVar(value=_resolve_jump_host_default_user(parent))
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
        self._quick_users, self._default_user = resolve_user_dialog_defaults(quick_users, default_user)

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
        self._quick_users, self._default_user = resolve_user_dialog_defaults(quick_users, default_user)

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
    """Dialog für Remote-Befehl, Skript-Runbooks, Verlauf und Favoriten."""

    def __init__(self, parent: tk.Tk, target_count: int, last_command: str = "", quick_users: list[str] | None = None, default_user: str = DEFAULT_USER, history: list[dict] | None = None, favorites: list[dict] | None = None):
        super().__init__(parent)
        self.title("Befehl/Skript ausführen")
        self.geometry("980x760")
        self.minsize(860, 660)
        self.result: tuple[str, dict, bool, bool] | None = None
        self._last_command = last_command
        self._history = history or []
        self._favorites = favorites or []
        self._quick_users, self._default_user = resolve_user_dialog_defaults(quick_users, default_user)
        self.transient(parent)
        self.grab_set()
        self._build(target_count)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, target_count: int) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        ttk.Label(root, text=f"Remote-Ausführung für {target_count} Host(s)", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Ablauf: optionaler Vor-Befehl → optionales Skript mit Argumenten → optionaler Nach-Befehl.", foreground="#666666").grid(row=1, column=0, sticky="w", pady=(2, 10))

        body = ttk.PanedWindow(root, orient="horizontal")
        body.grid(row=2, column=0, sticky="nsew")

        left = ttk.Frame(body, padding=(0, 0, 10, 0))
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=1)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        mode_frame = ttk.LabelFrame(left, text="Benutzer", padding=10)
        mode_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        mode_frame.columnconfigure(1, weight=1)
        self._user_mode = tk.StringVar(value="all")
        ttk.Radiobutton(mode_frame, text="Ein Benutzer für alle Hosts", variable=self._user_mode, value="all").grid(row=0, column=0, sticky="w", columnspan=2)
        ttk.Radiobutton(mode_frame, text="Benutzer pro Host auswählen", variable=self._user_mode, value="per_host").grid(row=1, column=0, sticky="w", columnspan=2)
        self._user_var = tk.StringVar(value=self._default_user)
        ttk.Label(mode_frame, text="Benutzername:").grid(row=2, column=0, sticky="w", pady=(8, 0), padx=(0, 8))
        ttk.Entry(mode_frame, textvariable=self._user_var).grid(row=2, column=1, sticky="ew", pady=(8, 0))
        _build_quickselect_buttons(mode_frame, self._quick_users, self._user_var).grid(row=3, column=1, sticky="ew", pady=(6, 0))

        source = ttk.LabelFrame(left, text="Skript / Modus", padding=10)
        source.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        source.columnconfigure(1, weight=1)
        self._run_mode = tk.StringVar(value="command")
        ttk.Radiobutton(source, text="Nur Remote-Befehl", variable=self._run_mode, value="command", command=self._update_help).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(source, text="Lokales Skript hochladen", variable=self._run_mode, value="local_script", command=self._update_help).grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(source, text="Skript liegt auf Server", variable=self._run_mode, value="remote_script", command=self._update_help).grid(row=2, column=0, sticky="w")
        self._path_var = tk.StringVar()
        ttk.Label(source, text="Skriptpfad:").grid(row=1, column=1, sticky="w", padx=(10, 0))
        ttk.Entry(source, textvariable=self._path_var).grid(row=2, column=1, sticky="ew", padx=(10, 8))
        ttk.Button(source, text="Lokale Datei…", command=self._choose_file).grid(row=2, column=2, sticky="e")
        self._interpreter = tk.StringVar(value="bash")
        ttk.Label(source, text="Interpreter:").grid(row=0, column=1, sticky="e", padx=(10, 8))
        ttk.Combobox(source, textvariable=self._interpreter, values=("bash", "sh", "python3", "python", "direct"), width=12, state="readonly").grid(row=0, column=2, sticky="e")
        self._arguments_var = tk.StringVar()
        ttk.Label(source, text="Argumente:").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(source, textvariable=self._arguments_var).grid(row=3, column=1, columnspan=2, sticky="ew", pady=(8, 0))
        self._help_var = tk.StringVar()
        ttk.Label(source, textvariable=self._help_var, foreground="#666666", wraplength=620).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        flow = ttk.LabelFrame(left, text="Ablauf", padding=8)
        flow.grid(row=3, column=0, sticky="nsew")
        flow.columnconfigure(0, weight=1)
        flow.rowconfigure(1, weight=1)
        flow.rowconfigure(3, weight=1)
        flow.rowconfigure(5, weight=1)
        ttk.Label(flow, text="1. Vor-Befehl (optional) — z.B. cd /opt/app oder systemctl stop …").grid(row=0, column=0, sticky="w")
        self._before_text = scrolledtext.ScrolledText(flow, wrap="word", height=4)
        self._before_text.grid(row=1, column=0, sticky="nsew", pady=(2, 8))
        ttk.Label(flow, text="2. Remote-Befehl (nur bei Modus 'Nur Remote-Befehl')").grid(row=2, column=0, sticky="w")
        self._command_text = scrolledtext.ScrolledText(flow, wrap="word", height=5)
        self._command_text.grid(row=3, column=0, sticky="nsew", pady=(2, 8))
        if self._last_command:
            self._command_text.insert("1.0", self._last_command)
        ttk.Label(flow, text="3. Nach-Befehl (optional) — z.B. status prüfen oder Log anzeigen").grid(row=4, column=0, sticky="w")
        self._after_text = scrolledtext.ScrolledText(flow, wrap="word", height=4)
        self._after_text.grid(row=5, column=0, sticky="nsew", pady=(2, 0))

        favorites_box = ttk.LabelFrame(right, text="Favoriten", padding=8)
        favorites_box.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        favorites_box.columnconfigure(0, weight=1); favorites_box.rowconfigure(0, weight=1)
        self._favorites_list = tk.Listbox(favorites_box, height=9)
        self._favorites_list.grid(row=0, column=0, sticky="nsew")
        fav_buttons = ttk.Frame(favorites_box); fav_buttons.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(fav_buttons, text="Übernehmen", command=lambda: self._load_selected(self._favorites_list, self._favorites)).pack(side="left")
        ttk.Button(fav_buttons, text="Neu", command=self._add_favorite).pack(side="left", padx=4)
        ttk.Button(fav_buttons, text="Bearbeiten", command=self._edit_selected_favorite).pack(side="left")

        history_box = ttk.LabelFrame(right, text="Zuletzt verwendet", padding=8)
        history_box.grid(row=1, column=0, sticky="nsew")
        history_box.columnconfigure(0, weight=1); history_box.rowconfigure(0, weight=1)
        self._history_list = tk.Listbox(history_box, height=9)
        self._history_list.grid(row=0, column=0, sticky="nsew")
        ttk.Button(history_box, text="Übernehmen", command=lambda: self._load_selected(self._history_list, self._history)).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self._history_list.bind("<Double-Button-1>", lambda _e: self._load_selected(self._history_list, self._history))
        self._favorites_list.bind("<Double-Button-1>", lambda _e: self._load_selected(self._favorites_list, self._favorites))

        options = ttk.Frame(root)
        options.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self._close_on_success = tk.BooleanVar(value=False)
        self._save_favorite = tk.BooleanVar(value=False)
        ttk.Checkbutton(options, text="Tab direkt schließen, wenn erfolgreich", variable=self._close_on_success).pack(side="left")
        ttk.Checkbutton(options, text="Diese Ausführung als Favorit speichern", variable=self._save_favorite).pack(side="left", padx=18)
        ttk.Button(options, text="Ausführen", command=self._on_ok, width=12).pack(side="right", padx=(6, 0))
        ttk.Button(options, text="Abbrechen", command=self._on_cancel, width=10).pack(side="right")

        self._refresh_lists()
        self._update_help()
        self._command_text.focus()

    def _refresh_lists(self) -> None:
        if hasattr(self, "_favorites_list"):
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
        return (f"{name} — {note}" if note else name)[:100]

    def _choose_file(self) -> None:
        filename = filedialog.askopenfilename(parent=self, title="Skript auswählen", filetypes=(("Skripte", "*.sh *.bash *.py"), ("Alle Dateien", "*.*")))
        if filename:
            self._path_var.set(filename)
            if filename.lower().endswith(".py"):
                self._interpreter.set("python3")
            elif filename.lower().endswith((".sh", ".bash")):
                self._interpreter.set("bash")
            self._run_mode.set("local_script")
            self._update_help()

    def _update_help(self) -> None:
        if not hasattr(self, "_help_var"):
            return
        mode = self._run_mode.get()
        if mode == "command":
            self._help_var.set("Ausgefüllt werden muss nur das Feld 'Remote-Befehl'. Skriptpfad und Argumente werden ignoriert. Vor-/Nach-Befehl nutzt du hier normalerweise nicht.")
        elif mode == "local_script":
            self._help_var.set("Pflicht: lokaler Skriptpfad. Die App lädt die Datei per scp nach /tmp hoch, führt sie mit Interpreter + Argumenten aus und löscht sie danach wieder. Vor-/Nach-Befehl laufen auf dem Zielhost.")
        else:
            self._help_var.set("Pflicht: Remote-Skriptpfad. Das Skript muss auf dem Zielhost existieren. Interpreter + Argumente werden davor/dahinter gesetzt. Vor-/Nach-Befehl laufen auf dem Zielhost.")

    def _current_spec(self, *, include_metadata: bool = False) -> dict:
        mode = self._run_mode.get() if hasattr(self, "_run_mode") else "command"
        command = self._command_text.get("1.0", "end").strip()
        path = self._path_var.get().strip() if hasattr(self, "_path_var") else ""
        spec = {
            "mode": mode,
            "command": command,
            "before_command": self._before_text.get("1.0", "end").strip() if hasattr(self, "_before_text") else "",
            "after_command": self._after_text.get("1.0", "end").strip() if hasattr(self, "_after_text") else "",
            "interpreter": self._interpreter.get() if hasattr(self, "_interpreter") else "bash",
            "arguments": self._arguments_var.get().strip() if hasattr(self, "_arguments_var") else "",
            "path": path,
        }
        if mode == "local_script":
            spec["local_path"] = path
        if mode == "remote_script":
            spec["remote_path"] = path
        if include_metadata:
            spec.setdefault("name", spec.get("path") or (command.splitlines()[0] if command else "Neuer Favorit"))
            spec.setdefault("note", "")
        return spec

    def _apply_spec(self, item: dict) -> None:
        self._run_mode.set(item.get("mode", "command"))
        self._interpreter.set(item.get("interpreter", "bash"))
        self._arguments_var.set(item.get("arguments", ""))
        self._path_var.set(item.get("path") or item.get("local_path") or item.get("remote_path") or "")
        for widget, key in ((self._before_text, "before_command"), (self._command_text, "command"), (self._after_text, "after_command")):
            widget.delete("1.0", "end")
            widget.insert("1.0", item.get(key, ""))
        self._update_help()

    def _load_selected(self, listbox: tk.Listbox, items: list[dict]) -> None:
        sel = listbox.curselection()
        if not sel:
            return
        self._apply_spec(items[sel[0]])

    def _prompt_metadata(self, item: dict) -> dict | None:
        name = simpledialog.askstring("Favorit", "Name für den Favorit:", initialvalue=item.get("name") or item.get("label") or item.get("path") or "", parent=self)
        if name is None:
            return None
        note = simpledialog.askstring("Favorit", "Notiz / Erklärung:", initialvalue=item.get("note", ""), parent=self)
        if note is None:
            return None
        item = dict(item)
        item["name"] = name.strip() or item.get("path") or item.get("command", "Favorit")
        item["note"] = note.strip()
        item["label"] = item["name"]
        return item

    def _add_favorite(self) -> None:
        item = self._prompt_metadata(self._current_spec(include_metadata=True))
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
        item = self._prompt_metadata(self._favorites[index])
        if item is None:
            return
        self._favorites[index] = item
        self._apply_spec(item)
        self._refresh_lists()

    def _on_ok(self) -> None:
        legacy_mode = not hasattr(self, "_run_mode")
        if legacy_mode and not self._command_text.get("1.0", "end").strip():
            messagebox.showwarning("Kein Befehl", "Bitte einen Befehl eingeben.", parent=self)
            return
        user_value = self._user_var.get()
        user_value = user_value.strip() if isinstance(user_value, str) else ""
        if self._user_mode.get() == "all":
            if not user_value:
                messagebox.showwarning("Kein Benutzername", "Bitte einen Benutzernamen eingeben oder per Quickselect wählen.", parent=self); return
            if not _USERNAME_RE.match(user_value):
                messagebox.showwarning("Ungültiger Benutzername", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self); return
        if legacy_mode:
            command = self._command_text.get("1.0", "end").strip()
            self.result = (self._user_mode.get(), command, self._close_on_success.get())
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
            item = self._prompt_metadata({**spec, "name": spec.get("path") or spec.get("command", "")})
            if item is None:
                return
            spec.update(item)
        self.result = (self._user_mode.get(), spec, self._close_on_success.get(), save_favorite)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width(); ph = parent.winfo_height(); px = parent.winfo_x(); py = parent.winfo_y()
        w = self.winfo_width(); h = self.winfo_height()
        self.geometry(f"{w}x{h}+{px + (pw - w) // 2}+{py + (ph - h) // 2}")


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
        self._quick_users, self._default_user = resolve_user_dialog_defaults(quick_users, default_user)

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
        quick_frame = _build_quickselect_buttons(frame, self._quick_users, self._user_var)
        quick_frame.grid(row=11, column=0, columnspan=quick_count, sticky="ew", pady=(0, 8))

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
# SSHManagerApp
# ---------------------------------------------------------------------------
