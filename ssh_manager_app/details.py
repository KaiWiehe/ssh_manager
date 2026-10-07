from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

SOURCE_NAMES = {"winscp": "WinSCP (Registry)", "ssh_config": "SSH Config (live)",
                "filezilla_config": "FileZilla Config (live)", "app": "Eigene App-Verbindung",
                "ssh_alias": "Eigene Alias-Kopie (SSH Config)"}


def session_detail_text(session, overrides, default_user):
    if session.is_ssh_config_session:
        user = f"{session.username or 'durch SSH ermittelt'} (SSH-Konfiguration; kein Benutzerdialog)"
    elif session.key in overrides:
        user = f"{session.username or overrides[session.key]} (App-Override)"
    elif session.username:
        user = f"{session.username} ({'eigene Verbindung' if session.source == 'app' else 'importierte Quelle'})"
    else:
        user = f"wird beim Verbinden gefragt; Vorschlag: {default_user}"
    editable = session.source in ("app", "ssh_alias")
    return (f"Host: {session.hostname}\nPort: {session.port}\nBenutzer: {user}\n"
            f"Quelle: {SOURCE_NAMES.get(session.source, session.source)}\nOrdner: {session.folder_key or 'ohne Ordner'}\n"
            + (f"SSH-Alias: {session.display_name}\n" if session.is_ssh_config_session else "")
            + ("Verbindung ist in der App bearbeitbar." if editable else "Host und Port werden aus der Quelle gelesen. Benutzer, Notiz und Farbe werden nur in der App angepasst."))


class SessionDetailsPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self.session = None
        self.title = tk.StringVar(value="Verbindungsdetails")
        self.info = tk.StringVar(value="Eine Verbindung im Baum fokussieren.")
        ttk.Label(self, textvariable=self.title, font=("Segoe UI", 11, "bold"), wraplength=270).pack(anchor="w", fill="x")
        ttk.Label(self, textvariable=self.info, wraplength=270, justify="left").pack(anchor="w", fill="x", pady=10)
        ttk.Label(self, text="App-interne Notiz").pack(anchor="w")
        self.note = ScrolledText(self, height=6, width=28, wrap="word", state="disabled")
        self.note.pack(fill="both", expand=True, pady=(5, 10))
        self.edit = ttk.Button(self, text="Verbindung bearbeiten…", command=self.edit_session, state="disabled")
        self.edit.pack(fill="x", pady=3)
        self.edit_note = ttk.Button(self, text="Notiz bearbeiten…", command=self.edit_session_note, state="disabled")
        self.edit_note.pack(fill="x", pady=3)

    def refresh(self, _event=None):
        self.session = self.app._tree.get_single_context_session()
        session = self.session
        self.title.set(session.display_name if session else "Verbindungsdetails")
        self.info.set(session_detail_text(session, self.app._session_user_overrides, self.app.settings.default_user) if session else "Eine Verbindung im Baum fokussieren.")
        self.note.configure(state="normal")
        self.note.delete("1.0", "end")
        if session:
            self.note.insert("1.0", self.app._notes.get(session.key, ""))
        self.note.configure(state="disabled")
        self.edit.configure(state="normal" if session else "disabled", text="Verbindung bearbeiten…" if session and session.source in ("app", "ssh_alias") else "App-Anpassungen bearbeiten…")
        self.edit_note.configure(state="normal" if session else "disabled")

    def edit_session(self):
        if not self.session:
            return
        from .actions_sessions import edit_session, edit_session_details
        (edit_session if self.session.source in ("app", "ssh_alias") else edit_session_details)(self.app, self.session)
        self.refresh()

    def edit_session_note(self):
        if not self.session:
            return
        from .actions_notes import edit_session_note
        edit_session_note(self.app, self.session)
        self.refresh()


def toggle_session_details(app):
    panel = app._details_panel
    pane = app._session_area
    if str(panel) in tuple(map(str, pane.panes())):
        pane.forget(panel)
    else:
        pane.add(panel, weight=1)
        panel.refresh()
