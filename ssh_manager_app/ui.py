from __future__ import annotations

import tkinter as tk
from tkinter import ttk

try:
    from ttkbootstrap import Style as BootstrapStyle
    from ttkbootstrap import apply_bootstyle, apply_icon
except ModuleNotFoundError:
    BootstrapStyle = None
    apply_bootstyle = None
    apply_icon = None

from .dialogs_settings_misc import SettingsView
from .core import _create_checkbox_images
from .shortcuts import ShortcutAction, ShortcutManager
from .themes import ThemePalette, bootstrap_theme_for, palette_for_theme
from .tree import SessionTree
from .version import APP_NAME, APP_VERSION


TOOLBAR_BUTTON_ORDER = [
    "show_select_all",
    "show_deselect_all",
    "show_expand_all",
    "show_collapse_all",
    "show_add_connection",
    "show_reload",
    "show_open_tunnel",
    "show_check_hosts",
    "show_restart_servers",
]

# Keep a small, non-collapsing gap between menu labels and ttk's arrow indicator.
_MENU_ARROW_GAP = "\N{NO-BREAK SPACE}"


def toolbar_direct_capacity(width: int) -> int:
    """Keep the command strip compact and move the rest into overflow."""
    if width < 700:
        return 2
    if width < 900:
        return 4
    if width < 1120:
        return 6
    return len(TOOLBAR_BUTTON_ORDER)


def layout_toolbar_buttons(app) -> None:
    enabled = [
        key for key in TOOLBAR_BUTTON_ORDER
        if key != "show_add_connection" and getattr(app.settings.toolbar, key)
    ]
    try:
        width = int(app.__dict__["_main_frame"].winfo_width())
    except (AttributeError, TypeError, ValueError):
        width = 900
    except KeyError:
        width = 900
    capacity = toolbar_direct_capacity(width)
    direct = enabled[:capacity]
    overflow = enabled[capacity:]

    for button in app._toolbar_buttons.values():
        button.grid_forget()
    add_button = app._toolbar_buttons.get("show_add_connection")
    if add_button is not None and app.settings.toolbar.show_add_connection:
        add_button.grid(row=0, column=1, padx=(8, 0))
    for column, key in enumerate(direct):
        app._toolbar_buttons[key].grid(row=0, column=column, padx=(0, 6))

    overflow_button = app.__dict__.get("_toolbar_overflow_btn")
    overflow_menu = app.__dict__.get("_toolbar_overflow_menu")
    if overflow_button is None or overflow_menu is None:
        return
    overflow_button.grid_forget()
    overflow_menu.delete(0, "end")
    for key in overflow:
        label, command = app._toolbar_specs[key]
        overflow_menu.add_command(label=label, command=command)
    if overflow:
        overflow_button.grid(row=0, column=len(direct), padx=(0, 6))


def _decorate(widget: tk.Misc, *, icon: str | None = None, bootstyle: str | None = None) -> None:
    """Apply optional ttkbootstrap semantics to an existing tkinter widget."""
    try:
        if bootstyle and apply_bootstyle is not None:
            apply_bootstyle(widget, bootstyle)
        if icon and apply_icon is not None:
            apply_icon(widget, icon, size=14)
    except (KeyError, TypeError, tk.TclError):
        pass


def _on_main_frame_resized(app, event) -> None:
    capacity = toolbar_direct_capacity(event.width)
    if getattr(app, "_toolbar_capacity", None) != capacity:
        app._toolbar_capacity = capacity
        layout_toolbar_buttons(app)
    compact = event.width < 720
    if getattr(app, "_command_bar_compact", None) == compact:
        return
    app._command_bar_compact = compact
    buttons = getattr(app, "_command_group_buttons", ())
    for button in buttons:
        button.grid_forget()
    if compact:
        for column, button in enumerate(buttons, start=1):
            button.grid(row=1, column=column, sticky="w", padx=(0, 6), pady=(8, 0))
    else:
        for column, button in enumerate(buttons, start=3):
            button.grid(row=0, column=column, padx=(0, 6) if column < 5 else 0)


def persist_ui_state_callback(app) -> None:
    from .actions_ui import persist_ui_state

    persist_ui_state(app)


def connect_sessions_callback(app, sessions) -> None:
    from .actions_remote import connect_sessions

    connect_sessions(app, sessions)


def connect_selected_sessions_callback(app) -> None:
    connect_sessions_callback(app, app._tree.get_selected_sessions())


def connect_selected_or_focused_callback(app) -> None:
    from .actions_ui import connect_selected_or_focused

    connect_selected_or_focused(app)


def focus_search_callback(app) -> None:
    from .actions_ui import focus_search

    focus_search(app)


def delete_focused_editable_session_callback(app) -> None:
    from .actions_ui import delete_focused_editable_session

    delete_focused_editable_session(app)


def quick_connect_session_callback(app, session) -> None:
    from .actions_remote import quick_connect_session

    quick_connect_session(app, session)


def add_favorite_session_callback(app, session, include_original_tree: bool) -> None:
    from .actions_ui import set_favorite_session

    set_favorite_session(app, session, include_original_tree=include_original_tree)


def add_favorite_sessions_callback(app, sessions, include_original_tree: bool) -> None:
    from .actions_ui import set_favorite_sessions

    set_favorite_sessions(app, sessions, include_original_tree=include_original_tree)


def remove_favorite_session_callback(app, session) -> None:
    from .actions_ui import remove_favorite_session

    remove_favorite_session(app, session)


def reload_sessions_callback(app) -> None:
    from .actions_ui import reload_sessions

    reload_sessions(app)


def edit_session_note_callback(app, session) -> None:
    from .actions_notes import edit_session_note

    edit_session_note(app, session)


def export_settings_dialog_callback(app) -> None:
    from .actions_app import export_settings_dialog

    export_settings_dialog(app)


def import_settings_dialog_callback(app) -> None:
    from .actions_app import import_settings_dialog

    import_settings_dialog(app)


def show_settings_view_callback(app) -> None:
    from .actions_ui import show_settings_view

    show_settings_view(app)


def show_main_view_callback(app) -> None:
    from .actions_ui import show_main_view

    show_main_view(app)


