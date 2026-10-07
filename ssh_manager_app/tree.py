from __future__ import annotations

import queue
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import messagebox, ttk

from . import PALETTE, Session, ToolbarSettings, color_tag
from .constants import _SSH_CONFIG_DEFAULT_FOLDER
from .core import check_host_reachable
from .ui_components import TooltipPopup

def _create_host_probe_pool():
    return ThreadPoolExecutor(max_workers=8, thread_name_prefix="ssh-host-check")


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
    TAG_HOVER = "hover"

    def __init__(
        self,
        parent: tk.Widget,
        sessions: list[Session],
        img_unchecked: tk.PhotoImage,
        img_checked: tk.PhotoImage,
        on_selection_changed,  # Callable[[int], None]
        initial_open_folders: set[str] | None = None,
        initial_session_colors: dict[str, str] | None = None,
        on_quick_connect=None,           # Callable[[list[Session]], None] | None
        on_connect_sessions=None,        # Callable[[list[Session]], None] | None
        on_edit_session=None,            # Callable[[list[Session]], None] | None
        on_set_sessions_username=None,   # Callable[[list[Session]], None] | None
        on_clear_sessions_username=None, # Callable[[list[Session]], None] | None
        on_delete_session=None,          # Callable[[list[Session]], None] | None
        on_delete_folder=None,           # Callable[[list[Session], str], None] | None
        on_rename_folder=None,           # Callable[[str, str], None] | None  (folder_key, new_name)
        on_add_session=None,             # Callable[[], None] | None
        on_add_session_in_folder=None,   # Callable[[str], None] | None  (folder_key)
        on_duplicate_ssh_alias=None,     # Callable[[list[Session]], None] | None
        on_inspect_ssh_config=None,      # Callable[[list[Session]], None] | None
        on_duplicate_app_session=None,   # Callable[[list[Session]], None] | None
        on_copy_external_session=None,
        on_move_session=None,            # Callable[[list[Session]], None] | None
        on_move_sessions=None,           # Callable[[list[Session]], None] | None
        on_open_ssh_config_in_vscode=None,  # Callable[[], None] | None
        on_deploy_ssh_key=None,             # Callable[[list[Session]], None] | None
        on_remove_ssh_key=None,             # Callable[[list[Session]], None] | None
        on_open_tunnel=None,                # Callable[[list[Session]], None] | None
        on_open_in_winscp=None,             # Callable[[list[Session]], None] | None
        on_run_remote_command=None,         # Callable[[list[Session]], None] | None
        on_run_script=None,                 # Callable[[list[Session], str], None] | None
        on_restart_servers=None,            # Callable[[list[Session]], None] | None
        on_deploy_certificate_files=None,   # Callable[[list[Session]], None] | None
        on_replace_certificates=None,       # Callable[[list[Session]], None] | None
        on_resolve_dns=None,                # Callable[[list[Session]], None] | None
        on_resolve_dns_with_server=None,    # Callable[[list[Session]], None] | None
        on_open_via_jumphost=None,          # Callable[[list[Session]], None] | None
        on_copy_ssh_command=None,           # Callable[[list[Session]], None] | None
        on_ui_state_changed=None,           # Callable[[], None] | None
        notes_getter=None,                  # Callable[[str], str] | None
        on_edit_note=None,                  # Callable[[list[Session]], None] | None
        on_add_favorite=None,               # Callable[[Session, bool], None] | None
        on_add_favorites=None,              # Callable[[list[Session], bool], None] | None
        on_remove_favorite=None,            # Callable[[list[Session]], None] | None
        favorite_keys_getter=None,          # Callable[[], set[str]] | None
        on_hide_column=None,                # Callable[[str], None] | None
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
        self._on_copy_external_session = on_copy_external_session
        self._on_move_session = on_move_session
        self._on_move_sessions = on_move_sessions
        self._on_open_ssh_config_in_vscode = on_open_ssh_config_in_vscode
        self._on_deploy_ssh_key = on_deploy_ssh_key
        self._on_remove_ssh_key = on_remove_ssh_key
        self._on_open_tunnel = on_open_tunnel
        self._on_open_in_winscp = on_open_in_winscp
        self._on_run_remote_command = on_run_remote_command
        self._on_run_script = on_run_script
        self._on_restart_servers = on_restart_servers
        self._on_deploy_certificate_files = on_deploy_certificate_files
        self._on_replace_certificates = on_replace_certificates
        self._on_resolve_dns = on_resolve_dns
        self._on_resolve_dns_with_server = on_resolve_dns_with_server
        self._on_open_via_jumphost = on_open_via_jumphost
        self._on_copy_ssh_command = on_copy_ssh_command
        self._on_ui_state_changed = on_ui_state_changed
        self._notes_getter = notes_getter or (lambda _key: "")
        self._on_edit_note = on_edit_note
        self._on_add_favorite = on_add_favorite
        self._on_add_favorites = on_add_favorites
        self._on_remove_favorite = on_remove_favorite
        self._favorite_keys_getter = favorite_keys_getter or (lambda: set())
        self._on_hide_column = on_hide_column
        self._toolbar_settings = toolbar_settings or ToolbarSettings()
        self._tooltip: TooltipPopup | None = None
        self._tooltip_after_id = None
        self._last_tooltip_item: str | None = None
        self._suppress_next_click = False
        self._left_press_item_id: str | None = None
        self._left_press_was_folder = False
        self._hover_item_id: str | None = None

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
        self._open_folders: set[str] = set(initial_open_folders or set())
        self._pre_search_open_folders: set[str] | None = None
        self._active_filter_query = ""
        self._empty_state: ttk.Frame | None = None
        self._suppress_open_state_events = 0

        self._build()
        self.populate(sessions, open_folders=self._open_folders)

    def _build(self) -> None:
        """Erstellt Treeview + Scrollbar."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._tv = ttk.Treeview(
            self,
            columns=("username", "hostname", "port", "notes"),
            # Native selection is used only as the visible keyboard cursor.
            # Multi-selection continues to be represented by our checkboxes.
            selectmode="browse",
        )
        self._tv.heading("#0", text="Name", anchor="w")
        self._tv.heading("username", text="Benutzer", anchor="w")
        self._tv.heading("hostname", text="Hostname", anchor="w")
        self._tv.heading("port", text="Port", anchor="w")
        self._tv.heading("notes", text="Notizen", anchor="w")
        # Default widths; used as proportional weights when redistributing
        # column widths after visibility changes (see
        # ``_redistribute_column_widths``). All data columns are configured
        # with stretch=True so Tk also fills extra space on window resizes;
        # the explicit redistribution keeps the visual proportions stable
        # after hiding/showing columns.
        self._tv.column("#0", width=self._DEFAULT_COLUMN_WIDTHS["#0"], stretch=True)
        self._tv.column("username", width=self._DEFAULT_COLUMN_WIDTHS["username"], stretch=True)
        self._tv.column("hostname", width=self._DEFAULT_COLUMN_WIDTHS["hostname"], stretch=True)
        self._tv.column("port", width=self._DEFAULT_COLUMN_WIDTHS["port"], stretch=True)
        self._tv.column("notes", width=self._DEFAULT_COLUMN_WIDTHS["notes"], stretch=True)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)

        self._tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._empty_state = ttk.Frame(self, style="EmptyState.TFrame", padding=28)
        self._empty_state.columnconfigure(0, weight=1)
        self._empty_state.rowconfigure(0, weight=1)
        content = ttk.Frame(self._empty_state, style="EmptyStateContent.TFrame", padding=(12, 8))
        content.grid(row=0, column=0)
        content.columnconfigure(0, weight=1)

        ttk.Label(content, text=">_", style="EmptyStateIcon.TLabel").grid(row=0, column=0, pady=(0, 18))
        self._empty_title = tk.StringVar(value="Keine Verbindungen vorhanden")
        self._empty_hint = tk.StringVar(value="Lege deine erste SSH-Verbindung an oder importiere später bestehende Quellen.")
        ttk.Label(
            content,
            textvariable=self._empty_title,
            style="EmptyStateTitle.TLabel",
        ).grid(row=1, column=0, sticky="ew")
        ttk.Label(
            content,
            textvariable=self._empty_hint,
            style="EmptyStateHint.TLabel",
            wraplength=390,
            justify="center",
        ).grid(row=2, column=0, sticky="ew", pady=(8, 22))
        self._empty_add_button = ttk.Button(
            content,
            text="+ Verbindung hinzufügen",
            style="Accent.TButton",
            command=self._empty_add_session,
        )
        self._empty_add_button.grid(row=3, column=0)

        # Events
        self._tv.bind("<ButtonPress-1>", self._on_left_press)
        self._tv.bind("<ButtonRelease-1>", self._on_left_click)
        self._tv.bind("<Double-Button-1>", self._on_double_click)
        self._tv.bind("<ButtonRelease-3>", self._on_right_click)
        self._tv.bind("<Up>", self._on_key_up)
        self._tv.bind("<Down>", self._on_key_down)
        self._tv.bind("<Left>", self._on_key_left)
        self._tv.bind("<Right>", self._on_key_right)
        self._tv.bind("<space>", self._on_key_space)
        self._tv.bind("<Shift-F10>", self._on_key_context_menu)
        self._tv.bind("<Menu>", self._on_key_context_menu)
        self._tv.bind("<FocusIn>", self._on_tree_focus_in)
        self._tv.bind("<<TreeviewOpen>>", lambda e: self._on_tree_folder_open_changed(e, True))
        self._tv.bind("<<TreeviewClose>>", lambda e: self._on_tree_folder_open_changed(e, False))
        self._tv.bind("<Motion>", self._on_tree_motion)
        self._tv.bind("<Leave>", self._on_tree_leave)
        self._tv.bind("<ButtonPress>", lambda _e: self._hide_tooltip(), add="+")

        self._configure_color_tags()
        self._configure_visual_tags()
        self._apply_column_visibility()
        self._build_header_hide_overlay()
        # Redistribute column widths whenever the tree itself is resized so
        # the visible columns always fill the full treeview width.
        self._tv.bind("<Configure>", self._on_tree_configure, add="+")

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
            searching = bool(self._active_filter_query.strip() or self.__dict__.get("_structured_filters"))
            self._empty_title.set("Keine Suchtreffer" if searching else "Keine Verbindungen vorhanden")
            self._empty_hint.set("Ändere oder leere die Suche, um deine Verbindungen wieder anzuzeigen." if searching else "Lege deine erste SSH-Verbindung an oder importiere später bestehende Quellen.")
            if searching:
                self._empty_add_button.grid_remove()
            else:
                self._empty_add_button.grid()
            self._empty_state.grid(row=0, column=0, sticky="nsew")
            self._empty_state.tkraise()

    def _configure_color_tags(self) -> None:
        """Registriert für jede Palettenfarbe einen Treeview-Tag."""
        for _, hex_color in PALETTE:
            self._tv.tag_configure(color_tag(hex_color), foreground=hex_color)

    def _configure_visual_tags(self) -> None:
        """Separates folder rows and hovered rows without changing their data."""
        style = ttk.Style(self)
        folder_background = style.lookup("Treeview.Heading", "background") or "#f8fafc"
        folder_foreground = style.lookup("Treeview.Heading", "foreground") or "#172033"
        folder_font = style.lookup("Treeview.Heading", "font") or "TkDefaultFont"
        hover_background = style.lookup("TreeHover.TFrame", "background") or folder_background
        self._tv.tag_configure(
            self.TAG_FOLDER,
            background=folder_background,
            foreground=folder_foreground,
            font=folder_font,
        )
        self._tv.tag_configure(self.TAG_HOVER, background=hover_background)

    # Default (preferred) column widths. Also used as proportional weights
    # when redistributing widths after a visibility change so the remaining
    # visible columns fill the entire treeview width.
    _DEFAULT_COLUMN_WIDTHS = {
        "#0": 340,
        "username": 110,
        "hostname": 130,
        "port": 60,
        "notes": 220,
    }

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
        # After changing displaycolumns Tk does not redistribute the widths
        # of the (still configured) columns by itself — visible columns keep
        # their previous widths and leave empty space on the right. Force a
        # redistribution so the visible columns always cover the full width.
        self._redistribute_column_widths(ordered)

    def _on_tree_configure(self, _event=None) -> None:
        # Recompute widths when the treeview itself changes size, so the
        # visible columns continue to fill the available area.
        try:
            display = self._tv.cget("displaycolumns")
        except Exception:
            return
        if display in ("#all", ""):
            ordered = [
                c for c in ("username", "hostname", "port", "notes")
                if getattr(self._toolbar_settings, f"show_{c}_column", True)
            ]
        else:
            try:
                ordered = list(display)
            except TypeError:
                ordered = [display]
        self._redistribute_column_widths(ordered)
        # The hide-X overlay position is tied to actual column widths; keep
        # it in sync after a resize.
        if self._header_x_visible_for:
            self._show_header_x_for(self._header_x_visible_for)

    def _redistribute_column_widths(self, visible_data_columns) -> None:
        """Distribute the available treeview width across the visible columns.

        ``#0`` and every visible data column receive a slice proportional to
        their default width. This runs after every visibility change so
        hiding/showing a column never leaves empty space on the right edge
        of the treeview.
        """
        if not hasattr(self, "_tv") or self._tv is None:
            return
        try:
            total = int(self._tv.winfo_width())
        except Exception:
            return
        # Widget not realized yet → retry once the geometry is known.
        if total <= 1:
            try:
                self._tv.after(50,
                    lambda: self._redistribute_column_widths(visible_data_columns)
                )
            except Exception:
                pass
            return

        defaults = self._DEFAULT_COLUMN_WIDTHS
        visible = ["#0", *[c for c in visible_data_columns if c in defaults]]
        weight_sum = sum(defaults.get(c, 0) for c in visible)
        if weight_sum <= 0:
            return

        # Reserve a tiny safety margin so rounding never causes a horizontal
        # scrollbar to appear.
        available = max(total - 2, 0)
        widths: dict[str, int] = {}
        assigned = 0
        for col in visible[:-1]:
            w = max(int(available * defaults[col] / weight_sum), 1)
            widths[col] = w
            assigned += w
        # Last column absorbs the rounding remainder so the total matches
        # exactly.
        widths[visible[-1]] = max(available - assigned, 1)

        for col, w in widths.items():
            try:
                self._tv.column(col, width=w)
            except Exception:
                pass

    def update_toolbar_settings(self, toolbar_settings: ToolbarSettings) -> None:
        self._toolbar_settings = toolbar_settings
        self._apply_column_visibility()
        self._hide_all_header_x()

    # ------------------------------------------------------------------
    # Header "X" overlay: dezenter Schliessen-Button im Spalten-Header.
    # Sichtbar nur on hover, blendet die Spalte ueber die bestehende
    # Settings-Mechanik aus (siehe actions_ui.hide_column_from_header).
    # ------------------------------------------------------------------

    _HIDEABLE_COLUMNS = ("username", "hostname", "port", "notes")

    def _build_header_hide_overlay(self) -> None:
        self._header_x_labels: dict[str, tk.Label] = {}
        self._header_x_visible_for: str | None = None
        self._header_x_hide_after_id: str | None = None
        # Hintergrundfarbe des Treeview-Headers ermitteln (Fallback grau)
        try:
            style = ttk.Style(self)
            header_bg = style.lookup("Treeview.Heading", "background") or "#f8fafc"
            idle_fg = style.lookup("Muted.TLabel", "foreground") or "#687386"
            hover_fg = style.lookup("TLabel", "foreground") or "#172033"
        except tk.TclError:
            header_bg = "#f8fafc"
            idle_fg = "#687386"
            hover_fg = "#172033"
        for column in self._HIDEABLE_COLUMNS:
            lbl = tk.Label(
                self,
                text="\u2715",
                bg=header_bg,
                fg=idle_fg,
                bd=0,
                padx=2,
                pady=0,
                cursor="hand2",
                font=("Segoe UI", 9),
            )
            lbl._idle_fg = idle_fg  # type: ignore[attr-defined]
            lbl._hover_fg = hover_fg  # type: ignore[attr-defined]
            lbl.bind("<Enter>", lambda _e, c=column: self._on_header_x_enter(c))
            lbl.bind("<Leave>", lambda _e, c=column: self._on_header_x_leave(c))
            lbl.bind("<Button-1>", lambda _e, c=column: self._on_header_x_click(c))
            self._header_x_labels[column] = lbl

    def _hide_all_header_x(self) -> None:
        self._cancel_header_x_hide_timer()
        for lbl in getattr(self, "_header_x_labels", {}).values():
            try:
                lbl.place_forget()
            except tk.TclError:
                pass
        self._header_x_visible_for = None

    def _cancel_header_x_hide_timer(self) -> None:
        after_id = getattr(self, "_header_x_hide_after_id", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
            self._header_x_hide_after_id = None

    def _schedule_header_x_hide(self, delay_ms: int = 80) -> None:
        self._cancel_header_x_hide_timer()
        self._header_x_hide_after_id = self.after(delay_ms, self._hide_all_header_x)

    def _column_visible(self, column: str) -> bool:
        attr = f"show_{column}_column"
        return bool(getattr(self._toolbar_settings, attr, False))

    def _column_id_for_index(self, header_index: int) -> str | None:
        # ttk Treeview liefert ueber identify_column einen 1-basierten Index
        # (#0 = Tree-Spalte, #1..#n = sichtbare Daten-Spalten in displaycolumns-Reihenfolge)
        if header_index <= 0:
            return None
        try:
            display = self._tv.cget("displaycolumns")
        except tk.TclError:
            return None
        # display kann Tuple oder "#all" sein
        if isinstance(display, str):
            if display in ("#all", ""):
                ordered = list(self._tv.cget("columns"))
            else:
                ordered = [display]
        else:
            ordered = list(display)
            if ordered == ["#all"]:
                ordered = list(self._tv.cget("columns"))
        if header_index - 1 >= len(ordered):
            return None
        return ordered[header_index - 1]

    def _maybe_show_header_x(self, event_x: int, event_y: int) -> None:
        if not self._on_hide_column:
            return
        try:
            region = self._tv.identify_region(event_x, event_y)
        except tk.TclError:
            return
        if region != "heading":
            self._schedule_header_x_hide()
            return
        col_token = self._tv.identify_column(event_x)
        # col_token z.B. "#0", "#1", ...
        if not col_token or not col_token.startswith("#"):
            self._schedule_header_x_hide()
            return
        try:
            idx = int(col_token[1:])
        except ValueError:
            self._schedule_header_x_hide()
            return
        column = self._column_id_for_index(idx)
        if column not in self._HIDEABLE_COLUMNS or not self._column_visible(column):
            self._schedule_header_x_hide()
            return
        self._cancel_header_x_hide_timer()
        self._show_header_x_for(column)

    def _show_header_x_for(self, column: str) -> None:
        if column == self._header_x_visible_for:
            return
        # alle anderen verstecken
        for col, lbl in self._header_x_labels.items():
            if col != column:
                try:
                    lbl.place_forget()
                except tk.TclError:
                    pass
        lbl = self._header_x_labels.get(column)
        if lbl is None:
            return
        try:
            bbox = self._header_bbox_for_column(column)
        except tk.TclError:
            return
        if bbox is None:
            return
        col_x, col_y, col_w, col_h = bbox
        # Position: rechte Seite des Headers, vertikal mittig
        try:
            req_w = lbl.winfo_reqwidth()
            req_h = lbl.winfo_reqheight()
        except tk.TclError:
            req_w, req_h = 14, 14
        x = col_x + col_w - req_w - 4
        y = col_y + max(0, (col_h - req_h) // 2)
        if x < col_x + 2:
            # Spalte zu schmal: kein X anzeigen
            try:
                lbl.place_forget()
            except tk.TclError:
                pass
            self._header_x_visible_for = None
            return
        try:
            lbl.configure(fg=getattr(lbl, "_idle_fg", "#9aa0a6"))
            lbl.place(in_=self, x=x, y=y)
            lbl.lift()
        except tk.TclError:
            return
        self._header_x_visible_for = column

    def _header_bbox_for_column(self, column: str) -> tuple[int, int, int, int] | None:
        """Liefert (x, y, width, height) des Header-Bereichs einer Datenspalte,
        bezogen auf die Koordinaten des SessionTree-Frames (self)."""
        # x-Offset des Treeviews innerhalb des Frames
        try:
            tv_x = self._tv.winfo_x()
            tv_y = self._tv.winfo_y()
        except tk.TclError:
            return None
        # Header-Hoehe via ttk Style ermitteln; Fallback ~22
        try:
            style = ttk.Style(self)
            row_h = int(style.lookup("Treeview.Heading", "rowheight") or 0)
        except (tk.TclError, ValueError):
            row_h = 0
        if row_h <= 0:
            # Versuch: erste Datenzeile bbox -> y_top deren bbox = Header-Hoehe
            try:
                children = self._tv.get_children("")
                if children:
                    first_bbox = self._tv.bbox(children[0])
                    if first_bbox:
                        row_h = first_bbox[1]
            except tk.TclError:
                pass
        if row_h <= 0:
            row_h = 22
        # x-Offset der Spalte: tree-spalte #0 plus alle vorhergehenden sichtbaren Datenspalten
        try:
            # Breite #0
            x0 = int(self._tv.column("#0", "width"))
        except tk.TclError:
            return None
        # displaycolumns Reihenfolge
        try:
            display = self._tv.cget("displaycolumns")
        except tk.TclError:
            return None
        if isinstance(display, str):
            ordered: list[str] = list(self._tv.cget("columns")) if display in ("#all", "") else [display]
        else:
            ordered = list(display)
            if ordered == ["#all"]:
                ordered = list(self._tv.cget("columns"))
        if column not in ordered:
            return None
        x_offset = x0
        for col in ordered:
            try:
                w = int(self._tv.column(col, "width"))
            except tk.TclError:
                return None
            if col == column:
                return (tv_x + x_offset, tv_y, w, row_h)
            x_offset += w
        return None

    def _on_header_x_enter(self, column: str) -> None:
        self._cancel_header_x_hide_timer()
        lbl = self._header_x_labels.get(column)
        if lbl is not None:
            try:
                lbl.configure(fg=getattr(lbl, "_hover_fg", "#202124"))
            except tk.TclError:
                pass

    def _on_header_x_leave(self, column: str) -> None:
        lbl = self._header_x_labels.get(column)
        if lbl is not None:
            try:
                lbl.configure(fg=getattr(lbl, "_idle_fg", "#9aa0a6"))
            except tk.TclError:
                pass
        self._schedule_header_x_hide()

    def _on_header_x_click(self, column: str) -> None:
        if not self._on_hide_column:
            return
        # erst verstecken, dann Action ausloesen (Settings-Update zieht
        # update_toolbar_settings nach sich, das wuerde sowieso aufraeumen).
        self._hide_all_header_x()
        try:
            self._on_hide_column(column)
        except Exception:
            # nicht silent verschlucken im Tk-Mainloop: messagebox
            messagebox.showerror("Spalte ausblenden", "Spalte konnte nicht ausgeblendet werden.", parent=self)

    def _on_tree_leave(self, _event: tk.Event) -> None:
        self._set_hover_item(None)
        self._hide_tooltip()
        # X nicht sofort verstecken: wenn der Mauszeiger das X-Label betritt,
        # erhaelt der Treeview ein <Leave>, aber das X soll bleiben.
        self._schedule_header_x_hide()

    def _on_tree_motion(self, event: tk.Event) -> None:
        # Header-Hide-X aktualisieren (unabhaengig vom Notes-Tooltip)
        self._maybe_show_header_x(event.x, event.y)
        item_id = self._tv.identify_row(event.y)
        self._set_hover_item(item_id or None)
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

    def _set_hover_item(self, item_id: str | None) -> None:
        if item_id == self._hover_item_id:
            return
        previous = self._hover_item_id
        self._hover_item_id = item_id
        for candidate, add_hover in ((previous, False), (item_id, True)):
            if not candidate or not self._tv.exists(candidate):
                continue
            tags = [tag for tag in self._tv.item(candidate, "tags") if tag != self.TAG_HOVER]
            if add_hover:
                tags.append(self.TAG_HOVER)
            self._tv.item(candidate, tags=tuple(tags))

    def _show_tooltip(self, item_id: str, x: int, y: int, text: str) -> None:
        if item_id != self._last_tooltip_item:
            return
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._tooltip_after_id = None
        self._tooltip = TooltipPopup(self, text, x, y, wraplength=420, offset=(12, 12))

    def _hide_tooltip(self) -> None:
        if self._tooltip_after_id:
            self.after_cancel(self._tooltip_after_id)
            self._tooltip_after_id = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._last_tooltip_item = None

    def get_open_folders(self) -> set[str]:
        """Gibt folder_keys der vom Benutzer geöffneten Ordner zurück."""
        return set(getattr(self, "_open_folders", set()))

    def _set_cached_folder_open(self, folder_key: str, state: bool) -> None:
        if not folder_key:
            return
        if state:
            self._open_folders.add(folder_key)
        else:
            self._open_folders.discard(folder_key)

    def _on_tree_folder_open_changed(self, event: tk.Event, state: bool) -> None:
        if getattr(self, "_suppress_open_state_events", 0):
            return
        # During search the tree uses a temporary "all matching folders open"
        # view. Do not let those transient open/close events replace the real
        # user folder state that gets restored when the search is cleared.
        if getattr(self, "_active_filter_query", "").strip() or self.__dict__.get("_structured_filters"):
            return
        item_id = ""
        widget = getattr(event, "widget", None)
        try:
            item_id = widget.focus() if widget is not None else self._tv.focus()
        except tk.TclError:
            item_id = ""
        folder_key = self._item_to_folder_key.get(item_id)
        if not folder_key:
            return
        self._set_cached_folder_open(folder_key, state)
        self._notify_ui_state_changed()

    def open_folder_key(self, folder_key: str) -> None:
        """Öffnet einen sichtbaren Ordner anhand seines folder_key."""
        for item_id, fkey in self._item_to_folder_key.items():
            if fkey == folder_key:
                self._suppress_open_state_events += 1
                try:
                    self._tv.item(item_id, open=True)
                finally:
                    self._suppress_open_state_events -= 1
                self._set_cached_folder_open(folder_key, True)
                self._notify_ui_state_changed()
                break

    def get_session_colors(self) -> dict[str, str]:
        """Gibt eine Kopie des aktuellen session_key → hex Mappings zurück."""
        return dict(self._session_colors)

    def _notify_ui_state_changed(self) -> None:
        if getattr(self, "_suppress_open_state_events", 0):
            return
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
                tag = color_tag(hex_color) if hex_color else None
                tags = (self.TAG_SESSION,) + ((tag,) if tag else ())
                if item_id == getattr(self, "_hover_item_id", None):
                    tags += (self.TAG_HOVER,)
                self._tv.item(item_id, tags=tags)
                break
        self._notify_ui_state_changed()

    def populate(
        self,
        sessions: list[Session],
        open_folders: set[str] | None = None,
        *,
        update_open_state: bool = True,
    ) -> None:
        """Füllt den Baum mit Sessions. Löscht vorherige Inhalte."""
        self._populate_generation = getattr(self, "_populate_generation", 0) + 1
        focus_identity = self._focused_identity()
        # Zustand merken (welche Ordner waren offen?) – falls nicht extern übergeben
        if open_folders is None:
            open_folders = self.get_open_folders()

        open_folders = set(open_folders)
        if update_open_state:
            self._open_folders = set(open_folders)

        self._suppress_open_state_events += 1
        try:
            # Alles löschen
            self._tv.delete(*self._tv.get_children())
            self._item_to_session.clear()
            self._checked.clear()
            self._item_to_folder_key.clear()
            self._item_to_status.clear()
            self._hover_item_id = None

            # Ordner-Nodes: folder_key → item_id
            folder_items: dict[str, str] = {}

            for session in sessions:
                # Ordner-Hierarchie aufbauen
                parent_id = ""
                for depth, folder_name in enumerate(session.folder_path):
                    folder_key = "/".join(session.folder_path[: depth + 1])
                    if folder_key not in folder_items:
                        was_open = folder_key in open_folders
                        folder_label = f"  {folder_name}"
                        folder_id = self._tv.insert(
                            parent_id, "end",
                            text=folder_label,
                            open=was_open,
                            tags=(self.TAG_FOLDER,),
                        )
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
        finally:
            self._suppress_open_state_events -= 1

        self._update_empty_state(sessions)
        self._restore_focus_identity(focus_identity)

    def _focused_identity(self) -> tuple[str, ...] | None:
        """Return a stable identity for the keyboard cursor across rebuilds."""
        try:
            item_id = self._tv.focus()
        except (AttributeError, tk.TclError):
            return None
        if item_id in self._item_to_folder_key:
            return ("folder", self._item_to_folder_key[item_id])
        session = self._item_to_session.get(item_id)
        if session is not None:
            return ("session", session.key, session.folder_key)
        return None

    def _restore_focus_identity(self, identity: tuple[str, ...] | None) -> None:
        target = ""
        if identity and identity[0] == "folder":
            target = next(
                (iid for iid, key in self._item_to_folder_key.items() if key == identity[1]),
                "",
            )
        elif identity and identity[0] == "session":
            target = next(
                (
                    iid
                    for iid, session in self._item_to_session.items()
                    if session.key == identity[1] and session.folder_key == identity[2]
                ),
                "",
            )
        if target and not self._is_item_visible(target):
            target = ""
        if not target:
            roots = self._tv.get_children("")
            target = roots[0] if roots else ""
        if target:
            self._focus_item(target, reveal=False)

    def _is_item_visible(self, item_id: str) -> bool:
        parent = self._tv.parent(item_id)
        while parent:
            if not self._tv.item(parent, "open"):
                return False
            parent = self._tv.parent(parent)
        return True

    def _focus_item(self, item_id: str, *, reveal: bool = True) -> None:
        if not item_id:
            return
        self._tv.focus(item_id)
        self._tv.selection_set(item_id)
        if reveal:
            self._tv.see(item_id)

    def has_keyboard_focus(self) -> bool:
        try:
            return self.focus_get() == self._tv
        except (AttributeError, tk.TclError):
            return False

    def _on_tree_focus_in(self, _event: tk.Event) -> None:
        if not self._tv.focus():
            self._restore_focus_identity(None)

    def _next_visible_item(self, item_id: str) -> str:
        if not item_id:
            roots = self._tv.get_children("")
            return roots[0] if roots else ""
        if self._tv.item(item_id, "open"):
            children = self._tv.get_children(item_id)
            if children:
                return children[0]
        current = item_id
        while current:
            sibling = self._tv.next(current)
            if sibling:
                return sibling
            current = self._tv.parent(current)
        return item_id

    def _previous_visible_item(self, item_id: str) -> str:
        if not item_id:
            roots = self._tv.get_children("")
            return roots[0] if roots else ""
        sibling = self._tv.prev(item_id)
        if not sibling:
            return self._tv.parent(item_id) or item_id
        current = sibling
        while self._tv.item(current, "open"):
            children = self._tv.get_children(current)
            if not children:
                break
            current = children[-1]
        return current

    def _move_focus(self, direction: int) -> str:
        current = self._tv.focus()
        target = self._next_visible_item(current) if direction > 0 else self._previous_visible_item(current)
        self._focus_item(target)
        return "break"

    def _on_key_up(self, _event: tk.Event) -> str:
        return self._move_focus(-1)

    def _on_key_down(self, _event: tk.Event) -> str:
        return self._move_focus(1)

    def _set_folder_open(self, item_id: str, state: bool) -> None:
        self._suppress_open_state_events += 1
        try:
            self._tv.item(item_id, open=state)
        finally:
            self._suppress_open_state_events -= 1
        if not (self._active_filter_query.strip() or self.__dict__.get("_structured_filters")):
            folder_key = self._item_to_folder_key.get(item_id, "")
            self._set_cached_folder_open(folder_key, state)
            self._notify_ui_state_changed()

    def _on_key_right(self, _event: tk.Event) -> str:
        item_id = self._tv.focus()
        if item_id in self._item_to_folder_key:
            if not self._tv.item(item_id, "open"):
                self._set_folder_open(item_id, True)
            else:
                children = self._tv.get_children(item_id)
                if children:
                    self._focus_item(children[0])
        return "break"

    def _on_key_left(self, _event: tk.Event) -> str:
        item_id = self._tv.focus()
        if item_id in self._item_to_folder_key and self._tv.item(item_id, "open"):
            self._set_folder_open(item_id, False)
        elif item_id:
            parent = self._tv.parent(item_id)
            if parent:
                self._focus_item(parent)
        return "break"

    def activate_focused(self) -> None:
        """Toggle a focused folder or quick-connect the focused session."""
        item_id = self._tv.focus()
        if item_id in self._item_to_folder_key:
            self._set_folder_open(item_id, not bool(self._tv.item(item_id, "open")))
            return
        session = self._item_to_session.get(item_id)
        if session is not None and self._on_quick_connect:
            self._on_quick_connect(session)

    def _folder_session_item_ids(self, folder_item_id: str) -> list[str]:
        result: list[str] = []
        for child_id in self._tv.get_children(folder_item_id):
            if child_id in self._item_to_session:
                result.append(child_id)
            elif child_id in self._item_to_folder_key:
                result.extend(self._folder_session_item_ids(child_id))
        return result

    def _on_key_space(self, _event: tk.Event) -> str:
        item_id = self._tv.focus()
        if item_id in self._item_to_session:
            self._toggle(item_id)
        elif item_id in self._item_to_folder_key:
            session_items = self._folder_session_item_ids(item_id)
            if session_items:
                new_state = not all(self._checked.get(iid, False) for iid in session_items)
                self._set_folder_checked(item_id, new_state)
        return "break"

    def _on_key_context_menu(self, _event: tk.Event) -> str:
        item_id = self._tv.focus()
        if not item_id:
            return "break"
        self._tv.see(item_id)
        bbox = self._tv.bbox(item_id)
        if not bbox:
            return "break"
        x, y, width, height = bbox
        x_root = self._tv.winfo_rootx() + x + min(max(width // 3, 24), 180)
        y_root = self._tv.winfo_rooty() + y + height
        if item_id in self._item_to_folder_key:
            self._show_folder_menu(item_id, x_root=x_root, y_root=y_root)
        elif item_id in self._item_to_session:
            self._show_session_menu(item_id, x_root=x_root, y_root=y_root)
        return "break"

    def get_visible_sessions_markdown(self) -> str:
        """Gibt die aktuell im Baum angezeigten Sessions als Markdown zurück."""
        lines: list[str] = []

        def _append_children(parent_id: str, folder_depth: int) -> None:
            for item_id in self._tv.get_children(parent_id):
                folder_key = self._item_to_folder_key.get(item_id)
                if folder_key is not None:
                    folder_name = folder_key.rsplit("/", 1)[-1]
                    if lines and lines[-1] != "":
                        lines.append("")
                    lines.extend((f"{'#' * (folder_depth + 1)} {folder_name}", ""))
                    _append_children(item_id, folder_depth + 1)
                    continue

                session = self._item_to_session.get(item_id)
                if session is not None:
                    lines.append(f"- {session.display_name}, {session.hostname}")

        _append_children("", 0)
        return "\n".join(lines).strip()

    def get_visible_sessions_by_folder(self) -> list[tuple[str, list[Session]]]:
        """Gruppiert die aktuell angezeigten Sessions in der sichtbaren Baumreihenfolge."""
        groups: list[tuple[str, list[Session]]] = []

        def _collect(parent_id: str) -> None:
            direct_sessions = [
                self._item_to_session[item_id]
                for item_id in self._tv.get_children(parent_id)
                if item_id in self._item_to_session
            ]
            if direct_sessions:
                groups.append((self._item_to_folder_key.get(parent_id, ""), direct_sessions))
            for item_id in self._tv.get_children(parent_id):
                if item_id in self._item_to_folder_key:
                    _collect(item_id)

        _collect("")
        return groups

    def _on_left_press(self, event: tk.Event) -> None:
        """Merkt, auf welcher Zeile der Linksklick begonnen hat.

        Treeview klappt Ordner bereits bei ButtonPress auf/zu. Wenn sich dadurch
        Zeilen verschieben, darf ButtonRelease nicht versehentlich eine nun unter
        der Maus liegende Session anhaken.
        """
        item_id = self._tv.identify_row(event.y)
        self._left_press_item_id = item_id or None
        self._left_press_was_folder = bool(item_id and self.TAG_FOLDER in self._tv.item(item_id, "tags"))

    def _on_left_click(self, event: tk.Event) -> None:
        """Checkbox togglen wenn Press und Release auf derselben Session-Zeile liegen."""
        if self._suppress_next_click:
            self._suppress_next_click = False
            self._left_press_item_id = None
            self._left_press_was_folder = False
            return
        item_id = self._tv.identify_row(event.y)
        press_item_id = self._left_press_item_id
        press_was_folder = self._left_press_was_folder
        self._left_press_item_id = None
        self._left_press_was_folder = False
        if not item_id or press_was_folder or item_id != press_item_id:
            return
        self._focus_item(item_id)
        if self.TAG_SESSION not in self._tv.item(item_id, "tags"):
            return
        self._toggle(item_id)

    def _on_double_click(self, event: tk.Event) -> None:
        """Einzelne Session per Doppelklick direkt öffnen."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        self._focus_item(item_id)
        if self.TAG_SESSION not in self._tv.item(item_id, "tags"):
            return
        self._suppress_next_click = True
        if self._on_quick_connect:
            self._on_quick_connect(self._item_to_session[item_id])

    def _toggle(self, item_id: str) -> None:
        """Checkbox-Zustand einer Session-Zeile umschalten."""
        new_state = not self._checked.get(item_id, False)
        key = self._item_to_session[item_id].key
        for iid, session in self._item_to_session.items():
            if session.key == key:
                self._checked[iid] = new_state
                self._tv.item(iid, image=self._img_checked if new_state else self._img_unchecked)
        self._notify_count()
        self._notify_ui_state_changed()

    def _notify_count(self) -> None:
        # Eine Session kann mehrfach im Baum erscheinen (z. B. im Ordner
        # "↺ Zuletzt verwendet" zusätzlich zu ihrer normalen Position).
        # Für den Counter und die Verbinden-Logik zählt jede Session aber
        # nur einmal – sonst öffnen wir nach einem Connect plötzlich
        # doppelt so viele Terminals wie ausgewählt.
        count = len({
            self._item_to_session[iid].key
            for iid, checked in self._checked.items()
            if checked and iid in self._item_to_session
        } | set(self.__dict__.get("_hidden_selected", {})))
        self._on_selection_changed(count)

    def get_selected_sessions(self) -> list[Session]:
        """Gibt alle ausgewählten (gecheckte) Sessions zurück – dedupliziert nach session.key."""
        result: list[Session] = []
        seen: set[str] = set()
        for iid, checked in self._checked.items():
            if not checked:
                continue
            session = self._item_to_session.get(iid)
            if session is None or session.key in seen:
                continue
            seen.add(session.key)
            result.append(session)
        for key, session in self.__dict__.get("_hidden_selected", {}).items():
            if key not in seen:
                seen.add(key)
                result.append(session)
        return result

    def hidden_selected_keys(self) -> set[str]:
        return set(self.__dict__.get("_hidden_selected", {}))

    def remove_from_selection(self, key: str) -> None:
        self.__dict__.get("_hidden_selected", {}).pop(key, None)
        for iid, session in self._item_to_session.items():
            if session.key == key:
                self._checked[iid] = False
                self._tv.item(iid, image=self._img_unchecked)
        self._notify_count()
        self._notify_ui_state_changed()

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
        if not state:
            self.__dict__.get("_hidden_selected", {}).clear()
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
            if child_id in self._item_to_session:
                self._checked[child_id] = state
                self._tv.item(
                    child_id,
                    image=self._img_checked if state else self._img_unchecked,
                )
            elif child_id in self._item_to_folder_key:
                self._set_folder_checked_inner(child_id, state)

    def _on_right_click(self, event: tk.Event) -> None:
        """Kontextmenü je nach Zeilentyp anzeigen."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        self._focus_item(item_id)
        tags = self._tv.item(item_id, "tags")
        if self.TAG_FOLDER in tags:
            self._show_folder_menu(item_id, event)
        elif self.TAG_SESSION in tags:
            self._show_session_menu(item_id, event)

    def _set_folder_open_recursive(self, folder_item_id: str, state: bool) -> None:
        """Klappt einen Ordner rekursiv auf oder zu."""
        changed: list[str] = []

        def apply(item_id: str) -> None:
            folder_key = self._item_to_folder_key.get(item_id)
            if folder_key:
                changed.append(folder_key)
            self._tv.item(item_id, open=state)
            for child_id in self._tv.get_children(item_id):
                if self.TAG_FOLDER in self._tv.item(child_id, "tags"):
                    apply(child_id)

        self._suppress_open_state_events += 1
        try:
            apply(folder_item_id)
        finally:
            self._suppress_open_state_events -= 1
        for folder_key in changed:
            self._set_cached_folder_open(folder_key, state)
        self._notify_ui_state_changed()

    def _show_folder_menu(
        self,
        item_id: str,
        event: tk.Event | None = None,
        *,
        x_root: int | None = None,
        y_root: int | None = None,
    ) -> None:
        """Kontextmenü für Ordner-Zeilen, in kurze thematische Gruppen geteilt."""
        folder_key = self._item_to_folder_key.get(item_id, "")
        folder_sessions = self._get_folder_sessions(item_id)
        count = len(folder_sessions)
        menu = tk.Menu(self, tearoff=False)

        if self._on_connect_sessions and folder_sessions:
            menu.add_command(
                label=f"Alle im Ordner verbinden ({count})",
                command=lambda ss=list(folder_sessions): self._on_connect_sessions(ss),
            )
        if self._on_add_session_in_folder:
            menu.add_command(
                label="Neue Verbindung hier…",
                command=lambda fk=folder_key: self._on_add_session_in_folder(fk),
            )

        selection_menu = tk.Menu(menu, tearoff=False)
        selection_menu.add_command(label="Alle auswählen", command=lambda: self._set_folder_checked(item_id, True))
        selection_menu.add_command(label="Alle abwählen", command=lambda: self._set_folder_checked(item_id, False))
        selection_menu.add_separator()
        selection_menu.add_command(label="Unterordner ausklappen", command=lambda: self._set_folder_open_recursive(item_id, True))
        selection_menu.add_command(label="Unterordner einklappen", command=lambda: self._set_folder_open_recursive(item_id, False))
        menu.add_cascade(label="Auswahl und Ansicht", menu=selection_menu)

        if folder_sessions:
            tools_menu = tk.Menu(menu, tearoff=False)
            winscp_sessions = [s for s in folder_sessions if s.source == "winscp"]
            if winscp_sessions and self._on_open_in_winscp:
                tools_menu.add_command(label=f"In WinSCP öffnen ({len(winscp_sessions)})", command=lambda ss=winscp_sessions: self._on_open_in_winscp(ss))
            if self._on_run_remote_command:
                tools_menu.add_command(label=f"Remote-Befehl ausführen… ({count})", command=lambda ss=list(folder_sessions): self._on_run_remote_command(ss))
            restart_servers = getattr(self, "_on_restart_servers", None)
            if restart_servers:
                tools_menu.add_command(label=f"Server neu starten… ({count})", command=lambda ss=list(folder_sessions), callback=restart_servers: callback(ss))
            if getattr(self, "_on_deploy_certificate_files", None):
                tools_menu.add_command(label=f"Dateien verteilen… ({count})", command=lambda ss=list(folder_sessions): self._on_deploy_certificate_files(ss))
            if getattr(self, "_on_replace_certificates", None):
                tools_menu.add_command(label=f"Zertifikate ersetzen… ({count})", command=lambda ss=list(folder_sessions): self._on_replace_certificates(ss))
            tools_menu.add_separator()
            tools_menu.add_command(label=f"Hosts prüfen ({count})", command=lambda fid=item_id: self.check_folder_hosts(fid))
            dns_sessions = [s for s in folder_sessions if s.hostname]
            if dns_sessions and self._on_resolve_dns:
                tools_menu.add_command(label=f"DNS/IP auflösen… ({len(dns_sessions)})", command=lambda ss=list(dns_sessions): self._on_resolve_dns(ss))
            if self._on_deploy_ssh_key:
                tools_menu.add_command(label=f"SSH Key übertragen… ({count})", command=lambda ss=list(folder_sessions): self._on_deploy_ssh_key(ss))
            if self._on_remove_ssh_key:
                tools_menu.add_command(label=f"SSH Key entfernen… ({count})", command=lambda ss=list(folder_sessions): self._on_remove_ssh_key(ss))
            menu.add_cascade(label="Serveraktionen", menu=tools_menu)

            manage_menu = tk.Menu(menu, tearoff=False)
            if self._on_set_sessions_username:
                manage_menu.add_command(label=f"Benutzer setzen… ({count})", command=lambda ss=list(folder_sessions): self._on_set_sessions_username(ss))
            if self._on_clear_sessions_username:
                manage_menu.add_command(label=f"Benutzer entfernen… ({count})", command=lambda ss=list(folder_sessions): self._on_clear_sessions_username(ss))
            favorite_keys = self._favorite_keys_getter()
            not_favorite = [s for s in folder_sessions if s.key not in favorite_keys]
            if not_favorite and self._on_add_favorites:
                manage_menu.add_command(label=f"Zu Favoriten hinzufügen… ({len(not_favorite)})", command=lambda ss=list(not_favorite): self._add_favorites_with_dialog(ss))
            color_menu = tk.Menu(manage_menu, tearoff=False)
            for name, hex_color in PALETTE:
                color_menu.add_command(label=name, command=lambda hc=hex_color, ss=list(folder_sessions): [self.set_session_color(s.key, hc) for s in ss])
            color_menu.add_separator()
            color_menu.add_command(label="Farbe entfernen", command=lambda ss=list(folder_sessions): [self.set_session_color(s.key, None) for s in ss])
            manage_menu.add_cascade(label="Farbe für alle", menu=color_menu)
            if all(s.source in ("app", "ssh_alias") for s in folder_sessions) and self._on_rename_folder:
                manage_menu.add_command(label="Ordner umbenennen…", command=lambda fk=folder_key: self._on_rename_folder(fk))
            menu.add_cascade(label="Verwalten", menu=manage_menu)

            copy_menu = tk.Menu(menu, tearoff=False)
            if self._on_copy_ssh_command:
                copy_menu.add_command(label=f"SSH-Befehle ({count})", command=lambda ss=list(folder_sessions): self._on_copy_ssh_command(ss))
            copy_menu.add_command(label=f"Hostnames ({count})", command=lambda ss=list(folder_sessions): self._copy_session_values(ss, "hostname"))
            copy_menu.add_command(label=f"Namen ({count})", command=lambda ss=list(folder_sessions): self._copy_session_values(ss, "display_name"))
            copy_menu.add_command(label=f"Notizen ({count})", command=lambda ss=list(folder_sessions): self._copy_session_notes(ss))
            menu.add_cascade(label="Kopieren", menu=copy_menu)

        if folder_key == _SSH_CONFIG_DEFAULT_FOLDER and self._on_open_ssh_config_in_vscode:
            menu.add_separator()
            menu.add_command(label="SSH Config in VS Code öffnen", command=self._on_open_ssh_config_in_vscode)
        if folder_sessions and all(s.source in ("app", "ssh_alias") for s in folder_sessions) and self._on_delete_folder:
            menu.add_separator()
            menu.add_command(label="Ordner löschen", command=lambda ss=list(folder_sessions), fk=folder_key: self._on_delete_folder(ss, fk))
        menu.tk_popup(
            event.x_root if event is not None else int(x_root or 0),
            event.y_root if event is not None else int(y_root or 0),
        )

    def _show_session_menu(
        self,
        item_id: str,
        event: tk.Event | None = None,
        *,
        x_root: int | None = None,
        y_root: int | None = None,
    ) -> None:
        """Kontextmenü für Session-Zeilen, thematisch in Sektionen sortiert."""
        session = self._item_to_session[item_id]
        selected = self.get_selected_sessions()
        selected_count = len(selected)
        favorite_keys = self._favorite_keys_getter()
        current_color = self._session_colors.get(session.key)

        menu = tk.Menu(self, tearoff=False)
        favorite_menu = tk.Menu(menu, tearoff=False)
        manage_menu = tk.Menu(menu, tearoff=False)
        copy_menu = tk.Menu(menu, tearoff=False)
        tools_menu = tk.Menu(menu, tearoff=False)
        security_menu = tk.Menu(menu, tearoff=False)
        appearance_menu = tk.Menu(menu, tearoff=False)

        # Öffnen / Verbinden – immer ganz oben.
        menu.add_command(label=f"Diese Verbindung: {session.display_name}", state="disabled")
        menu.add_command(label=f"Häkchen-Auswahl: {selected_count} Verbindung(en)", state="disabled")
        menu.add_separator()
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
        if session.key in favorite_keys:
            if self._on_remove_favorite:
                favorite_menu.add_command(
                    label="Aus Favoriten entfernen",
                    command=lambda s=session: self._on_remove_favorite(s),
                )
        elif self._on_add_favorite:
            favorite_menu.add_command(
                label="Zu Favoriten hinzufügen…",
                command=lambda s=session: self._add_favorite_with_dialog(s),
            )
        if selected_count >= 2:
            not_favorite = [s for s in selected if s.key not in favorite_keys]
            if not_favorite and self._on_add_favorites:
                favorite_menu.add_command(
                    label=f"Auswahl zu Favoriten hinzufügen… ({len(not_favorite)})",
                    command=lambda ss=list(not_favorite): self._add_favorites_with_dialog(ss),
                )

        # Bearbeiten / Organisation.
        if self._on_edit_session:
            manage_menu.add_command(
                label="Bearbeiten…",
                command=lambda s=session: self._on_edit_session(s),
            )
        if session.source in ("winscp", "filezilla_config") and self._on_copy_external_session:
            manage_menu.add_command(label="Als eigene Verbindung übernehmen…", command=lambda s=session: self._on_copy_external_session(s))
        if session.is_app_session:
            if self._on_duplicate_app_session:
                manage_menu.add_command(
                    label="Duplizieren…",
                    command=lambda s=session: self._on_duplicate_app_session(s),
                )
            if self._on_move_session:
                manage_menu.add_command(
                    label="In Ordner verschieben…",
                    command=lambda s=session: self._on_move_session(s),
                )
        if self._on_set_sessions_username:
            manage_menu.add_command(
                label="Benutzer setzen…",
                command=lambda s=session: self._on_set_sessions_username([s]),
            )
        if self._on_clear_sessions_username:
            manage_menu.add_command(
                label="Benutzer entfernen…",
                command=lambda s=session: self._on_clear_sessions_username([s]),
            )
        if session.source == "ssh_config":
            if self._on_duplicate_ssh_alias:
                manage_menu.add_command(
                    label="Alias als App-Eintrag übernehmen…",
                    command=lambda s=session: self._on_duplicate_ssh_alias(s),
                )
        elif session.is_ssh_alias_copy:
            if self._on_move_session:
                manage_menu.add_command(
                    label="In Ordner verschieben…",
                    command=lambda s=session: self._on_move_session(s),
                )
        if selected_count >= 2:
            moveable = [s for s in selected if s.source in ("app", "ssh_alias")]
            if moveable and self._on_move_sessions:
                manage_menu.add_command(
                    label=f"Ordner für Auswahl ändern… ({len(moveable)})",
                    command=lambda ss=moveable: self._on_move_sessions(ss),
                )
            if self._on_set_sessions_username:
                manage_menu.add_command(
                    label=f"Benutzer für Auswahl setzen… ({selected_count})",
                    command=lambda ss=list(selected): self._on_set_sessions_username(ss),
                )
            if self._on_clear_sessions_username:
                manage_menu.add_command(
                    label=f"Benutzer für Auswahl entfernen… ({selected_count})",
                    command=lambda ss=list(selected): self._on_clear_sessions_username(ss),
                )

        # Kopieren – alles zusammen in eigener Sektion.
        if self._on_copy_ssh_command:
            copy_menu.add_command(
                label="SSH-Befehl kopieren",
                command=lambda s=session: self._on_copy_ssh_command([s]),
            )
        copy_menu.add_command(
            label="Hostname kopieren",
            command=lambda s=session: self._copy_session_values([s], "hostname"),
        )
        copy_menu.add_command(
            label="Name kopieren",
            command=lambda s=session: self._copy_session_values([s], "display_name"),
        )
        copy_menu.add_command(
            label="Notiz kopieren",
            command=lambda s=session: self._copy_session_notes([s]),
        )
        if selected_count >= 2:
            if self._on_copy_ssh_command:
                copy_menu.add_command(
                    label=f"Auswahl-SSH-Befehle kopieren ({selected_count})",
                    command=lambda ss=list(selected): self._on_copy_ssh_command(ss),
                )
            copy_menu.add_command(
                label=f"Auswahl-Hostnamen kopieren ({selected_count})",
                command=lambda ss=list(selected): self._copy_session_values(ss, "hostname"),
            )
            copy_menu.add_command(
                label=f"Auswahl-Namen kopieren ({selected_count})",
                command=lambda ss=list(selected): self._copy_session_values(ss, "display_name"),
            )
            copy_menu.add_command(
                label=f"Auswahl-Notizen kopieren ({selected_count})",
                command=lambda ss=list(selected): self._copy_session_notes(ss),
            )

        # Tools / Aktionen.
        if self._on_open_tunnel:
            tools_menu.add_command(
                label="Tunnel öffnen…",
                command=lambda s=session: self._on_open_tunnel(s),
            )
        if self._on_open_via_jumphost:
            tools_menu.add_command(
                label="Über Jumphost öffnen…",
                command=lambda s=session: self._on_open_via_jumphost(s),
            )
        if self._on_run_remote_command:
            tools_menu.add_command(
                label="Befehl ausführen…",
                command=lambda s=session: self._on_run_remote_command([s]),
            )
            selected_runnable = [s for s in selected if s.hostname]
            if len(selected_runnable) >= 2:
                tools_menu.add_command(
                    label=f"Befehl auf Auswahl ausführen… ({len(selected_runnable)})",
                    command=lambda ss=selected_runnable: self._on_run_remote_command(ss),
                )
        run_script = self.__dict__.get("_on_run_script")
        if run_script:
            for mode, label in (("local_script", "Lokales Skript ausführen…"), ("remote_script", "Serverskript ausführen…")):
                tools_menu.add_command(label=label, command=lambda m=mode, s=session: run_script([s], m))
        restart_servers = getattr(self, "_on_restart_servers", None)
        if restart_servers and session.hostname:
            tools_menu.add_command(
                label="Server neu starten…",
                command=lambda s=session, callback=restart_servers: callback([s]),
            )
            selected_runnable = [s for s in selected if s.hostname]
            if len(selected_runnable) >= 2:
                tools_menu.add_command(
                    label=f"Server aus Auswahl neu starten… ({len(selected_runnable)})",
                    command=lambda ss=selected_runnable, callback=restart_servers: callback(ss),
                )
        if getattr(self, "_on_deploy_certificate_files", None) and session.hostname:
            tools_menu.add_command(
                label="Dateien verteilen…",
                command=lambda s=session: self._on_deploy_certificate_files([s]),
            )
            selected_runnable = [s for s in selected if s.hostname]
            if len(selected_runnable) >= 2:
                tools_menu.add_command(
                    label=f"Dateien auf Auswahl übertragen… ({len(selected_runnable)})",
                    command=lambda ss=selected_runnable: self._on_deploy_certificate_files(ss),
                )
        if getattr(self, "_on_replace_certificates", None) and session.hostname:
            tools_menu.add_command(label="Zertifikate ersetzen…", command=lambda s=session: self._on_replace_certificates([s]))
            selected_runnable = [s for s in selected if s.hostname]
            if len(selected_runnable) >= 2:
                tools_menu.add_command(label=f"Zertifikate auf Auswahl ersetzen… ({len(selected_runnable)})", command=lambda ss=selected_runnable: self._on_replace_certificates(ss))
        if self._on_resolve_dns and session.hostname:
            tools_menu.add_command(
                label="DNS/IP auflösen…",
                command=lambda s=session: self._on_resolve_dns([s]),
            )
            if self._on_resolve_dns_with_server:
                tools_menu.add_command(
                    label="DNS/IP auflösen… (DNS-Auswahl)",
                    command=lambda s=session: self._on_resolve_dns_with_server([s]),
                )
            selected_dns = [s for s in selected if s.hostname]
            if len(selected_dns) >= 2:
                tools_menu.add_command(
                    label=f"DNS/IP für Auswahl auflösen… ({len(selected_dns)})",
                    command=lambda ss=selected_dns: self._on_resolve_dns(ss),
                )
                if self._on_resolve_dns_with_server:
                    tools_menu.add_command(
                        label=f"DNS/IP für Auswahl auflösen… (DNS-Auswahl) ({len(selected_dns)})",
                        command=lambda ss=selected_dns: self._on_resolve_dns_with_server(ss),
                    )
        if session.source in ("ssh_config", "ssh_alias"):
            if self._on_inspect_ssh_config:
                tools_menu.add_command(
                    label="Konfiguration anzeigen (ssh -G)…",
                    command=lambda s=session: self._on_inspect_ssh_config(s),
                )
            if self._on_open_ssh_config_in_vscode:
                tools_menu.add_command(
                    label="SSH Config in VS Code öffnen",
                    command=self._on_open_ssh_config_in_vscode,
                )

        # Prüfen.
        if session.hostname:
            tools_menu.add_command(
                label="Host prüfen",
                command=lambda iid=item_id, s=session: self.check_hosts([(iid, s)]),
            )
        if selected_count >= 2:
            selected_pairs = [
                (iid, s) for iid, s in self._item_to_session.items()
                if self._checked.get(iid) and s.hostname
            ]
            if selected_pairs:
                tools_menu.add_command(
                    label=f"Auswahl-Hosts prüfen ({len(selected_pairs)})",
                    command=lambda p=selected_pairs: self.check_hosts(p),
                )

        # SSH-Key-Verwaltung.
        if self._on_deploy_ssh_key or self._on_remove_ssh_key:
            if self._on_deploy_ssh_key:
                security_menu.add_command(
                    label="SSH Key übertragen…",
                    command=lambda s=session: self._on_deploy_ssh_key([s]),
                )
                if selected_count >= 2:
                    security_menu.add_command(
                        label=f"SSH Key auf Auswahl übertragen… ({selected_count})",
                        command=lambda ss=list(selected): self._on_deploy_ssh_key(ss),
                    )
            if self._on_remove_ssh_key:
                security_menu.add_command(
                    label="SSH Key entfernen…",
                    command=lambda s=session: self._on_remove_ssh_key([s]),
                )
                if selected_count >= 2:
                    security_menu.add_command(
                        label=f"SSH Key aus Auswahl entfernen… ({selected_count})",
                        command=lambda ss=list(selected): self._on_remove_ssh_key(ss),
                    )

        # Farbe.
        color_menu = tk.Menu(appearance_menu, tearoff=False)
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
        appearance_menu.add_cascade(label="Farbe…", menu=color_menu)
        if selected_count >= 2:
            bulk_color_menu = tk.Menu(appearance_menu, tearoff=False)
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
            appearance_menu.add_cascade(label=f"Farbe für Auswahl ({selected_count})…", menu=bulk_color_menu)

        # Seltenere Funktionen bleiben schnell auffindbar, ohne die erste Ebene zu überladen.
        grouped_menus = (
            ("Favoriten", favorite_menu),
            ("Verwalten", manage_menu),
            ("Kopieren", copy_menu),
            ("Werkzeuge", tools_menu),
            ("SSH-Schlüssel", security_menu),
            ("Darstellung", appearance_menu),
        )
        menu.add_separator()
        for label, submenu in grouped_menus:
            try:
                has_items = submenu.index("end") is not None
            except AttributeError:
                has_items = bool(getattr(submenu, "commands", None) or getattr(submenu, "cascades", None))
            if has_items:
                menu.add_cascade(label=label, menu=submenu)

        # Destruktives unten.
        if (session.is_app_session or session.is_ssh_alias_copy) and self._on_delete_session:
            menu.add_separator()
            menu.add_command(
                label="Löschen",
                command=lambda s=session: self._on_delete_session(s),
            )

        menu.tk_popup(
            event.x_root if event is not None else int(x_root or 0),
            event.y_root if event is not None else int(y_root or 0),
        )

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
        Filtert sichtbare Sessions nach query (case-insensitive, Name + Hostname + Ordnerpfad).
        Bei leerem query werden alle Sessions wieder angezeigt.
        Checkbox-Zustände bleiben beim Filtern erhalten.
        Während einer aktiven Suche wird der Tree vollständig aufgeklappt;
        beim Leeren wird der Zustand von vor der Suche wiederhergestellt.
        """
        q = query.strip().lower()
        filters = self.__dict__.get("_structured_filters", {})
        active = bool(q or filters)
        self._active_filter_query = query

        # Checkbox-Zustände vor dem Neuaufbau sichern (item_id ändert sich)
        selected = {s.key: s for s in self.get_selected_sessions()}
        checked_keys = set(selected)

        # Zustand beim ersten Suchzeichen einmalig sichern
        if active and self._pre_search_open_folders is None:
            self._pre_search_open_folders = self.get_open_folders()

        if active:
            from .session_filters import matches_filters
            filtered = [
                s for s in self._sessions
                if matches_filters(s, filters) and (
                    q in s.display_name.lower()
                    or q in s.hostname.lower()
                    or q in "/".join(s.folder_path).lower()
                    or any(q in folder.lower() for folder in s.folder_path)
                )
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

        available = {s.key: s for s in self._sessions}
        visible_keys = {s.key for s in filtered}
        self._hidden_selected = {key: available[key] for key in selected if key in available and key not in visible_keys}
        self.populate(filtered, open_folders=open_folders, update_open_state=not active)

        # Checkbox-Zustände wiederherstellen
        for item_id, session in self._item_to_session.items():
            if session.key in checked_keys:
                self._checked[item_id] = True
                self._tv.item(item_id, image=self._img_checked)

        self._notify_count()

    def expand_all(self) -> None:
        """Klappt alle Ordner auf."""
        self._open_folders = set(self._item_to_folder_key.values())
        self._suppress_open_state_events += 1
        try:
            for item_id in self._item_to_folder_key:
                try:
                    self._tv.item(item_id, open=True)
                except tk.TclError:
                    pass
        finally:
            self._suppress_open_state_events -= 1
        self._notify_ui_state_changed()

    def collapse_all(self) -> None:
        """Klappt alle Ordner zu."""
        self._open_folders.clear()
        self._suppress_open_state_events += 1
        try:
            for item_id in self._item_to_folder_key:
                try:
                    self._tv.item(item_id, open=False)
                except tk.TclError:
                    pass
        finally:
            self._suppress_open_state_events -= 1
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
        if self._active_filter_query.strip() or self.__dict__.get("_structured_filters"):
            self.filter(self._active_filter_query)
            return
        self.populate(sessions, open_folders=open_folders)
        self._apply_column_visibility()
        for item_id, session in self._item_to_session.items():
            if session.key in checked_keys:
                self._checked[item_id] = True
                self._tv.item(item_id, image=self._img_checked)
        self._notify_count()

    def _session_label(self, session: Session, status: str | None) -> str:
        """Baut den Anzeigetext einer Session-Zeile inkl. Status-Symbol."""
        symbol = {"ok": "✓", "fail": "✗", "checking": "…"}.get(status or "", " ")
        if session.is_ssh_config_session:
            type_icon = "⚙ "
        elif session.is_app_session:
            type_icon = "★ "
        else:
            type_icon = ""
        prefix = f"  {symbol} "
        return f"{prefix}{type_icon}{session.display_name}"

    def _set_item_status(self, item_id: str, status: str | None) -> None:
        """Setzt den Status einer Session-Zeile und aktualisiert den Label-Text."""
        self._item_to_status[item_id] = status
        session = self._item_to_session.get(item_id)
        if session:
            self._tv.item(item_id, text=self._session_label(session, status))

    def check_hosts(self, item_session_pairs: list[tuple[str, Session]], timeout: int = 3) -> None:
        """Bounded probes; only this thread accesses widgets or tree mappings."""
        if not hasattr(self, "_host_pending"):
            self._host_executor = _create_host_probe_pool()
            self._host_check_timer = None
            self.bind("<Destroy>", lambda event: self._close_host_checks(event), add="+")
            self._host_pending = set()
            self._host_results = queue.SimpleQueue()
            self._host_pumping = False
        generation = getattr(self, "_populate_generation", 0)

        def completed(future, item_id, session):
            try:
                ok = future.result()
            except Exception as error:
                from .errors import record_failure
                record_failure(error)
                ok = False
            self._host_results.put((generation, item_id, session, ok))

        for item_id, session in item_session_pairs:
            if not session.hostname or session.key in self._host_pending:
                continue
            self._host_pending.add(session.key)
            self._set_item_status(item_id, "checking")
            try:
                future = self._host_executor.submit(check_host_reachable, session.hostname, session.port, timeout=timeout)
                future.add_done_callback(lambda result, iid=item_id, value=session: completed(result, iid, value))
            except RuntimeError:
                self._host_results.put((generation, item_id, session, False))
        if self._host_pending and not self._host_pumping:
            self._host_pumping = True
            self._host_check_timer = self.after(50, self._pump_host_checks)

    def _close_host_checks(self, event) -> None:
        if event.widget is self:
            self._host_executor.shutdown(wait=False, cancel_futures=True)
            if self._host_check_timer is not None:
                self.after_cancel(self._host_check_timer)

    def _pump_host_checks(self) -> None:
        self._host_check_timer = None
        if not self.winfo_exists():
            return
        while True:
            try:
                generation, item_id, session, ok = self._host_results.get_nowait()
            except queue.Empty:
                break
            self._host_pending.discard(session.key)
            if generation == getattr(self, "_populate_generation", 0) and self._item_to_session.get(item_id) is session:
                self._set_item_status(item_id, "ok" if ok else "fail")
        if self._host_pending:
            self._host_check_timer = self.after(50, self._pump_host_checks)
        else:
            self._host_pumping = False

    def check_selected_hosts(self, timeout: int = 3) -> None:
        pairs = [(iid, session) for iid, session in self._item_to_session.items()
                 if self._checked.get(iid) and session.hostname]
        if pairs:
            self.check_hosts(pairs, timeout=timeout)

    def check_folder_hosts(self, folder_item_id: str) -> None:
        pairs = [(iid, session) for iid, session in self._item_to_session.items()
                 if session.hostname and self._is_in_folder(iid, folder_item_id)]
        if pairs:
            self.check_hosts(pairs)

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
