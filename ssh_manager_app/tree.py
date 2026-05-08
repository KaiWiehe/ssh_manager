from __future__ import annotations

import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import PALETTE, Session, ToolbarSettings, color_tag
from .constants import _SSH_CONFIG_DEFAULT_FOLDER
from .core import check_host_reachable


def _session_values_text(sessions: list[Session], attribute: str) -> str:
    """Verkettet nicht-leere Session-Attribute zeilenweise für die Zwischenablage."""
    return "\n".join(
        value
        for session in sessions
        if (value := getattr(session, attribute, ""))
    )


def _session_notes_text(sessions: list[Session], notes_getter) -> str:
    """Verkettet nicht-leere Session-Notizen zeilenweise für die Zwischenablage."""
    return "\n".join(
        note
        for session in sessions
        if (note := notes_getter(session.key).strip())
    )


class SessionTree(ttk.Frame):
    """
    ttk.Treeview-Wrapper mit Checkbox-Unterstützung.
    Zeigt Sessions gruppiert nach Ordnern an.
    Unterstützt Live-Filter, Rechtsklick-Kontextmenü, Checkbox-Toggle.
    """

    # Tag-Konstanten
    TAG_SESSION = "session"
    TAG_FOLDER = "folder"

    def __init__(
        self,
        parent: tk.Widget,
        sessions: list[Session],
        img_unchecked: tk.PhotoImage,
        img_checked: tk.PhotoImage,
        on_selection_changed,  # Callable[[int], None]
        initial_open_folders: set[str] | None = None,
        initial_session_colors: dict[str, str] | None = None,
        on_quick_connect=None,           # Callable[[Session], None] | None
        on_connect_sessions=None,        # Callable[[list[Session]], None] | None
        on_edit_session=None,            # Callable[[Session], None] | None
        on_set_sessions_username=None,   # Callable[[list[Session]], None] | None
        on_clear_sessions_username=None, # Callable[[list[Session]], None] | None
        on_delete_session=None,          # Callable[[Session], None] | None
        on_delete_folder=None,           # Callable[[list[Session], str], None] | None
        on_rename_folder=None,           # Callable[[str, str], None] | None  (folder_key, new_name)
        on_add_session=None,             # Callable[[], None] | None
        on_add_session_in_folder=None,   # Callable[[str], None] | None  (folder_key)
        on_duplicate_ssh_alias=None,     # Callable[[Session], None] | None
        on_inspect_ssh_config=None,      # Callable[[Session], None] | None
        on_duplicate_app_session=None,   # Callable[[Session], None] | None
        on_move_session=None,            # Callable[[Session], None] | None
        on_move_sessions=None,           # Callable[[list[Session]], None] | None
        on_open_ssh_config_in_vscode=None,  # Callable[[], None] | None
        on_deploy_ssh_key=None,             # Callable[[list[Session]], None] | None
        on_remove_ssh_key=None,             # Callable[[list[Session]], None] | None
        on_open_tunnel=None,                # Callable[[Session], None] | None
        on_open_in_winscp=None,             # Callable[[list[Session]], None] | None
        on_run_remote_command=None,         # Callable[[list[Session]], None] | None
        on_open_via_jumphost=None,          # Callable[[Session], None] | None
        on_ui_state_changed=None,           # Callable[[], None] | None
        notes_getter=None,                  # Callable[[str], str] | None
        on_edit_note=None,                  # Callable[[Session], None] | None
        on_add_favorite=None,               # Callable[[Session, bool], None] | None
        on_add_favorites=None,              # Callable[[list[Session], bool], None] | None
        on_remove_favorite=None,            # Callable[[Session], None] | None
        favorite_keys_getter=None,          # Callable[[], set[str]] | None
        toolbar_settings: ToolbarSettings | None = None,
    ):
        super().__init__(parent)
        self._sessions = sessions
        self._img_unchecked = img_unchecked
        self._img_checked = img_checked
        self._on_selection_changed = on_selection_changed
        self._on_quick_connect = on_quick_connect
        self._on_connect_sessions = on_connect_sessions
        self._on_edit_session = on_edit_session
        self._on_set_sessions_username = on_set_sessions_username
        self._on_clear_sessions_username = on_clear_sessions_username
        self._on_delete_session = on_delete_session
        self._on_delete_folder = on_delete_folder
        self._on_rename_folder = on_rename_folder
        self._on_add_session = on_add_session
        self._on_add_session_in_folder = on_add_session_in_folder
        self._on_duplicate_ssh_alias = on_duplicate_ssh_alias
        self._on_inspect_ssh_config = on_inspect_ssh_config
        self._on_duplicate_app_session = on_duplicate_app_session
        self._on_move_session = on_move_session
        self._on_move_sessions = on_move_sessions
        self._on_open_ssh_config_in_vscode = on_open_ssh_config_in_vscode
        self._on_deploy_ssh_key = on_deploy_ssh_key
        self._on_remove_ssh_key = on_remove_ssh_key
        self._on_open_tunnel = on_open_tunnel
        self._on_open_in_winscp = on_open_in_winscp
        self._on_run_remote_command = on_run_remote_command
        self._on_open_via_jumphost = on_open_via_jumphost
        self._on_ui_state_changed = on_ui_state_changed
        self._notes_getter = notes_getter or (lambda _key: "")
        self._on_edit_note = on_edit_note
        self._on_add_favorite = on_add_favorite
        self._on_add_favorites = on_add_favorites
        self._on_remove_favorite = on_remove_favorite
        self._favorite_keys_getter = favorite_keys_getter or (lambda: set())
        self._toolbar_settings = toolbar_settings or ToolbarSettings()
        self._tooltip: tk.Toplevel | None = None
        self._tooltip_after_id = None
        self._last_tooltip_item: str | None = None
        self._suppress_next_click = False

        # item_id → Session (nur für Session-Zeilen, nicht Ordner)
        self._item_to_session: dict[str, Session] = {}
        # item_id → checked state
        self._checked: dict[str, bool] = {}
        # item_id → folder_key (z.B. "Extern/Sub")
        self._item_to_folder_key: dict[str, str] = {}
        # item_id → Status "ok" | "fail" | "checking" | None
        self._item_to_status: dict[str, str | None] = {}
        # session.key → hex-Farbe
        self._session_colors: dict[str, str] = dict(initial_session_colors or {})
        self._pre_search_open_folders: set[str] | None = None
        self._empty_state: ttk.Frame | None = None

        self._build()
        self.populate(sessions, open_folders=initial_open_folders or set())

    def _build(self) -> None:
        """Erstellt Treeview + Scrollbar."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._tv = ttk.Treeview(
            self,
            columns=("username", "hostname", "port", "notes"),
            selectmode="none",  # Selektion via Checkboxen, nicht Highlight
        )
        self._tv.heading("#0", text="Name", anchor="w")
        self._tv.heading("username", text="Benutzer", anchor="w")
        self._tv.heading("hostname", text="Hostname", anchor="w")
        self._tv.heading("port", text="Port", anchor="w")
        self._tv.heading("notes", text="Notizen", anchor="w")
        self._tv.column("#0", width=340, stretch=True)
        self._tv.column("username", width=110, stretch=False)
        self._tv.column("hostname", width=130, stretch=False)
        self._tv.column("port", width=60, stretch=False)
        self._tv.column("notes", width=220, stretch=True)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)

        self._tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._empty_state = ttk.Frame(self, style="EmptyState.TFrame", padding=28)
        self._empty_state.columnconfigure(0, weight=1)
        self._empty_state.rowconfigure(0, weight=1)
        card = ttk.Frame(self._empty_state, style="EmptyStateCard.TFrame", padding=(34, 28))
        card.grid(row=0, column=0)
        ttk.Label(card, text="Keine Verbindungen vorhanden", style="EmptyStateTitle.TLabel").grid(row=0, column=0, sticky="ew")
        ttk.Label(
            card,
            text="Lege deine erste SSH-Verbindung an oder importiere später bestehende Quellen.",
            style="EmptyStateHint.TLabel",
            wraplength=460,
            justify="center",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 18))
        ttk.Button(card, text="+ Verbindung hinzufügen", style="Accent.TButton", command=self._empty_add_session).grid(row=2, column=0)

        # Events
        self._tv.bind("<ButtonRelease-1>", self._on_left_click)
        self._tv.bind("<Double-Button-1>", self._on_double_click)
        self._tv.bind("<ButtonRelease-3>", self._on_right_click)
        self._tv.bind("<<TreeviewOpen>>", lambda _e: self._notify_ui_state_changed())
        self._tv.bind("<<TreeviewClose>>", lambda _e: self._notify_ui_state_changed())
        self._tv.bind("<Motion>", self._on_tree_motion)
        self._tv.bind("<Leave>", lambda _e: self._hide_tooltip())
        self._tv.bind("<ButtonPress>", lambda _e: self._hide_tooltip())

        self._configure_color_tags()
        self._apply_column_visibility()

    def _empty_add_session(self) -> None:
        if self._on_add_session:
            self._on_add_session()
        elif self._on_add_session_in_folder:
            self._on_add_session_in_folder("")

    def _update_empty_state(self, sessions: list[Session]) -> None:
        if self._empty_state is None:
            return
        if sessions:
            self._empty_state.grid_remove()
        else:
            self._empty_state.grid(row=0, column=0, sticky="nsew")
            self._empty_state.tkraise()

    def _configure_color_tags(self) -> None:
        """Registriert für jede Palettenfarbe einen Treeview-Tag."""
        for _, hex_color in PALETTE:
            self._tv.tag_configure(color_tag(hex_color), foreground=hex_color)

    def _apply_column_visibility(self) -> None:
        visible = {
            "username": self._toolbar_settings.show_username_column,
            "hostname": self._toolbar_settings.show_hostname_column,
            "port": self._toolbar_settings.show_port_column,
            "notes": self._toolbar_settings.show_notes_column,
        }
        ordered = []
        for column in self._toolbar_settings.column_order:
            if visible.get(column):
                ordered.append(column)
        for column in ("username", "hostname", "port", "notes"):
            if visible.get(column) and column not in ordered:
                ordered.append(column)
        self._tv.configure(displaycolumns=ordered)

    def update_toolbar_settings(self, toolbar_settings: ToolbarSettings) -> None:
        self._toolbar_settings = toolbar_settings
        self._apply_column_visibility()

    def _on_tree_motion(self, event: tk.Event) -> None:
        item_id = self._tv.identify_row(event.y)
        column_id = self._tv.identify_column(event.x)
        if not item_id or item_id not in self._item_to_session or column_id not in {"#0", "#3"}:
            self._hide_tooltip()
            return
        if item_id == self._last_tooltip_item and self._tooltip is not None:
            return
        self._hide_tooltip()
        self._last_tooltip_item = item_id
        note = self._notes_getter(self._item_to_session[item_id].key).strip()
        if not note:
            return
        self._tooltip_after_id = self.after(450, lambda iid=item_id, x=event.x_root, y=event.y_root, text=note: self._show_tooltip(iid, x, y, text))

    def _show_tooltip(self, item_id: str, x: int, y: int, text: str) -> None:
        if item_id != self._last_tooltip_item:
            return
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._tooltip_after_id = None
        self._tooltip = tk.Toplevel(self)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.attributes("-topmost", True)
        label = tk.Label(self._tooltip, text=text, justify="left", background="#fff8dc", relief="solid", borderwidth=1, padx=8, pady=6, wraplength=420)
        label.pack()
        self._tooltip.geometry(f"+{x + 12}+{y + 12}")

    def _hide_tooltip(self) -> None:
        if self._tooltip_after_id:
            self.after_cancel(self._tooltip_after_id)
            self._tooltip_after_id = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._last_tooltip_item = None

    def get_open_folders(self) -> set[str]:
        """Gibt folder_keys aller aktuell geöffneten Ordner zurück."""
        return {
            fkey
            for item_id, fkey in self._item_to_folder_key.items()
            if self._tv.item(item_id, "open")
        }

    def open_folder_key(self, folder_key: str) -> None:
        """Öffnet einen sichtbaren Ordner anhand seines folder_key."""
        for item_id, fkey in self._item_to_folder_key.items():
            if fkey == folder_key:
                self._tv.item(item_id, open=True)
                self._notify_ui_state_changed()
                break

    def get_session_colors(self) -> dict[str, str]:
        """Gibt eine Kopie des aktuellen session_key → hex Mappings zurück."""
        return dict(self._session_colors)

    def _notify_ui_state_changed(self) -> None:
        if self._on_ui_state_changed:
            self._on_ui_state_changed()

    def set_session_color(self, session_key: str, hex_color: str | None) -> None:
        """Setzt oder entfernt die Textfarbe einer Session sofort im Tree."""
        if hex_color:
            self._session_colors[session_key] = hex_color
        else:
            self._session_colors.pop(session_key, None)
        for item_id, session in self._item_to_session.items():
            if session.key == session_key:
                color_tag = color_tag(hex_color) if hex_color else None
                tags = (self.TAG_SESSION,) + ((color_tag,) if color_tag else ())
                self._tv.item(item_id, tags=tags)
                break
        self._notify_ui_state_changed()

    def populate(self, sessions: list[Session], open_folders: set[str] | None = None) -> None:
        """Füllt den Baum mit Sessions. Löscht vorherige Inhalte."""
        # Zustand merken (welche Ordner waren offen?) – falls nicht extern übergeben
        if open_folders is None:
            open_folders = self.get_open_folders()

        # Alles löschen
        self._tv.delete(*self._tv.get_children())
        self._item_to_session.clear()
        self._checked.clear()
        self._item_to_folder_key.clear()
        self._item_to_status.clear()

        # Ordner-Nodes: folder_key → item_id
        folder_items: dict[str, str] = {}

        for session in sessions:
            # Ordner-Hierarchie aufbauen
            parent_id = ""
            for depth, folder_name in enumerate(session.folder_path):
                folder_key = "/".join(session.folder_path[: depth + 1])
                if folder_key not in folder_items:
                    was_open = folder_key in open_folders
                    folder_label = f"  ⚙ {folder_name}" if folder_key == _SSH_CONFIG_DEFAULT_FOLDER else f"  {folder_name}"
                    folder_id = self._tv.insert(
                        parent_id, "end",
                        text=folder_label,
                        open=was_open,
                        tags=(self.TAG_FOLDER,),
                    )
                    self._tv.tag_bind(folder_id, "<<TreeviewOpen>>", lambda e: None)
                    folder_items[folder_key] = folder_id
                    self._item_to_folder_key[folder_id] = folder_key
                parent_id = folder_items[folder_key]

            # Session-Zeile
            port_str = str(session.port) if session.port != 22 else ""
            note_text = self._notes_getter(session.key)
            note_short = (note_text[:57] + "...") if len(note_text) > 60 else note_text
            _ctag = color_tag(self._session_colors[session.key]) if session.key in self._session_colors else None
            _tags = (self.TAG_SESSION,) + ((_ctag,) if _ctag else ())
            label = self._session_label(session, None)
            item_id = self._tv.insert(
                parent_id, "end",
                image=self._img_unchecked,
                text=label,
                values=(session.username, session.hostname, port_str, note_short),
                tags=_tags,
            )
            self._item_to_session[item_id] = session
            self._checked[item_id] = False

        self._update_empty_state(sessions)

    def _on_left_click(self, event: tk.Event) -> None:
        """Checkbox togglen wenn auf eine Session-Zeile geklickt wird."""
        if self._suppress_next_click:
            self._suppress_next_click = False
            return
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        self._tv.focus(item_id)
        if self.TAG_SESSION not in self._tv.item(item_id, "tags"):
            return
        self._toggle(item_id)

    def _on_double_click(self, event: tk.Event) -> None:
        """Einzelne Session per Doppelklick direkt öffnen."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        self._tv.focus(item_id)
        if self.TAG_SESSION not in self._tv.item(item_id, "tags"):
            return
        self._suppress_next_click = True
        if self._on_quick_connect:
            self._on_quick_connect(self._item_to_session[item_id])

    def _toggle(self, item_id: str) -> None:
        """Checkbox-Zustand einer Session-Zeile umschalten."""
        new_state = not self._checked.get(item_id, False)
        self._checked[item_id] = new_state
        self._tv.item(
            item_id,
            image=self._img_checked if new_state else self._img_unchecked,
        )
        self._notify_count()
        self._notify_ui_state_changed()

    def _notify_count(self) -> None:
        count = sum(1 for v in self._checked.values() if v)
        self._on_selection_changed(count)

    def get_selected_sessions(self) -> list[Session]:
        """Gibt alle ausgewählten (gecheckte) Sessions zurück."""
        return [
            self._item_to_session[iid]
            for iid, checked in self._checked.items()
            if checked
        ]

    def _copy_session_values(self, sessions: list[Session], attribute: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(_session_values_text(sessions, attribute))

    def _copy_session_notes(self, sessions: list[Session]) -> None:
        self.clipboard_clear()
        self.clipboard_append(_session_notes_text(sessions, self._notes_getter))

    def get_single_context_session(self) -> Session | None:
        """Gibt die fokussierte Treeview-Session zurück, falls genau eine Zeile im Fokus ist."""
        item_id = self._tv.focus()
        if item_id and self.TAG_SESSION in self._tv.item(item_id, "tags"):
            return self._item_to_session.get(item_id)
        return None

    def set_all_checked(self, state: bool) -> None:
        """Alle sichtbaren Session-Zeilen an-/abhaken."""
        for item_id in self._checked:
            self._checked[item_id] = state
            self._tv.item(
                item_id,
                image=self._img_checked if state else self._img_unchecked,
            )
        self._notify_count()
        self._notify_ui_state_changed()

    def _set_folder_checked(self, folder_item_id: str, state: bool) -> None:
        """Alle Session-Zeilen unter einem Ordner an-/abhaken (rekursiv)."""
        self._set_folder_checked_inner(folder_item_id, state)
        self._notify_count()
        self._notify_ui_state_changed()

    def _set_folder_checked_inner(self, folder_item_id: str, state: bool) -> None:
        """Rekursiver Kern ohne Notification – nur von _set_folder_checked aufrufen."""
        for child_id in self._tv.get_children(folder_item_id):
            tags = self._tv.item(child_id, "tags")
            if self.TAG_SESSION in tags:
                self._checked[child_id] = state
                self._tv.item(
                    child_id,
                    image=self._img_checked if state else self._img_unchecked,
                )
            elif self.TAG_FOLDER in tags:
                self._set_folder_checked_inner(child_id, state)

    def _on_right_click(self, event: tk.Event) -> None:
        """Kontextmenü je nach Zeilentyp anzeigen."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        self._tv.focus(item_id)
        tags = self._tv.item(item_id, "tags")
        if self.TAG_FOLDER in tags:
            self._show_folder_menu(item_id, event)
        elif self.TAG_SESSION in tags:
            self._show_session_menu(item_id, event)

    def _set_folder_open_recursive(self, folder_item_id: str, state: bool) -> None:
        """Klappt einen Ordner rekursiv auf oder zu."""
        self._tv.item(folder_item_id, open=state)
        for child_id in self._tv.get_children(folder_item_id):
            if self.TAG_FOLDER in self._tv.item(child_id, "tags"):
                self._set_folder_open_recursive(child_id, state)
        self._notify_ui_state_changed()

    def _show_folder_menu(self, item_id: str, event: tk.Event) -> None:
        """Kontextmenü für Ordner-Zeilen."""
        folder_key = self._item_to_folder_key.get(item_id, "")
        menu = tk.Menu(self, tearoff=False)
        if folder_key == _SSH_CONFIG_DEFAULT_FOLDER and self._on_open_ssh_config_in_vscode:
            menu.add_command(
                label="In VS Code öffnen",
                command=self._on_open_ssh_config_in_vscode,
            )
            menu.add_separator()
        if self._on_add_session_in_folder:
            menu.add_command(
                label="Neue Verbindung hier…",
                command=lambda fk=folder_key: self._on_add_session_in_folder(fk),
            )
            menu.add_separator()
        menu.add_command(
            label="Alle im Ordner auswählen",
            command=lambda: self._set_folder_checked(item_id, True),
        )
        menu.add_command(
            label="Alle im Ordner abwählen",
            command=lambda: self._set_folder_checked(item_id, False),
        )
        menu.add_separator()
        menu.add_command(
            label="Alle Unterordner ausklappen",
            command=lambda: self._set_folder_open_recursive(item_id, True),
        )
        menu.add_command(
            label="Alle Unterordner einklappen",
            command=lambda: self._set_folder_open_recursive(item_id, False),
        )
        folder_sessions = self._get_folder_sessions(item_id)
        if folder_sessions:
            if self._on_connect_sessions:
                menu.add_separator()
                menu.add_command(
                    label=f"Alle im Ordner verbinden ({len(folder_sessions)})",
                    command=lambda ss=list(folder_sessions): self._on_connect_sessions(ss),
                )
            winscp_sessions = [s for s in folder_sessions if s.source == "winscp"]
            if winscp_sessions and self._on_open_in_winscp:
                menu.add_command(
                    label=f"Alle in WinSCP öffnen ({len(winscp_sessions)})",
                    command=lambda ss=winscp_sessions: self._on_open_in_winscp(ss),
                )
            if self._on_run_remote_command:
                menu.add_command(
                    label=f"Befehl auf Ordner ausführen… ({len(folder_sessions)})",
                    command=lambda ss=list(folder_sessions): self._on_run_remote_command(ss),
                )
            if self._on_set_sessions_username:
                menu.add_command(
                    label=f"Benutzer setzen… ({len(folder_sessions)})",
                    command=lambda ss=list(folder_sessions): self._on_set_sessions_username(ss),
                )
            if self._on_clear_sessions_username:
                menu.add_command(
                    label=f"Benutzer entfernen… ({len(folder_sessions)})",
                    command=lambda ss=list(folder_sessions): self._on_clear_sessions_username(ss),
                )
            menu.add_separator()
            menu.add_command(
                label="Hostnames kopieren",
                command=lambda ss=list(folder_sessions): self._copy_session_values(ss, "hostname"),
            )
            menu.add_command(
                label="Namen kopieren",
                command=lambda ss=list(folder_sessions): self._copy_session_values(ss, "display_name"),
            )
            menu.add_command(
                label="Notizen kopieren",
                command=lambda ss=list(folder_sessions): self._copy_session_notes(ss),
            )
            menu.add_separator()
            menu.add_command(
                label="Hosts prüfen",
                command=lambda fid=item_id: self.check_folder_hosts(fid),
            )
            favorite_keys = self._favorite_keys_getter()
            not_favorite = [s for s in folder_sessions if s.key not in favorite_keys]
            if not_favorite and self._on_add_favorites:
                menu.add_command(
                    label=f"Zu Favoriten hinzufügen… ({len(not_favorite)})",
                    command=lambda ss=list(not_favorite): self._add_favorites_with_dialog(ss),
                )
        if folder_sessions and all(s.source in ("app", "ssh_alias") for s in folder_sessions):
            menu.add_separator()
            if self._on_rename_folder:
                menu.add_command(
                    label="Umbenennen…",
                    command=lambda fk=folder_key: self._on_rename_folder(fk),
                )
            if self._on_delete_folder:
                menu.add_command(
                    label="Ordner löschen",
                    command=lambda ss=list(folder_sessions), fk=folder_key: self._on_delete_folder(ss, fk),
                )
        if folder_sessions:
            color_menu = tk.Menu(menu, tearoff=False)
            for name, hex_color in PALETTE:
                color_menu.add_command(
                    label=f"  {name}",
                    command=lambda hc=hex_color, ss=list(folder_sessions): [
                        self.set_session_color(s.key, hc) for s in ss
                    ],
                )
            color_menu.add_separator()
            color_menu.add_command(
                label="✕ Farbe entfernen",
                command=lambda ss=list(folder_sessions): [
                    self.set_session_color(s.key, None) for s in ss
                ],
            )
            menu.add_separator()
            menu.add_cascade(label="Farbe für alle…", menu=color_menu)
        if folder_sessions and (self._on_deploy_ssh_key or self._on_remove_ssh_key):
            menu.add_separator()
            if self._on_deploy_ssh_key:
                menu.add_command(
                    label="SSH Key übertragen…",
                    command=lambda ss=list(folder_sessions): self._on_deploy_ssh_key(ss),
                )
            if self._on_remove_ssh_key:
                menu.add_command(
                    label="SSH Key entfernen…",
                    command=lambda ss=list(folder_sessions): self._on_remove_ssh_key(ss),
                )
        menu.tk_popup(event.x_root, event.y_root)

    def _show_session_menu(self, item_id: str, event: tk.Event) -> None:
        """Kontextmenü für Session-Zeilen, thematisch in Sektionen sortiert."""
        session = self._item_to_session[item_id]
        selected = self.get_selected_sessions()
        selected_count = len(selected)
        favorite_keys = self._favorite_keys_getter()
        current_color = self._session_colors.get(session.key)

        menu = tk.Menu(self, tearoff=False)

        # Öffnen / Verbinden – immer ganz oben.
        if self._on_quick_connect:
            menu.add_command(
                label="Verbindung öffnen",
                command=lambda s=session: self._on_quick_connect(s),
            )
        if selected_count >= 2 and self._on_connect_sessions:
            menu.add_command(
                label=f"Auswahl verbinden ({selected_count})",
                command=lambda ss=list(selected): self._on_connect_sessions(ss),
            )
        if self._on_open_in_winscp and session.source == "winscp":
            menu.add_command(
                label="In WinSCP öffnen",
                command=lambda s=session: self._on_open_in_winscp([s]),
            )
            selected_winscp = [s for s in selected if s.source == "winscp"]
            if len(selected_winscp) >= 2:
                menu.add_command(
                    label=f"Auswahl in WinSCP öffnen ({len(selected_winscp)})",
                    command=lambda ss=selected_winscp: self._on_open_in_winscp(ss),
                )

        # Favoriten – einzelne Session und Auswahl zusammenhalten.
        menu.add_separator()
        if session.key in favorite_keys:
            if self._on_remove_favorite:
                menu.add_command(
                    label="Aus Favoriten entfernen",
                    command=lambda s=session: self._on_remove_favorite(s),
                )
        elif self._on_add_favorite:
            menu.add_command(
                label="Zu Favoriten hinzufügen…",
                command=lambda s=session: self._add_favorite_with_dialog(s),
            )
        if selected_count >= 2:
            not_favorite = [s for s in selected if s.key not in favorite_keys]
            if not_favorite and self._on_add_favorites:
                menu.add_command(
                    label=f"Auswahl zu Favoriten hinzufügen… ({len(not_favorite)})",
                    command=lambda ss=list(not_favorite): self._add_favorites_with_dialog(ss),
                )

        # Bearbeiten / Organisation.
        menu.add_separator()
        if self._on_edit_session:
            menu.add_command(
                label="Bearbeiten…",
                command=lambda s=session: self._on_edit_session(s),
            )
        if session.is_app_session:
            if self._on_duplicate_app_session:
                menu.add_command(
                    label="Duplizieren…",
                    command=lambda s=session: self._on_duplicate_app_session(s),
                )
            if self._on_move_session:
                menu.add_command(
                    label="In Ordner verschieben…",
                    command=lambda s=session: self._on_move_session(s),
                )
        if self._on_set_sessions_username:
            menu.add_command(
                label="Benutzer setzen…",
                command=lambda s=session: self._on_set_sessions_username([s]),
            )
        if self._on_clear_sessions_username:
            menu.add_command(
                label="Benutzer entfernen…",
                command=lambda s=session: self._on_clear_sessions_username([s]),
            )
        if session.source == "ssh_config":
            if self._on_duplicate_ssh_alias:
                menu.add_command(
                    label="Als Alias in Ordner duplizieren…",
                    command=lambda s=session: self._on_duplicate_ssh_alias(s),
                )
        elif session.is_ssh_alias_copy:
            if self._on_move_session:
                menu.add_command(
                    label="In Ordner verschieben…",
                    command=lambda s=session: self._on_move_session(s),
                )
        if selected_count >= 2:
            moveable = [s for s in selected if s.source in ("app", "ssh_alias")]
            if moveable and self._on_move_sessions:
                menu.add_command(
                    label=f"Ordner für Auswahl ändern… ({len(moveable)})",
                    command=lambda ss=moveable: self._on_move_sessions(ss),
                )
            if self._on_set_sessions_username:
                menu.add_command(
                    label=f"Benutzer für Auswahl setzen… ({selected_count})",
                    command=lambda ss=list(selected): self._on_set_sessions_username(ss),
                )
            if self._on_clear_sessions_username:
                menu.add_command(
                    label=f"Benutzer für Auswahl entfernen… ({selected_count})",
                    command=lambda ss=list(selected): self._on_clear_sessions_username(ss),
                )

        # Kopieren – alles zusammen in eigener Sektion.
        menu.add_separator()
        menu.add_command(
            label="Hostname kopieren",
            command=lambda s=session: self._copy_session_values([s], "hostname"),
        )
        menu.add_command(
            label="Name kopieren",
            command=lambda s=session: self._copy_session_values([s], "display_name"),
        )
        menu.add_command(
            label="Notiz kopieren",
            command=lambda s=session: self._copy_session_notes([s]),
        )
        if selected_count >= 2:
            menu.add_command(
                label=f"Auswahl-Hostnamen kopieren ({selected_count})",
                command=lambda ss=list(selected): self._copy_session_values(ss, "hostname"),
            )
            menu.add_command(
                label=f"Auswahl-Namen kopieren ({selected_count})",
                command=lambda ss=list(selected): self._copy_session_values(ss, "display_name"),
            )
            menu.add_command(
                label=f"Auswahl-Notizen kopieren ({selected_count})",
                command=lambda ss=list(selected): self._copy_session_notes(ss),
            )

        # Tools / Aktionen.
        menu.add_separator()
        if self._on_open_tunnel:
            menu.add_command(
                label="Tunnel öffnen…",
                command=lambda s=session: self._on_open_tunnel(s),
            )
        if self._on_open_via_jumphost:
            menu.add_command(
                label="Über Jumphost öffnen…",
                command=lambda s=session: self._on_open_via_jumphost(s),
            )
        if self._on_run_remote_command:
            menu.add_command(
                label="Befehl ausführen…",
                command=lambda s=session: self._on_run_remote_command([s]),
            )
            selected_runnable = [s for s in selected if s.hostname]
            if len(selected_runnable) >= 2:
                menu.add_command(
                    label=f"Befehl auf Auswahl ausführen… ({len(selected_runnable)})",
                    command=lambda ss=selected_runnable: self._on_run_remote_command(ss),
                )
        if session.source in ("ssh_config", "ssh_alias"):
            if self._on_inspect_ssh_config:
                menu.add_command(
                    label="Konfiguration anzeigen (ssh -G)…",
                    command=lambda s=session: self._on_inspect_ssh_config(s),
                )
            if self._on_open_ssh_config_in_vscode:
                menu.add_command(
                    label="SSH Config in VS Code öffnen",
                    command=self._on_open_ssh_config_in_vscode,
                )

        # Prüfen.
        if session.hostname:
            menu.add_command(
                label="Host prüfen",
                command=lambda iid=item_id, s=session: self.check_hosts([(iid, s)]),
            )
        if selected_count >= 2:
            selected_pairs = [
                (iid, s) for iid, s in self._item_to_session.items()
                if self._checked.get(iid) and s.hostname
            ]
            if selected_pairs:
                menu.add_command(
                    label=f"Auswahl-Hosts prüfen ({len(selected_pairs)})",
                    command=lambda p=selected_pairs: self.check_hosts(p),
                )

        # SSH-Key-Verwaltung.
        if self._on_deploy_ssh_key or self._on_remove_ssh_key:
            menu.add_separator()
            if self._on_deploy_ssh_key:
                menu.add_command(
                    label="SSH Key übertragen…",
                    command=lambda s=session: self._on_deploy_ssh_key([s]),
                )
                if selected_count >= 2:
                    menu.add_command(
                        label=f"SSH Key auf Auswahl übertragen… ({selected_count})",
                        command=lambda ss=list(selected): self._on_deploy_ssh_key(ss),
                    )
            if self._on_remove_ssh_key:
                menu.add_command(
                    label="SSH Key entfernen…",
                    command=lambda s=session: self._on_remove_ssh_key([s]),
                )
                if selected_count >= 2:
                    menu.add_command(
                        label=f"SSH Key aus Auswahl entfernen… ({selected_count})",
                        command=lambda ss=list(selected): self._on_remove_ssh_key(ss),
                    )

        # Farbe.
        menu.add_separator()
        color_menu = tk.Menu(menu, tearoff=False)
        for name, hex_color in PALETTE:
            prefix = "✓" if hex_color == current_color else "  "
            color_menu.add_command(
                label=f"{prefix} {name}",
                command=lambda hc=hex_color, sk=session.key: self.set_session_color(sk, hc),
            )
        color_menu.add_separator()
        color_menu.add_command(
            label="✕ Farbe entfernen",
            command=lambda sk=session.key: self.set_session_color(sk, None),
        )
        menu.add_cascade(label="Farbe…", menu=color_menu)
        if selected_count >= 2:
            bulk_color_menu = tk.Menu(menu, tearoff=False)
            for name, hex_color in PALETTE:
                bulk_color_menu.add_command(
                    label=f"  {name}",
                    command=lambda hc=hex_color, ss=list(selected): [
                        self.set_session_color(s.key, hc) for s in ss
                    ],
                )
            bulk_color_menu.add_separator()
            bulk_color_menu.add_command(
                label="✕ Farbe entfernen",
                command=lambda ss=list(selected): [
                    self.set_session_color(s.key, None) for s in ss
                ],
            )
            menu.add_cascade(label=f"Farbe für Auswahl ({selected_count})…", menu=bulk_color_menu)

        # Destruktives unten.
        if (session.is_app_session or session.is_ssh_alias_copy) and self._on_delete_session:
            menu.add_separator()
            menu.add_command(
                label="Löschen",
                command=lambda s=session: self._on_delete_session(s),
            )

        menu.tk_popup(event.x_root, event.y_root)

    def _add_favorite_with_dialog(self, session: Session) -> None:
        self._add_favorites_with_dialog([session])

    def _add_favorites_with_dialog(self, sessions: list[Session]) -> None:
        count_text = "diese Verbindung" if len(sessions) == 1 else f"diese {len(sessions)} Verbindungen"
        result = messagebox.askyesnocancel(
            "Favorit hinzufügen",
            f"Soll die Favoriten-Kopie für {count_text} die originale Ordnerstruktur mitnehmen?\n\nJa = unter Favoriten mit Ordnerstruktur\nNein = flach direkt unter Favoriten\n\nDas Original bleibt immer unverändert an seinem Platz.",
            parent=self,
        )
        if result is None:
            return
        if len(sessions) == 1 and self._on_add_favorite:
            self._on_add_favorite(sessions[0], result)
        elif self._on_add_favorites:
            self._on_add_favorites(sessions, result)

    def filter(self, query: str) -> None:
        """
        Filtert sichtbare Sessions nach query (case-insensitive, Name + Hostname).
        Bei leerem query werden alle Sessions wieder angezeigt.
        Checkbox-Zustände bleiben beim Filtern erhalten.
        Während einer aktiven Suche wird der Tree vollständig aufgeklappt;
        beim Leeren wird der Zustand von vor der Suche wiederhergestellt.
        """
        q = query.strip().lower()

        # Checkbox-Zustände vor dem Neuaufbau sichern (item_id ändert sich)
        checked_keys = {
            self._item_to_session[iid].key
            for iid, v in self._checked.items()
            if v
        }

        # Zustand beim ersten Suchzeichen einmalig sichern
        if q and self._pre_search_open_folders is None:
            self._pre_search_open_folders = self.get_open_folders()

        if q:
            filtered = [
                s for s in self._sessions
                if q in s.display_name.lower() or q in s.hostname.lower()
            ]
            # Alle Ordner der Treffer aufklappen
            open_folders: set[str] | None = {
                "/".join(s.folder_path[:d + 1])
                for s in filtered
                for d in range(len(s.folder_path))
            }
        else:
            filtered = self._sessions
            # Vorherigen Zustand wiederherstellen
            open_folders = self._pre_search_open_folders
            self._pre_search_open_folders = None

        self.populate(filtered, open_folders=open_folders)

        # Checkbox-Zustände wiederherstellen
        for item_id, session in self._item_to_session.items():
            if session.key in checked_keys:
                self._checked[item_id] = True
                self._tv.item(item_id, image=self._img_checked)

        self._notify_count()

    def expand_all(self) -> None:
        """Klappt alle Ordner auf."""
        for item_id in self._item_to_folder_key:
            self._tv.item(item_id, open=True)
        self._notify_ui_state_changed()

    def collapse_all(self) -> None:
        """Klappt alle Ordner zu."""
        for item_id in self._item_to_folder_key:
            self._tv.item(item_id, open=False)
        self._notify_ui_state_changed()

    def set_checkbox_images(self, img_unchecked: tk.PhotoImage, img_checked: tk.PhotoImage) -> None:
        """Aktualisiert die Checkbox-Icons, z.B. nach Theme-Wechsel."""
        self._img_unchecked = img_unchecked
        self._img_checked = img_checked
        for item_id in self._item_to_session:
            state = self._checked.get(item_id, False)
            self._tv.item(item_id, image=self._img_checked if state else self._img_unchecked)

    def refresh(self, sessions: list[Session]) -> None:
        """Baut den Baum mit neuen Sessions neu auf, behält Ordner-Status und Checkboxen."""
        open_folders = self.get_open_folders()
        checked_keys = {
            s.key for iid, s in self._item_to_session.items() if self._checked.get(iid)
        }
        self._sessions = sessions
        self.populate(sessions, open_folders=open_folders)
        self._apply_column_visibility()
        for item_id, session in self._item_to_session.items():
            if session.key in checked_keys:
                self._checked[item_id] = True
                self._tv.item(item_id, image=self._img_checked)
        self._notify_count()

    def _session_label(self, session: Session, status: str | None) -> str:
        """Baut den Anzeigetext einer Session-Zeile inkl. Status-Symbol."""
        symbol = {"ok": "✓", "fail": "✗", "checking": "⏳"}.get(status or "", "")
        if session.is_ssh_config_session:
            type_icon = "⚙ "
        elif session.is_app_session:
            type_icon = "★ "
        else:
            type_icon = ""
        prefix = f"  {symbol + ' ' if symbol else ''}"
        return f"{prefix}{type_icon}{session.display_name}"

    def _set_item_status(self, item_id: str, status: str | None) -> None:
        """Setzt den Status einer Session-Zeile und aktualisiert den Label-Text."""
        self._item_to_status[item_id] = status
        session = self._item_to_session.get(item_id)
        if session:
            self._tv.item(item_id, text=self._session_label(session, status))

    def check_hosts(self, item_session_pairs: list[tuple[str, Session]]) -> None:
        """Prüft TCP-Erreichbarkeit aller übergebenen Sessions asynchron."""
        for item_id, _ in item_session_pairs:
            self._set_item_status(item_id, "checking")

        def _probe(item_id: str, hostname: str, port: int) -> None:
            ok = check_host_reachable(hostname, port, timeout=getattr(self, "_host_check_timeout", 3))
            self.after(0, lambda iid=item_id, s=ok: self._set_item_status(iid, "ok" if s else "fail"))

        for item_id, session in item_session_pairs:
            if session.hostname:
                threading.Thread(
                    target=_probe,
                    args=(item_id, session.hostname, session.port or 22),
                    daemon=True,
                ).start()

    def check_selected_hosts(self, timeout: int = 3) -> None:
        """Prüft alle aktuell ausgewählten Sessions."""
        self._host_check_timeout = timeout
        pairs = [
            (iid, s) for iid, s in self._item_to_session.items()
            if self._checked.get(iid) and s.hostname
        ]
        if pairs:
            self.check_hosts(pairs)

    def check_folder_hosts(self, folder_item_id: str) -> None:
        """Prüft alle Sessions eines Ordners."""
        pairs = [
            (iid, s)
            for iid, s in self._item_to_session.items()
            if s.hostname and self._tv.parent(iid) == folder_item_id
               or self._is_in_folder(iid, folder_item_id)
        ]
        # eindeutige Paare (durch zwei Bedingungen oben keine Duplikate nötig)
        seen: set[str] = set()
        unique = []
        for iid, s in pairs:
            if iid not in seen and self._is_in_folder(iid, folder_item_id) and s.hostname:
                seen.add(iid)
                unique.append((iid, s))
        if unique:
            self.check_hosts(unique)

    def _is_in_folder(self, item_id: str, folder_item_id: str) -> bool:
        """Prüft rekursiv ob item_id unter folder_item_id liegt."""
        parent = self._tv.parent(item_id)
        if not parent:
            return False
        if parent == folder_item_id:
            return True
        return self._is_in_folder(parent, folder_item_id)

    def _get_folder_sessions(self, folder_item_id: str) -> list[Session]:
        """Gibt alle Sessions rekursiv unter einem Ordner-Item zurück."""
        result = []
        for child_id in self._tv.get_children(folder_item_id):
            tags = self._tv.item(child_id, "tags")
            if self.TAG_SESSION in tags:
                result.append(self._item_to_session[child_id])
            elif self.TAG_FOLDER in tags:
                result.extend(self._get_folder_sessions(child_id))
        return result


# ---------------------------------------------------------------------------
# UserDialog
# ---------------------------------------------------------------------------