def edit_session_callback(app, session) -> None:
    from .actions_sessions import edit_session, edit_session_details

    if session.source in ("app", "ssh_alias"):
        edit_session(app, session)
    else:
        edit_session_details(app, session)


def set_sessions_username_callback(app, sessions) -> None:
    from .actions_sessions import set_sessions_username

    set_sessions_username(app, sessions)


def clear_sessions_username_callback(app, sessions) -> None:
    from .actions_sessions import clear_sessions_username

    clear_sessions_username(app, sessions)


def delete_session_callback(app, session) -> None:
    from .actions_sessions import delete_session

    delete_session(app, session)


def delete_folder_callback(app, sessions, folder_key) -> None:
    from .actions_sessions import delete_folder

    delete_folder(app, sessions, folder_key)


def rename_folder_callback(app, folder_key) -> None:
    from .actions_sessions import rename_folder

    rename_folder(app, folder_key)


def duplicate_ssh_alias_callback(app, session) -> None:
    from .actions_sessions import duplicate_ssh_alias

    duplicate_ssh_alias(app, session)


def inspect_ssh_config_callback(app, session) -> None:
    from .actions_open import inspect_ssh_config

    inspect_ssh_config(app, session)


def duplicate_app_session_callback(app, session) -> None:
    from .actions_sessions import duplicate_app_session

    duplicate_app_session(app, session)


def move_session_callback(app, session) -> None:
    from .actions_sessions import move_session

    move_session(app, session)


def move_sessions_callback(app, sessions) -> None:
    from .actions_sessions import move_sessions

    move_sessions(app, sessions)


def open_ssh_config_in_vscode_callback(app) -> None:
    from .actions_open import open_ssh_config_in_vscode

    open_ssh_config_in_vscode(app)


def open_in_winscp_callback(app, sessions) -> None:
    from .actions_open import open_in_winscp

    open_in_winscp(app, sessions)


def deploy_ssh_key_callback(app, sessions) -> None:
    from .actions_remote import deploy_ssh_key

    deploy_ssh_key(app, sessions)


def remove_ssh_key_callback(app, sessions) -> None:
    from .actions_remote import remove_ssh_key

    remove_ssh_key(app, sessions)


def open_tunnel_callback(app, session=None) -> None:
    from .actions_remote import open_tunnel

    open_tunnel(app, session=session)


def run_remote_command_callback(app, sessions) -> None:
    from .actions_remote import run_remote_command

    run_remote_command(app, sessions)


def restart_servers_callback(app, sessions) -> None:
    from .actions_restart import restart_servers

    restart_servers(app, sessions)


def deploy_certificate_files_callback(app, sessions) -> None:
    from .actions_certificates import deploy_certificate_files

    deploy_certificate_files(app, sessions)


def replace_certificates_callback(app, sessions) -> None:
    from .actions_certificate_replace import replace_certificates

    replace_certificates(app, sessions)


def open_dns_lookup_dialog_callback(app) -> None:
    from .actions_dns import open_dns_lookup_dialog

    open_dns_lookup_dialog(app)


def resolve_dns_for_sessions_callback(app, sessions) -> None:
    from .actions_dns import resolve_dns_for_sessions

    resolve_dns_for_sessions(app, sessions)


def resolve_dns_for_sessions_with_server_callback(app, sessions) -> None:
    from .actions_dns import resolve_dns_for_sessions_with_server_selection

    resolve_dns_for_sessions_with_server_selection(app, sessions)


def open_via_jumphost_callback(app, session) -> None:
    from .actions_remote import open_via_jumphost

    open_via_jumphost(app, session)


def copy_ssh_command_callback(app, sessions) -> None:
    from .actions_remote import copy_ssh_commands

    if not isinstance(sessions, list):
        sessions = [sessions]
    copy_ssh_commands(app, sessions)


def copy_visible_sessions_as_markdown_callback(app) -> None:
    from .actions_app import copy_visible_sessions_as_markdown

    copy_visible_sessions_as_markdown(app)


def export_visible_sessions_callback(app, export_format: str) -> None:
    from .actions_app import export_visible_sessions

    export_visible_sessions(app, export_format)


def add_session_callback(app, folder_preset="") -> None:
    from .actions_sessions import add_session

    add_session(app, folder_preset=folder_preset)


def open_appdata_jsons_in_vscode_callback(app) -> None:
    from .actions_sessions import open_appdata_jsons_in_vscode

    open_appdata_jsons_in_vscode(app)


def close_app_callback(app) -> None:
    from .actions_app import close_app

    close_app(app)


def show_search_history_menu_callback(app) -> None:
    from .actions_app import show_search_history_menu

    show_search_history_menu(app)


def on_search_changed_callback(app) -> None:
    from .actions_ui import on_search_changed

    on_search_changed(app)


def preview_toolbar_visibility_callback(app, toolbar_settings) -> None:
    from .actions_ui import preview_toolbar_visibility

    preview_toolbar_visibility(app, toolbar_settings)


def hide_column_from_header_callback(app, column_key: str) -> None:
    from .actions_ui import hide_column_from_header

    hide_column_from_header(app, column_key)


def preview_source_visibility_callback(app, source_visibility) -> None:
    from .actions_ui import preview_source_visibility

    preview_source_visibility(app, source_visibility)


def reset_settings_callback(app) -> None:
    from .actions_ui import reset_settings

    reset_settings(app)


def reset_session_colors_callback(app) -> None:
    from .actions_ui import reset_session_colors

    reset_session_colors(app)


def reset_view_state_callback(app) -> None:
    from .actions_ui import reset_view_state

    reset_view_state(app)


def invert_selection_callback(app) -> None:
    from .actions_ui import invert_selection

    invert_selection(app)


def on_selection_changed_callback(app, count: int) -> None:
    from .actions_ui import on_selection_changed

    on_selection_changed(app, count)


def select_all_callback(app) -> None:
    from .actions_ui import select_all

    select_all(app)


def deselect_all_callback(app) -> None:
    from .actions_ui import deselect_all

    deselect_all(app)


def open_command_palette_callback(app) -> None:
    from .actions_app import open_command_palette

    open_command_palette(app)


