"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

import json
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ssh_manager_app import (
    AppSettings,
    REGISTRY_PATH,
    ToolbarSettings,
    WindowsTerminalSettings,
    SourceVisibilitySettings,
    Session,
    WINDOW_MIN_SIZE,
    WINDOW_TITLE,
    default_settings,
    load_app_sessions,
    load_filezilla_config_sessions,
    load_notes,
    load_settings,
    load_ssh_config_sessions,
    load_ui_state,
    save_app_sessions,
    save_notes,
    save_settings,
    save_ui_state,
)
from ssh_manager_app.constants import _SSH_CONFIG_DEFAULT_FOLDER, _SSH_CONFIG_FILE

from ssh_manager_app.core import (
    RegistryReader,
    TerminalLauncher,
    _create_checkbox_images,
    build_jump_wt_command,
    build_remote_command_wt_command,
    build_ssh_tunnel_command,
)

from ssh_manager_app.tree import SessionTree
from ssh_manager_app.ui import build_main_ui, configure_app_styles

from ssh_manager_app.dialogs import (
    MoveFolderDialog,
    RemoteCommandConfirmDialog,
    RemoteCommandDialog,
    SessionEditDialog,
    SettingsView,
    SshConfigInspectDialog,
    SshCopyIdDialog,
    SshRemoveKeyDialog,
    SshTunnelDialog,
    ToastNotification,
    UserDialog,
)

