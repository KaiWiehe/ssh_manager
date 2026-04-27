from __future__ import annotations

import tkinter as tk
import uuid
from tkinter import messagebox, ttk
from typing import Optional

from . import DEFAULT_USER, Session
from .constants import _APP_PREFIX, _SSH_ALIAS_PREFIX
from .dialogs_base import _HOSTNAME_RE, _USERNAME_RE


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