def expand_all_callback(app) -> None:
    from .actions_ui import expand_all

    expand_all(app)


def collapse_all_callback(app) -> None:
    from .actions_ui import collapse_all

    collapse_all(app)


def _apply_palette_styles(app: tk.Tk, palette: ThemePalette) -> None:
    style = ttk.Style(app)
    appearance = getattr(getattr(app, "settings", None), "appearance", None)
    accent = getattr(appearance, "accent_color", "#2563eb")
    bg = palette.bg
    surface = palette.surface
    surface_alt = palette.surface_alt
    nav = palette.nav
    border = palette.border
    text = palette.text
    muted = palette.muted
    selected = palette.selected
    button_active = palette.button_active
    dark_mode = int(bg[1:3], 16) < 80
    warning_text = "#fbbf24" if dark_mode else "#9a5b00"
    danger_text = "#fca5a5" if dark_mode else "#b42318"
    danger_border = "#7f1d1d" if dark_mode else "#e5a9a4"
    danger_active = "#4a2525" if dark_mode else "#fff1f0"
    danger_pressed = "#5c2020" if dark_mode else "#fee4e2"

    app.configure(background=bg)
    app.option_add("*Menu.background", surface)
    app.option_add("*Menu.foreground", text)
    app.option_add("*Menu.activeBackground", selected)
    app.option_add("*Menu.activeForeground", text)
    app.option_add("*Listbox.background", surface)
    app.option_add("*Listbox.foreground", text)
    app.option_add("*Listbox.selectBackground", accent)
    app.option_add("*Listbox.selectForeground", "#ffffff")
    app.option_add("*Listbox.highlightColor", accent)
    app.option_add("*Listbox.highlightBackground", border)
    ui_font = (getattr(appearance, "ui_font_family", "Segoe UI"), getattr(appearance, "ui_font_size", 10))
    tree_font = (getattr(appearance, "tree_font_family", "Segoe UI"), getattr(appearance, "tree_font_size", 10))
    tree_row_height = getattr(appearance, "tree_row_height", 28)
    style.configure(".", background=bg, foreground=text, font=ui_font)
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=text)
    style.configure("Header.TFrame", background=surface)
    style.configure("HeaderBrand.TFrame", background=surface)
    style.configure("HeaderMark.TLabel", background=accent, foreground="#ffffff", font=("Cascadia Mono", ui_font[1] + 4, "bold"), padding=(9, 6))
    style.configure("HeaderTitle.TLabel", background=surface, foreground=text, font=(ui_font[0], ui_font[1] + 7, "bold"))
    style.configure("HeaderVersion.TLabel", background=surface_alt, foreground=muted, font=(ui_font[0], max(8, ui_font[1] - 1), "bold"), padding=(7, 3))
    style.configure("HeaderSubtitle.TLabel", background=surface, foreground=muted)
    style.configure("CommandBar.TFrame", background=surface_alt)
    style.configure("CommandBar.TLabel", background=surface_alt, foreground=muted)
    style.configure("SearchBar.TFrame", background=surface, bordercolor=border, lightcolor=border, darkcolor=border, relief="solid")
    style.configure("SearchIcon.TLabel", background=surface, foreground=muted, font=(ui_font[0], ui_font[1] + 2))
    style.configure("SearchEntry.TEntry", fieldbackground=surface, foreground=text, borderwidth=0, relief="flat", insertcolor=text)
    style.configure("QuickBar.TFrame", background=bg)
    style.configure("Quick.TButton", padding=(9, 6), background=surface, foreground=text, bordercolor=border)
    style.map("Quick.TButton", background=[("active", button_active), ("pressed", selected)], bordercolor=[("focus", accent), ("active", accent)])
    style.configure("TreeSurface.TFrame", background=surface)
    style.configure("StatusBar.TFrame", background=surface_alt)
    style.configure("StatusBar.TLabel", background=surface_alt, foreground=muted)
    style.configure("Muted.TLabel", foreground=muted)
    style.configure("DialogTitle.TLabel", foreground=text, font=(ui_font[0], ui_font[1] + 3, "bold"))
    style.configure("Warning.TLabel", background=bg, foreground=warning_text)
    style.configure("Error.TLabel", background=bg, foreground=danger_text)
    style.configure("DialogPanel.TLabelframe", background=surface, bordercolor=border, lightcolor=border, darkcolor=border, relief="solid")
    style.configure("DialogPanel.TLabelframe.Label", background=surface, foreground=text, font=(ui_font[0], ui_font[1], "bold"))
    style.configure("DialogPanel.TFrame", background=surface)
    style.configure("DialogPanel.TLabel", background=surface, foreground=text)
    style.configure("DialogPanelMuted.TLabel", background=surface, foreground=muted)
    style.configure("DialogPanel.TCheckbutton", background=surface, foreground=text)
    style.map("DialogPanel.TCheckbutton", background=[("active", surface)], foreground=[("disabled", muted)])
    style.configure("DialogPanel.TRadiobutton", background=surface, foreground=text)
    style.map("DialogPanel.TRadiobutton", background=[("active", surface)], foreground=[("disabled", muted)])
    style.configure("TButton", padding=(12, 7), background=surface, foreground=text, bordercolor=border, focusthickness=1, focuscolor=accent)
    style.map("TButton", background=[("active", button_active), ("pressed", selected)], foreground=[("active", text)], bordercolor=[("focus", accent), ("active", accent)])
    style.configure("SearchHistory.TButton", padding=(4, 1), background=surface, foreground=text, bordercolor=border, focusthickness=1, focuscolor=accent)
    style.map("SearchHistory.TButton", background=[("active", button_active), ("pressed", selected)], foreground=[("active", text)], bordercolor=[("focus", accent), ("active", accent)])
    style.configure("TEntry", fieldbackground=surface, foreground=text, bordercolor=border, lightcolor=border, darkcolor=border, insertcolor=text)
    style.map("TEntry", fieldbackground=[("disabled", surface_alt)], foreground=[("disabled", muted)])
    style.configure("TSpinbox", fieldbackground=surface, foreground=text, bordercolor=border, lightcolor=border, darkcolor=border, insertcolor=text, arrowcolor=muted, arrowsize=13)
    style.map("TSpinbox", fieldbackground=[("disabled", surface_alt), ("readonly", surface)], foreground=[("disabled", muted)], arrowcolor=[("active", accent)])
    style.configure("TCombobox", fieldbackground=surface, background=surface, foreground=text, bordercolor=border, lightcolor=border, darkcolor=border, arrowcolor=muted, selectbackground=surface, selectforeground=text)
    style.map("TCombobox", fieldbackground=[("readonly", surface), ("disabled", surface_alt)], foreground=[("readonly", text), ("disabled", muted)], selectbackground=[("readonly", surface)], selectforeground=[("readonly", text)], arrowcolor=[("active", accent), ("disabled", muted)])
    style.configure("TCheckbutton", background=bg, foreground=text)
    style.configure("TLabelframe", background=surface, bordercolor=border, lightcolor=border, darkcolor=border, relief="solid")
    style.configure("TLabelframe.Label", background=surface, foreground=text, font=(ui_font[0], ui_font[1], "bold"))
    style.configure("TMenubutton", padding=(10, 7), background=surface, foreground=text, bordercolor=border)
    style.map("TMenubutton", background=[("active", button_active), ("pressed", selected)], bordercolor=[("focus", accent), ("active", accent)])
    style.configure("Treeview", background=surface, fieldbackground=surface, foreground=text, rowheight=tree_row_height, font=tree_font, bordercolor=border, lightcolor=border, darkcolor=border)
    style.configure("Treeview.Heading", background=surface_alt, foreground=text, relief="flat", bordercolor=border, padding=(8, 7), font=(tree_font[0], tree_font[1], "bold"))
    style.map("Treeview", background=[("selected", selected)], foreground=[("selected", text)])
    style.configure("Vertical.TScrollbar", background=surface_alt, troughcolor=bg, bordercolor=border, arrowcolor=muted)
    style.configure("Horizontal.TScrollbar", background=surface_alt, troughcolor=bg, bordercolor=border, arrowcolor=muted)
    style.configure("Toast.TFrame", background=palette.toast_bg, relief="flat")
    style.configure("Toast.TLabel", background=palette.toast_bg, foreground=palette.toast_text)
    style.configure("SettingsRoot.TFrame", background=bg)
    style.configure("SettingsNav.TFrame", background=nav)
    style.configure("SettingsContent.TFrame", background=bg)
    style.configure("SettingsPanel.TFrame", background=surface)
    style.configure("SettingsActions.TFrame", background=bg)
    style.configure("SettingsTitle.TLabel", background=bg, foreground=text, font=(ui_font[0], ui_font[1] + 8, "bold"))
    style.configure("SettingsSubtitle.TLabel", background=bg, foreground=muted)
    style.configure("SettingsNavTitle.TLabel", background=nav, foreground=text, font=(ui_font[0], ui_font[1], "bold"))
    style.configure("SettingsSectionTitle.TLabel", background=surface, foreground=text, font=(ui_font[0], ui_font[1] + 3, "bold"))
    style.configure("SettingsHint.TLabel", background=surface, foreground=muted)
    style.configure("SettingsValue.TLabel", background=surface, foreground=text)
    style.configure("SettingsNav.TButton", padding=(14, 10), anchor="w", background=nav, foreground=text, bordercolor=nav)
    style.map("SettingsNav.TButton", background=[("active", selected), ("pressed", selected)], foreground=[("active", text)])
    style.configure("EmptyState.TFrame", background=surface)
    style.configure("EmptyStateContent.TFrame", background=surface)
    style.configure("EmptyStateCard.TFrame", background=surface, relief="flat")
    style.configure("EmptyStateIcon.TLabel", background=surface, foreground=accent, font=("Cascadia Mono", ui_font[1] + 18, "bold"), anchor="center")
    style.configure("EmptyStateTitle.TLabel", background=surface, foreground=text, font=(ui_font[0], ui_font[1] + 6, "bold"), anchor="center")
    style.configure("EmptyStateHint.TLabel", background=surface, foreground=muted, font=(ui_font[0], ui_font[1] + 1), anchor="center")
    style.configure("Accent.TButton", padding=(14, 8), background=accent, foreground="#ffffff", bordercolor=accent)
    style.map("Accent.TButton", background=[("active", accent), ("pressed", accent)], foreground=[("active", "#ffffff"), ("disabled", "#d9e4f4")])
    style.configure("Danger.TButton", padding=(12, 7), foreground=danger_text, background=surface, bordercolor=danger_border)
    style.map("Danger.TButton", background=[("active", danger_active), ("pressed", danger_pressed)])
    _configure_classic_widgets(app, background=surface, foreground=text, accent=accent, border=border)
    _configure_combobox_popdowns(app, background=surface, foreground=text, accent=accent)
    app.update_idletasks()