class SSHManagerApp(tk.Tk):
    """Hauptfenster der SSH-Manager Applikation."""

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.minsize(*WINDOW_MIN_SIZE)
        self.geometry("750x550")

        configure_app_styles(self)

        # Registry laden
        try:
            reader = RegistryReader()
            winscp_sessions = reader.load_sessions()
        except OSError as e:
            messagebox.showerror(
                "Registry-Fehler",
                f"WinSCP-Sessions konnten nicht geladen werden:\n{e}\n\n"
                f"Pfad: HKCU\\{REGISTRY_PATH}"
            )
            winscp_sessions = []

        self.settings = load_settings()
        self._startup_settings = load_settings()
        self._winscp_sessions = winscp_sessions
        self._filezilla_sessions = load_filezilla_config_sessions()

        # App-eigene Sessions und SSH-Config-Sessions laden und mergen
        self._app_sessions: list[Session] = load_app_sessions()
        self._notes = load_notes()
        self._ssh_config_sessions = load_ssh_config_sessions()
        self._sessions = self._build_visible_sessions()

        # Checkbox-Images (nach Tk-Initialisierung erzeugen!)
        self._img_unchecked, self._img_checked = _create_checkbox_images(self)

        self._initial_open_folders, self._initial_session_colors, self._initial_toolbar_search_texts = load_ui_state()
        if self.settings.startup_expand_mode == "expanded":
            self._initial_open_folders = {s.folder_key for s in self._sessions if s.folder_key}
        elif self.settings.startup_expand_mode == "collapsed":
            self._initial_open_folders = set()
        self._toolbar_buttons: dict[str, ttk.Button] = {}
        self._main_frame: ttk.Frame | None = None
        self._settings_view: SettingsView | None = None
        build_main_ui(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _add_search_history_entry(self, value: str) -> None:
        query = value.strip()
        if len(query) < 2:
            return
        self._search_history = [item for item in self._search_history if item != query]
        self._search_history.insert(0, query)
        self._search_history = self._search_history[:10]
        self._persist_ui_state()

    def _apply_search_history_entry(self, value: str) -> None:
        self._search_var.set(value)
        self._search_entry.icursor("end")
        self._search_entry.focus_set()

    def _show_search_history_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)
        if self._search_history:
            for item in self._search_history:
                menu.add_command(label=item, command=lambda v=item: self._apply_search_history_entry(v))
            menu.add_separator()
            menu.add_command(label="Verlauf leeren", command=self._clear_search_history)
        else:
            menu.add_command(label="Kein Suchverlauf", state=tk.DISABLED)
        x = self._search_history_btn.winfo_rootx()
        y = self._search_history_btn.winfo_rooty() + self._search_history_btn.winfo_height()
        menu.tk_popup(x, y)

    def _clear_search_history(self) -> None:
        self._search_history = []
        self._persist_ui_state()

    def _build_visible_sessions(self) -> list[Session]:
        visible: list[Session] = []
        if self.settings.source_visibility.show_winscp:
            visible.extend(self._winscp_sessions)
        if self.settings.source_visibility.show_app_connections:
            visible.extend(self._app_sessions)
        if self.settings.source_visibility.show_ssh_config:
            visible.extend(self._ssh_config_sessions)
        if self.settings.source_visibility.show_filezilla_config:
            visible.extend(self._filezilla_sessions)
        return sorted(
            visible,
            key=lambda s: (0 if s.folder_key == _SSH_CONFIG_DEFAULT_FOLDER else 1, s.folder_key.lower(), s.display_name.lower()),
        )

    def _layout_toolbar_buttons(self) -> None:
        col = 2
        order = [
            "show_select_all",
            "show_deselect_all",
            "show_expand_all",
            "show_collapse_all",
            "show_add_connection",
            "show_reload",
            "show_open_tunnel",
            "show_check_hosts",
        ]
        for key in order:
            btn = self._toolbar_buttons[key]
            btn.grid_forget()
            if getattr(self.settings.toolbar, key):
                padx = (8, 2) if key == "show_add_connection" else (2, 2)
                if key == "show_check_hosts":
                    padx = (2, 0)
                btn.grid(row=0, column=col, padx=padx)
                col += 1

    def preview_toolbar_visibility(self, toolbar_settings: ToolbarSettings) -> None:
        self.settings.toolbar = toolbar_settings
        self._layout_toolbar_buttons()
        self._tree.update_toolbar_settings(toolbar_settings)

    def preview_source_visibility(self, source_visibility: SourceVisibilitySettings) -> None:
        self.settings.source_visibility = source_visibility
        self._sessions = self._build_visible_sessions()
        self._tree.refresh(self._sessions)
        self._persist_ui_state()

    def _edit_session_note(self, session: Session) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Notiz bearbeiten")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text=f"Notiz für {session.display_name}:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        note_text = tk.Text(frame, width=48, height=6)
        note_text.grid(row=1, column=0, sticky="ew")
        current = self._notes.get(session.key, "")
        if current:
            note_text.insert("1.0", current)
        note_text.focus_set()

        result = {"saved": False}

        def on_ok() -> None:
            note = note_text.get("1.0", "end").strip()
            if note:
                self._notes[session.key] = note
            else:
                self._notes.pop(session.key, None)
            save_notes(self._notes)
            result["saved"] = True
            dialog.destroy()

        def on_cancel() -> None:
            dialog.destroy()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=on_cancel, width=10).pack(side="left", padx=4)

        dialog.update_idletasks()
        pw = self.winfo_width()
        ph = self.winfo_height()
        px = self.winfo_x()
        py = self.winfo_y()
        w = dialog.winfo_reqwidth()
        h = dialog.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.bind("<Escape>", lambda _e: on_cancel())
        dialog.bind("<Control-Return>", lambda _e: on_ok())
        self.wait_window(dialog)
        if result["saved"]:
            self._tree.refresh(self._sessions)
            self._update_notes_info(session)
            self._persist_ui_state()

    def get_default_user(self) -> str:
        return self.settings.default_user

    def get_quick_users(self) -> list[str]:
        return list(self.settings.quick_users)

    def get_terminal_settings(self) -> WindowsTerminalSettings:
        return self.settings.windows_terminal

    def _export_settings_dialog(self) -> None:
        if self._settings_view is None:
            return
        self._settings_view._export_settings()

    def _import_settings_dialog(self) -> None:
        if self._settings_view is None:
            return
        self._settings_view._import_settings()

    def _persist_ui_state(self) -> None:
        save_ui_state(
            self._tree.get_open_folders(),
            self._tree.get_session_colors(),
            {
                "main": self._search_var.get(),
                "last_remote_command": self._initial_toolbar_search_texts.get("last_remote_command", ""),
                "search_history": list(self._search_history),
            },
        )

    def show_settings_view(self) -> None:
        if self._settings_view is None or self._main_frame is None:
            return
        self._settings_view.load_from_app()
        self._main_frame.grid_remove()
        self._settings_view.grid(row=0, column=0, sticky="nsew")

    def show_main_view(self) -> None:
        if self._settings_view is not None:
            self._settings_view.grid_remove()
        if self._main_frame is not None:
            self._main_frame.grid()
        self._layout_toolbar_buttons()

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        save_settings(settings)
        self._layout_toolbar_buttons()
        self._search_entry.focus_set()
        ToastNotification(self, "Einstellungen gespeichert")

    def reset_settings(self) -> None:
        self.apply_settings(default_settings())
        if self._settings_view is not None:
            self._settings_view.load_from_app()

    def _reset_session_colors(self) -> None:
        for session_key in list(self._tree.get_session_colors().keys()):
            self._tree.set_session_color(session_key, None)
        ToastNotification(self, "Farben zurückgesetzt")

    def reset_view_state(self) -> None:
        self._search_var.set("")
        self._tree.populate(self._sessions, open_folders=set(self._initial_open_folders))
        current_colors = set(self._tree.get_session_colors())
        startup_colors = dict(self._initial_session_colors)
        for session_key in current_colors | set(startup_colors):
            self._tree.set_session_color(session_key, startup_colors.get(session_key))
        ToastNotification(self, "Ansicht auf Startzustand zurückgesetzt")

    def _invert_selection(self) -> None:
        self._tree.invert_checked()

    def _update_notes_info(self, session: Session | None = None) -> None:
        if not hasattr(self, "_notes_info_var"):
            return
        if session is None:
            self._notes_info_var.set("Notizinfo: Zeige den Mauszeiger auf Name oder Notiz, oder nutze Rechtsklick → Notiz bearbeiten…")
            return
        note = self._notes.get(session.key, "").strip()
        if note:
            self._notes_info_var.set(f"Notiz für {session.display_name}: {note}")
        else:
            self._notes_info_var.set(f"Notiz für {session.display_name}: Keine Notiz hinterlegt")

    def _on_selection_changed(self, count: int) -> None:
        """Callback vom SessionTree – aktualisiert den Verbinden-Button."""
        if count > 0:
            self._connect_btn.config(
                text=f"Verbinden ({count} ausgewählt)",
                state=tk.NORMAL,
            )
        else:
            self._connect_btn.config(text="Verbinden", state=tk.DISABLED)

    def _on_search_changed(self) -> None:
        value = self._search_var.get()
        self._tree.filter(value)
        self._persist_ui_state()
        self.after_cancel(self._search_history_after_id) if getattr(self, '_search_history_after_id', None) else None
        query = value.strip()
        if len(query) >= 2:
            self._search_history_after_id = self.after(450, lambda q=query: self._add_search_history_entry(q))
        else:
            self._search_history_after_id = None

    def _select_all(self) -> None:
        self._tree.set_all_checked(True)

    def _deselect_all(self) -> None:
        self._tree.set_all_checked(False)

    def _expand_all(self) -> None:
        self._tree.expand_all()

    def _collapse_all(self) -> None:
        self._tree.collapse_all()

    def _on_connect(self) -> None:
        selected = self._tree.get_selected_sessions()
        if not selected:
            return
        dialog = UserDialog(self, quick_users=self.get_quick_users(), default_user=self.get_default_user())
        self.wait_window(dialog)
        if dialog.result is None:
            return  # Abbrechen gedrückt
        user = dialog.result
        try:
            TerminalLauncher.launch(selected, user, self._tree.get_session_colors(), terminal_settings=self.get_terminal_settings())
        except Exception as e:
            messagebox.showerror("Fehler beim Starten", str(e))

    def _resolve_single_session_user(self, session: Session, title: str = "Benutzername auswählen") -> str | None:
        """Löst den Benutzernamen für genau eine Session auf."""
        if session.is_ssh_config_session and session.username:
            return session.username
        dialog = UserDialog(self, title=title, quick_users=self.get_quick_users(), default_user=self.get_default_user())
        self.wait_window(dialog)
        return dialog.result

    def _quick_connect_session(self, session: Session) -> None:
        """Öffnet eine einzelne Session direkt (via Doppelklick oder Kontextmenü)."""
        colors = self._tree.get_session_colors()
        user = self._resolve_single_session_user(session)
        if user is None and not (session.is_ssh_config_session and session.username):
            return
        try:
            TerminalLauncher.launch([session], user or "", colors, terminal_settings=self.get_terminal_settings())
        except Exception as e:
            messagebox.showerror("Fehler beim Starten", str(e))

    def _get_all_folder_names(self) -> list[str]:
        """Gibt alle bekannten Ordnernamen aus allen Session-Quellen zurück."""
        folders = set()
        for s in self._sessions:
            if s.folder_key:
                folders.add(s.folder_key)
        return sorted(folders)

    def _get_ssh_aliases(self) -> list[str]:
        """Gibt alle SSH-Config-Aliases zurück (für Alias-Picker im Dialog)."""
        return sorted(s.display_name for s in self._sessions if s.source == "ssh_config")

    def _rebuild_sessions(self, *, reload_winscp: bool = False) -> None:
        """Merged alle Session-Quellen und aktualisiert den Baum."""
        self._ssh_config_sessions = load_ssh_config_sessions()
        self._filezilla_sessions = load_filezilla_config_sessions()
        if reload_winscp:
            try:
                self._winscp_sessions = RegistryReader().load_sessions()
            except OSError as e:
                messagebox.showerror(
                    "Registry-Fehler",
                    f"WinSCP-Sessions konnten nicht geladen werden:\n{e}\n\n"
                    f"Pfad: HKCU\\{REGISTRY_PATH}",
                    parent=self,
                )
                self._winscp_sessions = []
        self._sessions = self._build_visible_sessions()
        self._tree.refresh(self._sessions)

    def _reload_sessions(self) -> None:
        """Lädt WinSCP- und SSH-Config-Sessions erneut ein und aktualisiert die Ansicht."""
        self._rebuild_sessions(reload_winscp=True)
        ToastNotification(self, "Verbindungen neu geladen")

    def _add_session(self, folder_preset: str = "") -> None:
        """Öffnet den Dialog zum Anlegen einer neuen Session (App oder SSH-Alias)."""
        dialog = SessionEditDialog(
            self,
            self._get_all_folder_names(),
            ssh_aliases=self._get_ssh_aliases(),
            folder_preset=folder_preset,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._app_sessions.append(dialog.result)
        if dialog.note_result:
            self._notes[dialog.result.key] = dialog.note_result
        else:
            self._notes.pop(dialog.result.key, None)
        save_notes(self._notes)
        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _edit_session(self, session: Session) -> None:
        """Öffnet den Dialog zum Bearbeiten einer App-Session."""
        dialog = SessionEditDialog(self, self._get_all_folder_names(), session=session, note=self._notes.get(session.key, ""))
        self.wait_window(dialog)
        if dialog.result is None:
            return
        for i, s in enumerate(self._app_sessions):
            if s.key == session.key:
                # Farbe auf neuen Key übertragen falls Key sich geändert hat (sollte nicht passieren)
                self._app_sessions[i] = dialog.result
                break
        if dialog.note_result:
            self._notes[dialog.result.key] = dialog.note_result
        else:
            self._notes.pop(dialog.result.key, None)
        save_notes(self._notes)
        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _duplicate_app_session(self, session: Session) -> None:
        """Dupliziert eine App-Session (öffnet Dialog mit vorausgefüllten Daten, neue UUID)."""
        dialog = SessionEditDialog(
            self, self._get_all_folder_names(), session=session, duplicate=True
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._app_sessions.append(dialog.result)
        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _move_session(self, session: Session) -> None:
        """Verschiebt eine App- oder SSH-Alias-Session in einen anderen Ordner."""
        dialog = MoveFolderDialog(self, self._get_all_folder_names(), session.folder_key)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        folder_path = [p for p in dialog.result.split("/") if p]
        for i, s in enumerate(self._app_sessions):
            if s.key == session.key:
                self._app_sessions[i] = Session(
                    key=s.key,
                    display_name=s.display_name,
                    folder_path=folder_path,
                    hostname=s.hostname,
                    username=s.username,
                    port=s.port,
                    source=s.source,
                )
                break
        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _move_sessions(self, sessions: list[Session]) -> None:
        """Verschiebt mehrere App-/SSH-Alias-Sessions in denselben Ordner."""
        dialog = MoveFolderDialog(self, self._get_all_folder_names(), sessions[0].folder_key)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        folder_path = [p for p in dialog.result.split("/") if p]
        keys = {s.key for s in sessions}
        for i, s in enumerate(self._app_sessions):
            if s.key in keys:
                self._app_sessions[i] = Session(
                    key=s.key,
                    display_name=s.display_name,
                    folder_path=folder_path,
                    hostname=s.hostname,
                    username=s.username,
                    port=s.port,
                    source=s.source,
                )
        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _delete_session(self, session: Session) -> None:
        """Löscht eine App-Session nach Bestätigung."""
        if not messagebox.askyesno(
            "Verbindung löschen",
            f"Verbindung '{session.display_name}' wirklich löschen?",
            parent=self,
        ):
            return
        self._app_sessions = [s for s in self._app_sessions if s.key != session.key]
        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _delete_folder(self, sessions: list[Session], folder_key: str) -> None:
        """Löscht alle App-Sessions in einem Ordner nach Bestätigung."""
        if not messagebox.askyesno(
            "Ordner löschen",
            f"Ordner '{folder_key}' und alle {len(sessions)} Verbindung(en) darin löschen?",
            parent=self,
        ):
            return
        keys_to_delete = {s.key for s in sessions}
        self._app_sessions = [s for s in self._app_sessions if s.key not in keys_to_delete]
        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _rename_folder(self, folder_key: str) -> None:
        """Benennt einen Ordner um, indem folder_path aller enthaltenen Sessions angepasst wird."""
        parts = folder_key.split("/")
        depth = len(parts) - 1
        old_name = parts[depth]
        prefix = parts[:depth]

        new_name = simpledialog.askstring(
            "Ordner umbenennen",
            f"Neuer Name für '{old_name}':",
            initialvalue=old_name,
            parent=self,
        )
        if not new_name or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        for session in self._app_sessions:
            fp = session.folder_path
            if (len(fp) > depth
                    and fp[:depth] == prefix
                    and fp[depth] == old_name):
                session.folder_path = fp[:depth] + [new_name] + fp[depth + 1:]

        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _duplicate_ssh_alias(self, session: Session) -> None:
        """Dupliziert einen SSH-Config-Alias in einen anderen Ordner."""
        dialog = SessionEditDialog(
            self,
            self._get_all_folder_names(),
            ssh_aliases=self._get_ssh_aliases(),
            alias_preset=session.display_name,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._app_sessions.append(dialog.result)
        save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _inspect_ssh_config(self, session: Session) -> None:
        """Zeigt die effektive SSH-Konfiguration für einen Alias."""
        SshConfigInspectDialog(self, session.display_name)

    def _open_ssh_config_in_vscode(self) -> None:
        """Öffnet ~/.ssh/config in VS Code."""
        try:
            subprocess.Popen(f'code "{_SSH_CONFIG_FILE}"', shell=True)
        except OSError as e:
            messagebox.showerror("VS Code nicht gefunden", f"Fehler beim Öffnen:\n{e}")

    def _open_appdata_jsons_in_vscode(self) -> None:
        """Öffnet den SSH-Manager-AppData-Ordner mit JSON-Dateien in VS Code."""
        try:
            _APPDATA_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(f'code "{_APPDATA_DIR}"', shell=True)
        except OSError as e:
            messagebox.showerror("VS Code nicht gefunden", f"Fehler beim Öffnen:\n{e}")

    def _deploy_ssh_key(self, sessions: list[Session]) -> None:
        """Öffnet den ssh-copy-id Dialog und startet den Key-Transfer im Terminal."""
        dialog = SshCopyIdDialog(self, target_count=len(sessions), quick_users=self.get_quick_users(), default_user=self.get_default_user())
        self.wait_window(dialog)
        if dialog.result is None:
            return
        key_filename, user = dialog.result
        try:
            cmd = build_ssh_copy_id_command(sessions, key_filename, user, terminal_settings=self.get_terminal_settings())
            subprocess.Popen(cmd, shell=True)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}")

    def _remove_ssh_key(self, sessions: list[Session]) -> None:
        """Öffnet den Remove-Key Dialog und entfernt den Key remote via SSH."""
        dialog = SshRemoveKeyDialog(self, target_count=len(sessions), quick_users=self.get_quick_users(), default_user=self.get_default_user())
        self.wait_window(dialog)
        if dialog.result is None:
            return
        key_filename, user = dialog.result
        try:
            cmd = build_ssh_remove_key_command(sessions, key_filename, user, terminal_settings=self.get_terminal_settings())
            subprocess.Popen(cmd, shell=True)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}")

    def _open_tunnel(self, session: Session | None = None) -> None:
        """Öffnet den Tunnel-Dialog und startet den SSH-Tunnel im Terminal."""
        dialog = SshTunnelDialog(
            self,
            session=session,
            quick_users=self.get_quick_users(),
            default_user=self.get_default_user(),
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        jumphost, local_port, remote_host, remote_port, user = dialog.result
        try:
            cmd = build_ssh_tunnel_command(jumphost, local_port, remote_host, remote_port, user, terminal_settings=self.get_terminal_settings())
            subprocess.Popen(cmd)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}")

    def _open_via_jumphost(self, session: Session) -> None:
        """Öffnet eine einzelne Verbindung temporär über einen Jumphost."""
        dialog = JumpHostDialog(self, session, self._sessions, open_folders_getter=self._tree.get_open_folders)
        self.wait_window(dialog)

        if dialog.save_result is not None:
            alias, jump_host, jump_port, jump_user, _target_key = dialog.save_result
            target_user = self._resolve_single_session_user(session, title=f"Benutzername für {session.display_name}")
            if target_user is None:
                return
            try:
                _append_ssh_config_alias(alias, session, target_user, jump_host, jump_user, jump_port)
            except ValueError as e:
                messagebox.showwarning("SSH-Config", str(e), parent=self)
                return
            except OSError as e:
                messagebox.showerror("SSH-Config", f"Fehler beim Schreiben von ~/.ssh/config:\n{e}", parent=self)
                return
            self._rebuild_sessions(reload_winscp=True)
            ToastNotification(self, f"SSH-Config '{alias}' gespeichert")
            return

        if dialog.result is None:
            return

        jump_host, jump_user, jump_port = dialog.result
        target_user = self._resolve_single_session_user(session, title=f"Benutzername für {session.display_name}")
        if target_user is None:
            return
        try:
            cmd = build_jump_wt_command(
                session,
                target_user,
                jump_host,
                jump_user or None,
                jump_port,
                self._tree.get_session_colors().get(session.key),
                terminal_settings=self.get_terminal_settings(),
            )
            subprocess.Popen(cmd, shell=True)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}", parent=self)

    def _resolve_users_for_sessions(self, sessions: list[Session], mode: str) -> list[tuple[Session, str]] | None:
        """Löst Benutzernamen für Sessions auf, global oder pro Host."""
        resolved: list[tuple[Session, str]] = []
        if mode == "all":
            missing = [s for s in sessions if not (s.is_ssh_config_session and s.username)]
            shared_user = None
            if missing:
                dialog = UserDialog(self, title="Benutzername für alle Hosts")
                self.wait_window(dialog)
                if dialog.result is None:
                    return None
                shared_user = dialog.result
            for session in sessions:
                user = session.username if session.is_ssh_config_session and session.username else shared_user
                if not user:
                    messagebox.showwarning("Fehlender Benutzer", f"Für '{session.display_name}' konnte kein Benutzer bestimmt werden.", parent=self)
                    return None
                resolved.append((session, user))
            return resolved

        for session in sessions:
            if session.is_ssh_config_session and session.username:
                resolved.append((session, session.username))
                continue
            dialog = UserDialog(self, title=f"Benutzername für {session.display_name}")
            self.wait_window(dialog)
            if dialog.result is None:
                return None
            resolved.append((session, dialog.result))
        return resolved

    def _run_remote_command(self, sessions: list[Session]) -> None:
        """Führt einen Remote-Befehl auf einem oder mehreren Hosts aus."""
        runnable = [s for s in sessions if s.hostname]
        if not runnable:
            messagebox.showwarning("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=self)
            return

        dialog = RemoteCommandDialog(
            self,
            target_count=len(runnable),
            last_command=self._initial_toolbar_search_texts.get("last_remote_command", ""),
            quick_users=self.get_quick_users(),
            default_user=self.get_default_user(),
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        user_mode, command, close_on_success = dialog.result
        self._initial_toolbar_search_texts["last_remote_command"] = command

        session_users = self._resolve_users_for_sessions(runnable, user_mode)
        if session_users is None:
            return

        confirm = RemoteCommandConfirmDialog(self, command, session_users, close_on_success)
        self.wait_window(confirm)
        if not confirm.result:
            return

        cmd = build_remote_command_wt_command(
            [(session, user, command) for session, user in session_users],
            close_on_success=close_on_success,
            session_colors=self._tree.get_session_colors(),
            terminal_settings=self.get_terminal_settings(),
        )
        try:
            subprocess.Popen(cmd, shell=True)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}", parent=self)

    def _open_in_winscp(self, sessions: list[Session]) -> None:
        """Öffnet eine oder mehrere WinSCP-Sessions direkt in WinSCP."""
        winscp = _find_winscp()
        if not winscp:
            messagebox.showerror(
                "WinSCP nicht gefunden",
                "WinSCP.exe wurde nicht gefunden.\n"
                "Bitte WinSCP installieren oder zum PATH hinzufügen.",
                parent=self,
            )
            return
        try:
            for session in sessions:
                full_path = "/".join(session.folder_path + [session.display_name])
                subprocess.Popen([winscp, full_path])
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten von WinSCP:\n{e}", parent=self)

    def _on_close(self) -> None:
        self._persist_ui_state()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SSHManagerApp()
    app.mainloop()
