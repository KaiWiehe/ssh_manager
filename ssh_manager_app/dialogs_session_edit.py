from __future__ import annotations

import tkinter as tk
import uuid
from tkinter import messagebox, ttk
from typing import Optional

from . import Session
from .constants import QUICK_USERS, _APP_PREFIX, _SSH_ALIAS_PREFIX
from .dialogs_base import _HOSTNAME_RE, _USERNAME_RE, _build_quickselect_buttons
from .ui_components import build_dialog_actions, build_dialog_header, center_on_parent, set_validation_state


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
        quick_users: list[str] | None = None,
    ):
        super().__init__(parent)
        self._existing_session = session
        self._duplicate = duplicate
        self._existing_folders = existing_folders
        self._quick_users = list(quick_users) if quick_users else list(QUICK_USERS)
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
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._build(folder_preset)
        self._center_on_parent(parent)

        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, folder_preset: str) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        build_dialog_header(
            frame,
            self.title(),
            "Verbindungsdaten und optionale Notizen an einem Ort pflegen.",
            columnspan=2,
        )

        self._mode_var = tk.StringVar(value=self._initial_mode)
        content_row = 1

        # Modus-Auswahl (nur wenn Aliases vorhanden und kein Bearbeitungsmodus)
        can_switch = bool(self._ssh_aliases) and not self._existing_session
        if can_switch:
            mode_frame = ttk.Frame(frame)
            mode_frame.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))
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
            content_row = 2

        s = self._existing_session

        # --- SSH-Alias Frame ---
        self._alias_frame = ttk.Frame(frame)
        self._alias_frame.columnconfigure(1, weight=1)
        self._alias_frame.grid(row=content_row, column=0, columnspan=2, sticky="ew")

        ttk.Label(self._alias_frame, text="Alias:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        alias_val = self._alias_preset or (s.display_name if s and s.is_ssh_alias_copy else "")
        self._alias_var = tk.StringVar(value=alias_val)
        alias_cb_state = "readonly" if self._alias_preset else "normal"
        self._alias_combo = ttk.Combobox(
            self._alias_frame, textvariable=self._alias_var,
            values=self._ssh_aliases, width=30, state=alias_cb_state,
        )
        self._alias_combo.grid(row=0, column=1, sticky="ew")

        ttk.Label(self._alias_frame, text="Ordner:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        alias_folder_val = (s.folder_key if s and s.is_ssh_alias_copy else folder_preset)
        self._alias_folder_var = tk.StringVar(value=alias_folder_val)
        self._alias_folder_combo = ttk.Combobox(
            self._alias_frame, textvariable=self._alias_folder_var,
            values=self._existing_folders, width=30,
        )
        self._alias_folder_combo.grid(row=1, column=1, sticky="ew")

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
        self._name_entry = ttk.Entry(self._verbindung_frame, textvariable=self._name_var, width=32)
        self._name_entry.grid(row=0, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Ordner:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self._folder_var = tk.StringVar(value=s.folder_key if (s and s.is_app_session) else folder_preset)
        ttk.Combobox(
            self._verbindung_frame, textvariable=self._folder_var,
            values=self._existing_folders, width=30,
        ).grid(row=1, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Hostname:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        self._host_var = tk.StringVar(value=s.hostname if (s and s.is_app_session) else "")
        self._host_entry = ttk.Entry(self._verbindung_frame, textvariable=self._host_var, width=32)
        self._host_entry.grid(row=2, column=1, sticky="ew")

        self._user_var = tk.StringVar(value=s.username if (s and s.is_app_session) else "")
        ttk.Label(self._verbindung_frame, text="Quickselect:").grid(row=3, column=0, sticky="nw", pady=4, padx=(0, 8))
        quick_frame = _build_quickselect_buttons(self._verbindung_frame, self._quick_users, self._user_var)
        quick_frame.grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(self._verbindung_frame, text="Benutzername:").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        user_entry = ttk.Entry(self._verbindung_frame, textvariable=self._user_var, width=32)
        user_entry.grid(row=4, column=1, sticky="ew")
        self._user_entry = user_entry
        active_text = f"Aktiv gesetzt: {s.username}" if (s and s.is_app_session and s.username) else "Aktiv gesetzt: keiner — beim Verbinden fragen"
        ttk.Label(self._verbindung_frame, text=active_text, style="SettingsHint.TLabel").grid(row=5, column=1, sticky="w", pady=(2, 4))

        ttk.Label(self._verbindung_frame, text="Port:").grid(row=6, column=0, sticky="w", pady=4, padx=(0, 8))
        self._port_var = tk.StringVar(value=str(s.port) if (s and s.is_app_session) else "22")
        self._port_entry = ttk.Entry(self._verbindung_frame, textvariable=self._port_var, width=8)
        self._port_entry.grid(row=6, column=1, sticky="w")

        ttk.Label(self._verbindung_frame, text="Notizen:").grid(row=7, column=0, sticky="nw", pady=4, padx=(0, 8))
        self._note_text = tk.Text(self._verbindung_frame, width=32, height=4)
        self._note_text.grid(row=7, column=1, sticky="ew", pady=4)
        if self.note_result:
            self._note_text.insert("1.0", self.note_result)

        self._validation_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._validation_var, style="ValidationError.TLabel").grid(
            row=content_row + 1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        build_dialog_actions(
            frame,
            row=content_row + 2,
            columnspan=2,
            primary_text="Speichern",
            primary_command=self._on_ok,
            cancel_command=self._on_cancel,
        )

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
            set_validation_state(
                getattr(self, "_alias_combo", None),
                getattr(self, "_validation_var", None),
                "Bitte einen Alias auswählen.",
                normal_style="TCombobox",
                invalid_style="Invalid.TCombobox",
            )
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Alias auswählen.", parent=self)
            return
        folder_path = [p for p in folder_str.split("/") if p]
        if not folder_path:
            set_validation_state(
                getattr(self, "_alias_folder_combo", None),
                getattr(self, "_validation_var", None),
                "Bitte einen Ordner eingeben.",
                normal_style="TCombobox",
                invalid_style="Invalid.TCombobox",
            )
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
            self._show_validation_error("_name_entry", "Bitte einen Namen eingeben.")
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Namen eingeben.", parent=self)
            return
        if not hostname:
            self._show_validation_error("_host_entry", "Bitte einen Hostnamen eingeben.")
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Hostnamen eingeben.", parent=self)
            return
        if not _HOSTNAME_RE.match(hostname):
            self._show_validation_error("_host_entry", "Der Hostname enthält ungültige Zeichen.")
            messagebox.showwarning(
                "Ungültiger Hostname",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche, Unterstriche und Doppelpunkte erlaubt.",
                parent=self,
            )
            return
        if username and not _USERNAME_RE.match(username):
            self._show_validation_error("_user_entry", "Der Benutzername enthält ungültige Zeichen.")
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
            self._show_validation_error("_port_entry", "Port muss zwischen 1 und 65535 liegen.")
            messagebox.showwarning("Ungültiger Port", "Port muss eine Zahl zwischen 1 und 65535 sein.", parent=self)
            return

        set_validation_state(None, getattr(self, "_validation_var", None))

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

    def _show_validation_error(self, widget_name: str, message: str) -> None:
        set_validation_state(
            getattr(self, widget_name, None),
            getattr(self, "_validation_var", None),
            message,
        )

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        center_on_parent(self, parent)


# ---------------------------------------------------------------------------
# SshConfigInspectDialog
# ---------------------------------------------------------------------------