def _safe_widget_configure(widget: tk.Misc, **options) -> None:
    """Set widget options defensively because Tk/ttk support differs by platform/theme."""
    for key, value in options.items():
        try:
            widget.configure(**{key: value})
        except tk.TclError:
            pass


def _configure_classic_widgets(widget: tk.Misc, *, background: str, foreground: str, accent: str, border: str) -> None:
    """Apply runtime colors to classic Tk widgets that ttk styles do not cover."""
    for child in widget.children.values():
        if isinstance(child, (tk.Entry, tk.Spinbox, tk.Text)):
            _safe_widget_configure(
                child,
                background=background,
                foreground=foreground,
                insertbackground=foreground,
                disabledbackground=background,
                disabledforeground=foreground,
                readonlybackground=background,
                highlightcolor=accent,
                highlightbackground=border,
            )
        if isinstance(child, tk.Listbox):
            _safe_widget_configure(
                child,
                background=background,
                foreground=foreground,
                selectbackground=accent,
                selectforeground="#ffffff",
                highlightcolor=accent,
                highlightbackground=border,
            )
        _configure_classic_widgets(child, background=background, foreground=foreground, accent=accent, border=border)


def _configure_combobox_popdowns(widget: tk.Misc, *, background: str, foreground: str, accent: str) -> None:
    for child in widget.children.values():
        if isinstance(child, ttk.Combobox):
            _install_combobox_popdown_style(child, background=background, foreground=foreground, accent=accent)
        _configure_combobox_popdowns(child, background=background, foreground=foreground, accent=accent)


def _style_dialog_actions(widget: tk.Misc) -> None:
    """Give dialog actions a consistent primary/destructive hierarchy."""
    primary_labels = (
        "ok", "speichern", "verbinden", "ausführen", "starten", "übernehmen",
        "hinzufügen", "exportieren", "importieren", "hochladen", "server neu starten",
    )
    danger_labels = ("löschen", "entfernen", "zertifikate ersetzen")
    for child in widget.children.values():
        if isinstance(child, ttk.Button):
            label = str(child.cget("text")).strip().lower()
            if any(label.startswith(prefix) for prefix in danger_labels):
                child.configure(style="Danger.TButton")
            elif any(label.startswith(prefix) for prefix in primary_labels):
                child.configure(style="Accent.TButton")
        _style_dialog_actions(child)


def _style_dialog_surfaces(widget: tk.Misc, *, inside_panel: bool = False) -> None:
    """Keep default ttk controls visually attached to their dialog panel.

    ttk does not inherit a parent's background.  Without panel-specific styles,
    labels and check/radio controls therefore show the window background as
    rectangular patches on top of a themed ``LabelFrame``.
    """
    for child in widget.children.values():
        child_inside_panel = inside_panel or isinstance(child, ttk.LabelFrame)
        try:
            current_style = str(child.cget("style"))
        except tk.TclError:
            current_style = ""

        if isinstance(child, ttk.LabelFrame) and current_style in {"", "TLabelframe"}:
            child.configure(style="DialogPanel.TLabelframe")
        elif child_inside_panel:
            if isinstance(child, ttk.Label) and current_style in {"", "TLabel"}:
                child.configure(style="DialogPanel.TLabel")
            elif isinstance(child, ttk.Label) and current_style == "Muted.TLabel":
                child.configure(style="DialogPanelMuted.TLabel")
            elif isinstance(child, ttk.Frame) and current_style in {"", "TFrame"}:
                child.configure(style="DialogPanel.TFrame")
            elif isinstance(child, ttk.Checkbutton) and current_style in {"", "TCheckbutton"}:
                child.configure(style="DialogPanel.TCheckbutton")
            elif isinstance(child, ttk.Radiobutton) and current_style in {"", "TRadiobutton"}:
                child.configure(style="DialogPanel.TRadiobutton")

        _style_dialog_surfaces(child, inside_panel=child_inside_panel)


def _install_combobox_popdown_style(combobox: ttk.Combobox, *, background: str, foreground: str, accent: str) -> None:
    def apply_popdown_style() -> None:
        try:
            popdown = combobox.tk.call("ttk::combobox::PopdownWindow", combobox)
            listbox = f"{popdown}.f.l"
            combobox.tk.call(listbox, "configure", "-background", background)
            combobox.tk.call(listbox, "configure", "-foreground", foreground)
            combobox.tk.call(listbox, "configure", "-selectbackground", accent)
            combobox.tk.call(listbox, "configure", "-selectforeground", "#ffffff")
        except tk.TclError:
            pass

    combobox.configure(postcommand=apply_popdown_style)


def _install_toplevel_theme_hook(app: tk.Tk) -> None:
    """Apply the active palette to classic Tk controls created in dialogs."""
    if getattr(app, "_theme_toplevel_hook_installed", False):
        return
    app._theme_toplevel_hook_installed = True

    def restyle_dialog(event) -> None:
        dialog = event.widget
        appearance = getattr(getattr(app, "settings", None), "appearance", None)
        theme = getattr(appearance, "theme", "default")
        accent = getattr(appearance, "accent_color", "#2563eb")
        palette = palette_for_theme(theme)
        _safe_widget_configure(dialog, background=palette.bg)
        try:
            dialog.after_idle(
                lambda: (
                    _style_dialog_surfaces(dialog),
                    _configure_classic_widgets(
                        dialog,
                        background=palette.surface,
                        foreground=palette.text,
                        accent=accent,
                        border=palette.border,
                    ),
                    _style_dialog_actions(dialog),
                )
            )
        except tk.TclError:
            pass

    app.bind_class("Toplevel", "<Map>", restyle_dialog, add="+")


def configure_app_styles(app: tk.Tk) -> None:
    appearance = getattr(getattr(app, "settings", None), "appearance", None)
    theme = getattr(appearance, "theme", "default")
    foundation = bootstrap_theme_for(theme)
    if BootstrapStyle is not None:
        style = BootstrapStyle(theme=foundation, default_button="neutral")
        style.theme_use(foundation)
    else:
        style = ttk.Style(app)
        available = style.theme_names()
        fallback = "vista" if "vista" in available else "clam"
        if fallback in available:
            style.theme_use(fallback)
    app._bootstrap_style = style
    _apply_palette_styles(app, palette_for_theme(theme))
    _install_toplevel_theme_hook(app)

def refresh_checkbox_images(app) -> None:
    """Rebuild tree checkbox icons from the active theme palette."""
    appearance = getattr(getattr(app, "settings", None), "appearance", None)
    theme = getattr(appearance, "theme", "default")
    accent = getattr(appearance, "accent_color", "#1a7a3a")
    palette = palette_for_theme(theme)
    background = palette.surface
    border = palette.border
    if not isinstance(app, tk.Misc):
        return
    app._img_unchecked, app._img_checked = _create_checkbox_images(app, background=background, border=border, check=accent)
    tree = getattr(app, "_tree", None)
    if tree is not None:
        tree.set_checkbox_images(app._img_unchecked, app._img_checked)


def install_shortcut_manager(app) -> None:
    """Build the ``ShortcutManager`` for ``app`` and apply persisted bindings."""
    from .actions_ui import (
        collapse_all,
        connect_selected_or_focused,
        connect_selected_sessions,
        delete_focused_editable_session,
        deselect_all,
        focus_search,
        invert_selection,
        reload_sessions,
        select_all,
        show_settings_view,
        toggle_recent_folder,
    )
    from .actions_sessions import add_session
    from .actions_app import export_settings_dialog, import_settings_dialog

    manager = ShortcutManager(app)

    def tree_has_focus() -> bool:
        return app._tree.has_keyboard_focus()

    def open_command_palette() -> None:
        from .actions_ui import open_command_palette as _open
        _open(app)

    def edit_focused() -> None:
        from .actions_ui import edit_focused_session
        edit_focused_session(app)

    actions = [
        # Let text widgets keep their normal Ctrl+P / typing behavior.
        ShortcutAction("open_command_palette", "Befehlspalette öffnen", "Ctrl+P", open_command_palette, skip_in_entry=True),
        ShortcutAction("focus_search", "Suche fokussieren", "Ctrl+F", lambda: focus_search(app), skip_in_entry=False),
        ShortcutAction("new_session", "Neue Verbindung", "Ctrl+N", lambda: add_session(app), skip_in_entry=False),
        ShortcutAction("open_settings", "Einstellungen öffnen", "Ctrl+,", lambda: show_settings_view(app), skip_in_entry=False),
        ShortcutAction("refresh", "Neu laden", "F5", lambda: reload_sessions(app), skip_in_entry=False),
        ShortcutAction(
            "connect",
            "Verbinden",
            "Return",
            lambda: connect_selected_or_focused(app),
            skip_in_entry=True,
            enabled_when=tree_has_focus,
        ),
        ShortcutAction(
            "connect_selected",
            "Auswahl verbinden",
            "Ctrl+Enter",
            lambda: connect_selected_sessions(app),
            skip_in_entry=True,
            enabled_when=tree_has_focus,
        ),
        ShortcutAction("edit", "Bearbeiten", "F2", edit_focused, skip_in_entry=False),
        ShortcutAction("delete", "Löschen", "Delete", lambda: delete_focused_editable_session(app), skip_in_entry=True),
        ShortcutAction("select_all", "Alle auswählen", "Ctrl+A", lambda: select_all(app), skip_in_entry=True),
        ShortcutAction("deselect_all", "Alle abwählen", "Ctrl+D", lambda: deselect_all(app), skip_in_entry=True),
        ShortcutAction("invert_selection", "Auswahl umkehren", "Ctrl+I", lambda: invert_selection(app), skip_in_entry=True),
        ShortcutAction("toggle_recent_folder", "Ordner 'Zuletzt verwendet' umschalten", "Ctrl+Shift+R", lambda: toggle_recent_folder(app), skip_in_entry=False),
        ShortcutAction("import_settings", "Einstellungen importieren", "", lambda: import_settings_dialog(app), skip_in_entry=False),
        ShortcutAction("export_settings", "Einstellungen exportieren", "", lambda: export_settings_dialog(app), skip_in_entry=False),
    ]
    for action in actions:
        manager.register(action)
    app._shortcut_manager = manager
    manager.load_bindings(dict(getattr(app.settings, "keyboard_shortcuts", {})))


def reapply_shortcut_bindings(app) -> None:
    """Re-apply bindings after settings changed."""
    manager = getattr(app, "_shortcut_manager", None)
    if manager is None:
        return
    manager.apply_bindings(dict(getattr(app.settings, "keyboard_shortcuts", {})))


def build_main_ui(self) -> None:
    """Erstellt alle UI-Elemente."""
    self.columnconfigure(0, weight=1)
    self.rowconfigure(0, weight=1)

    install_shortcut_manager(self)

    menubar = tk.Menu(self)
    self.config(menu=menubar)

    def _acc(action_id: str) -> str:
        mgr = getattr(self, "_shortcut_manager", None)
        if mgr is None:
            return ""
        return mgr.current_mapping().get(action_id, "")

    file_menu = tk.Menu(menubar, tearoff=False)
    file_menu.add_command(label="Neue Verbindung", accelerator=_acc("new_session"), command=lambda: add_session_callback(self))
    file_menu.add_command(label="Neu laden", accelerator=_acc("refresh"), command=lambda: reload_sessions_callback(self))
    file_menu.add_command(label="Befehlspalette\u2026", accelerator=_acc("open_command_palette"), command=lambda: open_command_palette_callback(self))
    file_menu.add_separator()
    file_menu.add_command(label="Einstellungen", accelerator=_acc("open_settings"), command=lambda: show_settings_view_callback(self))
    file_menu.add_command(label="JSONs in VS Code öffnen", command=lambda: open_appdata_jsons_in_vscode_callback(self))
    file_menu.add_separator()
    file_menu.add_command(label="Beenden", command=lambda: close_app_callback(self))
    menubar.add_cascade(label="Datei", menu=file_menu)

    selection_menu = tk.Menu(menubar, tearoff=False)
    selection_menu.add_command(label="Alle auswählen", accelerator=_acc("select_all"), command=lambda: select_all_callback(self))
    selection_menu.add_command(label="Alle abwählen", accelerator=_acc("deselect_all"), command=lambda: deselect_all_callback(self))
    selection_menu.add_command(label="Auswahl umkehren", accelerator=_acc("invert_selection"), command=lambda: invert_selection_callback(self))
    menubar.add_cascade(label="Auswahl", menu=selection_menu)

    view_menu = tk.Menu(menubar, tearoff=False)
    view_menu.add_command(label="Ausklappen", command=lambda: expand_all_callback(self))
    view_menu.add_command(label="Einklappen", command=lambda: collapse_all_callback(self))
    view_menu.add_separator()
    view_menu.add_command(label="Farben zurücksetzen", command=lambda: reset_session_colors_callback(self))
    view_menu.add_command(label="Ansicht auf Startzustand zurücksetzen", command=lambda: reset_view_state_callback(self))
    menubar.add_cascade(label="Ansicht", menu=view_menu)

    actions_menu = tk.Menu(menubar, tearoff=False)
    actions_menu.add_command(label="Auswahl verbinden", accelerator=_acc("connect_selected"), command=lambda: connect_selected_sessions_callback(self))
    actions_menu.add_command(label="Hosts prüfen", command=lambda: self._tree.check_selected_hosts(timeout=self.settings.host_check_timeout_seconds))
    actions_menu.add_command(label="Server neu starten…", command=lambda: restart_servers_callback(self, self._tree.get_selected_sessions()))
    actions_menu.add_command(label="Tunnel öffnen", command=lambda: open_tunnel_callback(self))
    actions_menu.add_command(label="Remote-Befehl ausführen", command=lambda: run_remote_command_callback(self, self._tree.get_selected_sessions()))
    actions_menu.add_command(label="Dateien übertragen…", command=lambda: deploy_certificate_files_callback(self, self._tree.get_selected_sessions()))
    actions_menu.add_command(label="Zertifikate ersetzen…", command=lambda: replace_certificates_callback(self, self._tree.get_selected_sessions()))
    actions_menu.add_separator()
    actions_menu.add_command(label="DNS/IP auflösen…", command=lambda: open_dns_lookup_dialog_callback(self))
    actions_menu.add_command(label="DNS/IP für Auswahl auflösen…", command=lambda: resolve_dns_for_sessions_callback(self, self._tree.get_selected_sessions()))
    actions_menu.add_command(
        label="DNS/IP für Auswahl auflösen… (DNS-Auswahl)",
        command=lambda: resolve_dns_for_sessions_with_server_callback(self, self._tree.get_selected_sessions()),
    )
    actions_menu.add_separator()
    actions_menu.add_command(
        label="Angezeigte Verbindungen als Markdown kopieren",
        command=lambda: copy_visible_sessions_as_markdown_callback(self),
    )
    actions_menu.add_command(
        label="Angezeigte Verbindungen als CSV exportieren…",
        command=lambda: export_visible_sessions_callback(self, "csv"),
    )
    actions_menu.add_command(
        label="Angezeigte Verbindungen als Excel exportieren…",
        command=lambda: export_visible_sessions_callback(self, "xlsx"),
    )
    menubar.add_cascade(label="Aktionen", menu=actions_menu)

    settings_menu = tk.Menu(menubar, tearoff=False)
    settings_menu.add_command(label="Einstellungen öffnen", command=lambda: show_settings_view_callback(self))
    settings_menu.add_command(label="Einstellungen exportieren…", command=lambda: export_settings_dialog_callback(self))
    settings_menu.add_command(label="Einstellungen importieren…", command=lambda: import_settings_dialog_callback(self))
    settings_menu.add_separator()
    settings_menu.add_command(label="Einstellungen zurücksetzen", command=lambda: reset_settings_callback(self))
    menubar.add_cascade(label="Einstellungen", menu=settings_menu)

    self._main_frame = ttk.Frame(self)
    self._main_frame.grid(row=0, column=0, sticky="nsew")
    self._main_frame.columnconfigure(0, weight=1)
    self._main_frame.rowconfigure(3, weight=1)

    header = ttk.Frame(self._main_frame, style="Header.TFrame", padding=(18, 13))
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    brand_wrap = ttk.Frame(header, style="HeaderBrand.TFrame")
    brand_wrap.grid(row=0, column=0, sticky="w")
    ttk.Label(brand_wrap, text=">_", style="HeaderMark.TLabel").grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 12))
    title_wrap = ttk.Frame(brand_wrap, style="Header.TFrame")
    title_wrap.grid(row=0, column=1, rowspan=2, sticky="w")
    ttk.Label(title_wrap, text=APP_NAME, style="HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(title_wrap, text=f"v{APP_VERSION}", style="HeaderVersion.TLabel").grid(
        row=0,
        column=1,
        sticky="sw",
        padx=(8, 0),
        pady=(0, 2),
    )
    ttk.Label(
        title_wrap,
        text="Verbindungen zentral finden, verwalten und öffnen",
        style="HeaderSubtitle.TLabel",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(1, 0))

    self._toolbar_buttons["show_add_connection"] = ttk.Button(
        header,
        text="Neue Verbindung",
        command=lambda: add_session_callback(self),
    )
    _decorate(self._toolbar_buttons["show_add_connection"], icon="plus-lg")
    settings_button = ttk.Button(header, text="Einstellungen", command=lambda: show_settings_view_callback(self))
    settings_button.grid(row=0, column=2, padx=(8, 0))
    _decorate(settings_button, icon="gear")

    command_bar = ttk.Frame(self._main_frame, style="CommandBar.TFrame", padding=(18, 10))
    command_bar.grid(row=1, column=0, sticky="ew")
    command_bar.columnconfigure(0, weight=1)
    search_wrap = ttk.Frame(command_bar, style="SearchBar.TFrame", padding=(8, 3))
    search_wrap.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    search_wrap.columnconfigure(1, weight=1)
    ttk.Label(search_wrap, text="⌕", style="SearchIcon.TLabel").grid(row=0, column=0, padx=(2, 7))
    self._search_var = tk.StringVar(value=self._initial_toolbar_search_texts.get("main", ""))
    self._search_history = list(self._initial_toolbar_search_texts.get("search_history", []))
    self._search_entry = ttk.Entry(search_wrap, textvariable=self._search_var, style="SearchEntry.TEntry")
    self._search_entry.grid(row=0, column=1, sticky="ew")
    self._search_history_btn = ttk.Button(search_wrap, text="▾", width=1, style="SearchHistory.TButton", command=lambda: show_search_history_menu_callback(self))
    self._search_history_btn.grid(row=0, column=2, sticky="ns", padx=(6, 0))

    self._connect_btn = ttk.Button(
        command_bar,
        text="Verbinden",
        style="Accent.TButton",
        command=lambda: connect_selected_sessions_callback(self),
        state=tk.DISABLED,
    )
    self._connect_btn.grid(row=0, column=1)
    _decorate(self._connect_btn, icon="terminal")

    quick_bar = ttk.Frame(self._main_frame, style="QuickBar.TFrame", padding=(18, 8, 12, 2))
    quick_bar.grid(row=2, column=0, sticky="ew")
    self._quick_bar = quick_bar
    self._toolbar_specs = {
        "show_select_all": ("Alle auswählen", lambda: select_all_callback(self)),
        "show_deselect_all": ("Alle abwählen", lambda: deselect_all_callback(self)),
        "show_expand_all": ("Ausklappen", lambda: expand_all_callback(self)),
        "show_collapse_all": ("Einklappen", lambda: collapse_all_callback(self)),
        "show_add_connection": ("Neue Verbindung", lambda: add_session_callback(self)),
        "show_reload": ("Neu laden", lambda: reload_sessions_callback(self)),
        "show_open_tunnel": ("Tunnel öffnen…", lambda: open_tunnel_callback(self)),
        "show_check_hosts": ("Hosts prüfen", lambda: self._tree.check_selected_hosts(timeout=self.settings.host_check_timeout_seconds)),
        "show_restart_servers": ("Server neu starten…", lambda: restart_servers_callback(self, self._tree.get_selected_sessions())),
    }
    quick_icons = {
        "show_select_all": "check2-square",
        "show_deselect_all": "square",
        "show_expand_all": "chevron-expand",
        "show_collapse_all": "chevron-contract",
        "show_reload": "arrow-repeat",
        "show_open_tunnel": "ethernet",
        "show_check_hosts": "shield-check",
        "show_restart_servers": "power",
    }
    for key in TOOLBAR_BUTTON_ORDER:
        if key == "show_add_connection":
            continue
        label, command = self._toolbar_specs[key]
        button = ttk.Button(quick_bar, text=label, style="Quick.TButton", command=command)
        self._toolbar_buttons[key] = button
        _decorate(button, icon=quick_icons.get(key))
    self._toolbar_overflow_menu = tk.Menu(quick_bar, tearoff=False)
    self._toolbar_overflow_btn = ttk.Menubutton(
        quick_bar,
        text=f"Mehr{_MENU_ARROW_GAP}",
        menu=self._toolbar_overflow_menu,
        style="Quick.TButton",
    )
    _decorate(self._toolbar_overflow_btn, icon="three-dots")
    layout_toolbar_buttons(self)
    self._main_frame.bind("<Configure>", lambda event: _on_main_frame_resized(self, event), add="+")

    refresh_checkbox_images(self)

    self._tree = SessionTree(
        self._main_frame,
        sessions=self._sessions,
        img_unchecked=self._img_unchecked,
        img_checked=self._img_checked,
        on_selection_changed=lambda count: on_selection_changed_callback(self, count),
        initial_open_folders=self._initial_open_folders,
        initial_session_colors=self._initial_session_colors,
        on_quick_connect=lambda session: quick_connect_session_callback(self, session),
        on_connect_sessions=lambda sessions: connect_sessions_callback(self, sessions),
        on_add_favorite=lambda session, only: add_favorite_session_callback(self, session, only),
        on_add_favorites=lambda sessions, only: add_favorite_sessions_callback(self, sessions, only),
        on_remove_favorite=lambda session: remove_favorite_session_callback(self, session),
        favorite_keys_getter=lambda: set(self._favorite_sessions),
        on_edit_session=lambda session: edit_session_callback(self, session),
        on_set_sessions_username=lambda sessions: set_sessions_username_callback(self, sessions),
        on_clear_sessions_username=lambda sessions: clear_sessions_username_callback(self, sessions),
        on_delete_session=lambda session: delete_session_callback(self, session),
        on_delete_folder=lambda sessions, folder_key: delete_folder_callback(self, sessions, folder_key),
        on_rename_folder=lambda folder_key: rename_folder_callback(self, folder_key),
        on_add_session=lambda: add_session_callback(self),
        on_add_session_in_folder=lambda folder_key: add_session_callback(self, folder_key),
        on_duplicate_ssh_alias=lambda session: duplicate_ssh_alias_callback(self, session),
        on_inspect_ssh_config=lambda session: inspect_ssh_config_callback(self, session),
        on_duplicate_app_session=lambda session: duplicate_app_session_callback(self, session),
        on_move_session=lambda session: move_session_callback(self, session),
        on_move_sessions=lambda sessions: move_sessions_callback(self, sessions),
        on_open_ssh_config_in_vscode=lambda: open_ssh_config_in_vscode_callback(self),
        on_deploy_ssh_key=lambda sessions: deploy_ssh_key_callback(self, sessions),
        on_remove_ssh_key=lambda sessions: remove_ssh_key_callback(self, sessions),
        on_open_tunnel=lambda session=None: open_tunnel_callback(self, session),
        on_open_in_winscp=lambda sessions: open_in_winscp_callback(self, sessions),
        on_run_remote_command=lambda sessions: run_remote_command_callback(self, sessions),
        on_restart_servers=lambda sessions: restart_servers_callback(self, sessions),
        on_deploy_certificate_files=lambda sessions: deploy_certificate_files_callback(self, sessions),
        on_replace_certificates=lambda sessions: replace_certificates_callback(self, sessions),
        on_resolve_dns=lambda sessions: resolve_dns_for_sessions_callback(self, sessions),
        on_resolve_dns_with_server=lambda sessions: resolve_dns_for_sessions_with_server_callback(self, sessions),
        on_open_via_jumphost=lambda session: open_via_jumphost_callback(self, session),
        on_copy_ssh_command=lambda session: copy_ssh_command_callback(self, session),
        on_ui_state_changed=lambda: persist_ui_state_callback(self),
        notes_getter=lambda key: self._notes.get(key, ""),
        on_edit_note=lambda session: edit_session_note_callback(self, session),
        on_hide_column=lambda column_key: hide_column_from_header_callback(self, column_key),
        toolbar_settings=self.settings.toolbar,
    )
    self._tree.grid(row=3, column=0, sticky="nsew", padx=18, pady=(8, 0))

    status_bar = ttk.Frame(self._main_frame, style="StatusBar.TFrame", padding=(18, 6))
    status_bar.grid(row=4, column=0, sticky="ew", pady=(8, 0))
    status_bar.columnconfigure(0, weight=1)
    self._selection_status_var = tk.StringVar(value="Keine Verbindung ausgewählt")
    ttk.Label(status_bar, textvariable=self._selection_status_var, style="StatusBar.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(status_bar, text="Enter: verbinden  ·  Ctrl+P: Befehlspalette", style="StatusBar.TLabel").grid(row=0, column=1, sticky="e")

    self._search_history_after_id = None
    self._search_var.trace_add("write", lambda *_: on_search_changed_callback(self))

    self._settings_view = SettingsView(self, self)

