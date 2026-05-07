from __future__ import annotations

import json
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import AppSettings, AppearanceSettings, SourceVisibilitySettings, ToolbarSettings, WindowsTerminalSettings, settings_to_dict
from .constants import _SSH_CONFIG_FILE
from .dialogs_toast import ToastNotification
from .storage import load_settings_from_path


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


class SettingsView(ttk.Frame):
    """Einstellungsansicht im Hauptfenster."""

    THEME_LABELS = {
        "default": "Default",
        "modern_light": "Modern Light",
        "dark_neutral": "Dark Neutral",
        "midnight": "Midnight",
    }
    ACCENT_COLORS = [
        ("Blau", "#2563eb", "🟦"),
        ("Sky", "#0ea5e9", "🔷"),
        ("Türkis", "#14b8a6", "🟩"),
        ("Grün", "#22c55e", "🟩"),
        ("Lime", "#84cc16", "🟩"),
        ("Amber", "#f59e0b", "🟨"),
        ("Orange", "#f97316", "🟧"),
        ("Rot", "#ef4444", "🟥"),
        ("Violett", "#a855f7", "🟪"),
        ("Pink", "#ec4899", "💗"),
    ]
    FONT_FAMILIES = ["Segoe UI", "Arial", "Calibri", "Consolas", "Cascadia Mono", "Verdana"]

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
        self._theme_var = tk.StringVar()
        self._accent_var = tk.StringVar()
        self._ui_font_family_var = tk.StringVar()
        self._ui_font_size_var = tk.StringVar()
        self._tree_font_family_var = tk.StringVar()
        self._tree_font_size_var = tk.StringVar()
        self._tree_row_height_var = tk.StringVar()
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
        self._root_frame = root

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
        ttk.Button(actions, text="Zurück", command=lambda: self._cancel_and_show_main_view()).pack(side="left", padx=(8, 0))

        sections = [
            ("general", "Allgemein"),
            ("sources", "Quellen / Ansicht"),
            ("appearance", "Design"),
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
        self._section_frames["appearance"] = self._build_appearance_section()
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
            ("show_favorites", "Favoriten", "Eigener Bereich oben im Tree"),
            ("show_recent", "Zuletzt verwendet", "Die letzten geöffneten Verbindungen"),
        ]
        grid = ttk.Frame(frame, style="SettingsPanel.TFrame")
        grid.grid(row=2, column=0, sticky="nw")
        for row, (key, label, hint) in enumerate(items):
            var = tk.BooleanVar()
            self._source_visibility_vars[key] = var
            ttk.Checkbutton(grid, text=label, variable=var, command=self._on_source_visibility_changed).grid(row=row * 2, column=0, sticky="w", pady=(0, 2))
            ttk.Label(grid, text=hint, style="SettingsHint.TLabel").grid(row=row * 2 + 1, column=0, sticky="w", pady=(0, 8), padx=(24, 0))
        self._add_section_tools(frame, 3, "sources")
        return frame

    def _build_appearance_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Design", "Wähle Theme und Akzentfarbe. Default bleibt die bisherige Optik.")
        grid = ttk.Frame(frame, style="SettingsPanel.TFrame")
        grid.grid(row=2, column=0, sticky="nw")
        grid.columnconfigure(0, minsize=220)
        grid.columnconfigure(1, minsize=260)

        ttk.Label(grid, text="Theme:", style="SettingsValue.TLabel").grid(row=0, column=0, sticky="nw", pady=6, padx=(0, 12))
        theme_list = tk.Listbox(grid, height=len(self.THEME_LABELS), exportselection=False, activestyle="none")
        theme_list.grid(row=0, column=1, sticky="ew", pady=6)
        for label in self.THEME_LABELS.values():
            theme_list.insert("end", label)
        theme_list.bind("<<ListboxSelect>>", self._on_theme_list_selected)
        self._theme_list = theme_list

        ttk.Label(grid, text="Akzentfarbe:", style="SettingsValue.TLabel").grid(row=1, column=0, sticky="nw", pady=(16, 6), padx=(0, 12))
        accent_list = tk.Listbox(grid, height=10, exportselection=False, activestyle="none")
        accent_list.grid(row=1, column=1, sticky="ew", pady=(16, 6))
        for index, (name, hex_color, _swatch) in enumerate(self.ACCENT_COLORS):
            accent_list.insert("end", f"■ {name}  {hex_color}")
            accent_list.itemconfig(index, foreground=hex_color, selectforeground="#ffffff")
        accent_list.bind("<<ListboxSelect>>", self._on_accent_list_selected)
        self._accent_list = accent_list

        font_form = ttk.Frame(frame, style="SettingsPanel.TFrame")
        font_form.grid(row=3, column=0, sticky="nw", pady=(20, 0))
        font_form.columnconfigure(0, minsize=220)
        font_form.columnconfigure(1, minsize=180)
        ttk.Label(font_form, text="UI-Schriftart:", style="SettingsValue.TLabel").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        self._ui_font_family_combo = ttk.Combobox(font_form, textvariable=self._ui_font_family_var, values=self.FONT_FAMILIES, state="readonly", width=24)
        self._ui_font_family_combo.grid(row=0, column=1, sticky="ew", pady=6)
        self._ui_font_family_combo.bind("<<ComboboxSelected>>", self._on_appearance_changed)
        ttk.Label(font_form, text="UI-Schriftgröße:", style="SettingsValue.TLabel").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 12))
        self._ui_font_size_spin = ttk.Spinbox(font_form, from_=8, to=14, textvariable=self._ui_font_size_var, width=8, command=self._on_appearance_changed)
        self._ui_font_size_spin.grid(row=1, column=1, sticky="w", pady=6)
        self._ui_font_size_spin.bind("<KeyRelease>", self._on_appearance_changed)
        ttk.Label(font_form, text="Tree-Schriftart:", style="SettingsValue.TLabel").grid(row=2, column=0, sticky="w", pady=(16, 6), padx=(0, 12))
        self._tree_font_family_combo = ttk.Combobox(font_form, textvariable=self._tree_font_family_var, values=self.FONT_FAMILIES, state="readonly", width=24)
        self._tree_font_family_combo.grid(row=2, column=1, sticky="ew", pady=(16, 6))
        self._tree_font_family_combo.bind("<<ComboboxSelected>>", self._on_appearance_changed)
        ttk.Label(font_form, text="Tree-Schriftgröße:", style="SettingsValue.TLabel").grid(row=3, column=0, sticky="w", pady=6, padx=(0, 12))
        self._tree_font_size_spin = ttk.Spinbox(font_form, from_=8, to=16, textvariable=self._tree_font_size_var, width=8, command=self._on_appearance_changed)
        self._tree_font_size_spin.grid(row=3, column=1, sticky="w", pady=6)
        self._tree_font_size_spin.bind("<KeyRelease>", self._on_appearance_changed)
        ttk.Label(font_form, text="Tree-Zeilenhöhe:", style="SettingsValue.TLabel").grid(row=4, column=0, sticky="w", pady=6, padx=(0, 12))
        self._tree_row_height_spin = ttk.Spinbox(font_form, from_=22, to=44, textvariable=self._tree_row_height_var, width=8, command=self._on_appearance_changed)
        self._tree_row_height_spin.grid(row=4, column=1, sticky="w", pady=6)
        self._tree_row_height_spin.bind("<KeyRelease>", self._on_appearance_changed)

        ttk.Label(frame, text="Hinweis: Bei manchen nativen Windows-Menüs greift Tkinter-Design nur eingeschränkt.", style="SettingsHint.TLabel").grid(row=4, column=0, sticky="w", pady=(14, 0))
        self._add_section_tools(frame, 5, "appearance")
        return frame

    def _add_section_tools(self, frame: ttk.Frame, row: int, section: str) -> None:
        tools = ttk.Frame(frame, style="SettingsPanel.TFrame")
        tools.grid(row=row, column=0, sticky="w", pady=(18, 0))
        ttk.Button(tools, text="Gespeicherten Stand wiederherstellen", command=lambda s=section: self._restore_section(s)).pack(side="left")
        ttk.Button(tools, text="Bereich zurücksetzen", command=lambda s=section: self._reset_section(s)).pack(side="left", padx=(8, 0))

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
            ("show_username_column", "Spalte Benutzer"),
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
        self._column_order_list = tk.Listbox(order_frame, height=4, exportselection=False)
        self._column_order_list.grid(row=1, column=0, rowspan=2, sticky="w")
        btns = ttk.Frame(order_frame, style="SettingsPanel.TFrame")
        btns.grid(row=1, column=1, sticky="nw", padx=(10, 0))
        ttk.Button(btns, text="Hoch", command=lambda: self._move_column_order(-1), width=10).pack(anchor="w")
        ttk.Button(btns, text="Runter", command=lambda: self._move_column_order(1), width=10).pack(anchor="w", pady=(6, 0))
        self._add_section_tools(frame, 4, "toolbar")
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
        from .actions_ui import apply_settings

        apply_settings(self._app, settings)
        self.load_from_app()
        ToastNotification(self._app, "Einstellungen importiert")

    def _show_main_view(self) -> None:
        from .actions_ui import show_main_view

        show_main_view(self._app)

    def _cancel_and_show_main_view(self) -> None:
        from .actions_ui import preview_appearance, preview_source_visibility, preview_toolbar_visibility, show_main_view

        persisted = getattr(self._app, "_persisted_settings", self._app.settings)
        preview_appearance(self._app, persisted.appearance)
        preview_toolbar_visibility(self._app, persisted.toolbar)
        preview_source_visibility(self._app, persisted.source_visibility)
        self.load_from_app()
        show_main_view(self._app)

    def _show_section(self, key: str) -> None:
        self._active_section = key
        labels = {
            "general": "Allgemein",
            "sources": "Quellen / Ansicht",
            "appearance": "Design",
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
        settings = getattr(self._app, "_persisted_settings", self._app.settings)
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
        self._set_listbox_selection(self._theme_list, list(self.THEME_LABELS).index(settings.appearance.theme if settings.appearance.theme in self.THEME_LABELS else "default"))
        accent_values = [hex_color for _name, hex_color, _swatch in self.ACCENT_COLORS]
        accent = settings.appearance.accent_color if settings.appearance.accent_color in accent_values else accent_values[0]
        self._set_listbox_selection(self._accent_list, accent_values.index(accent))
        self._ui_font_family_var.set(settings.appearance.ui_font_family)
        self._ui_font_size_var.set(str(settings.appearance.ui_font_size))
        self._tree_font_family_var.set(settings.appearance.tree_font_family)
        self._tree_font_size_var.set(str(settings.appearance.tree_font_size))
        self._tree_row_height_var.set(str(settings.appearance.tree_row_height))

    def _set_listbox_selection(self, listbox: tk.Listbox, index: int) -> None:
        listbox.selection_clear(0, "end")
        listbox.selection_set(index)
        listbox.activate(index)
        listbox.see(index)

    def _on_theme_list_selected(self, _event=None) -> None:
        selection = self._theme_list.curselection()
        if selection:
            self._theme_var.set(list(self.THEME_LABELS)[selection[0]])
            self._on_appearance_changed()

    def _on_accent_list_selected(self, _event=None) -> None:
        selection = self._accent_list.curselection()
        if selection:
            self._accent_var.set(self.ACCENT_COLORS[selection[0]][1])
            self._on_appearance_changed()

    def _on_appearance_changed(self, _event=None) -> None:
        from .actions_ui import preview_appearance

        preview_appearance(self._app, self._collect_appearance_settings())

    def _on_toolbar_changed(self) -> None:
        from .actions_ui import preview_toolbar_visibility

        preview_toolbar_visibility(self._app, self._collect_toolbar_settings())

    def _column_label(self, key: str) -> str:
        return {
            "username": "Benutzer",
            "notes": "Notiz",
            "hostname": "Hostname",
            "port": "Port",
        }[key]

    def _column_key_from_label(self, label: str) -> str:
        return {
            "Benutzer": "username",
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

    def _collect_appearance_settings(self) -> AppearanceSettings:
        if not hasattr(self, "_theme_list") or not hasattr(self, "_accent_list"):
            return AppearanceSettings()
        theme_selection = self._theme_list.curselection()
        theme_keys = list(self.THEME_LABELS)
        theme = theme_keys[theme_selection[0]] if theme_selection else "default"
        accent_selection = self._accent_list.curselection()
        accent = self.ACCENT_COLORS[accent_selection[0]][1] if accent_selection else self.ACCENT_COLORS[0][1]
        def bounded_int(var: tk.StringVar, default: int, low: int, high: int) -> int:
            try:
                return min(high, max(low, int(var.get().strip())))
            except ValueError:
                return default

        ui_font_family = self._ui_font_family_var.get().strip() or "Segoe UI"
        if ui_font_family not in self.FONT_FAMILIES:
            ui_font_family = "Segoe UI"
        tree_font_family = self._tree_font_family_var.get().strip() or "Segoe UI"
        if tree_font_family not in self.FONT_FAMILIES:
            tree_font_family = "Segoe UI"

        return AppearanceSettings(
            theme=theme,
            accent_color=accent,
            ui_font_family=ui_font_family,
            ui_font_size=bounded_int(self._ui_font_size_var, 10, 8, 14),
            tree_font_family=tree_font_family,
            tree_font_size=bounded_int(self._tree_font_size_var, 10, 8, 16),
            tree_row_height=bounded_int(self._tree_row_height_var, 28, 22, 44),
        )

    def _on_source_visibility_changed(self) -> None:
        from .actions_ui import preview_source_visibility

        preview_source_visibility(self._app, self._collect_source_visibility_settings())

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
            appearance=self._collect_appearance_settings(),
        )

    def _save(self) -> None:
        try:
            settings = self._collect_settings()
        except ValueError as e:
            messagebox.showwarning("Einstellungen", str(e), parent=self)
            return
        from .actions_ui import apply_settings

        apply_settings(self._app, settings)
        self._app._persisted_settings = settings
        self._show_main_view()

    def _restore_section(self, section: str) -> None:
        persisted = getattr(self._app, "_persisted_settings", self._app.settings)
        from .actions_ui import preview_appearance, preview_source_visibility, preview_toolbar_visibility

        if section == "appearance":
            preview_appearance(self._app, persisted.appearance)
        elif section == "toolbar":
            preview_toolbar_visibility(self._app, persisted.toolbar)
        elif section == "sources":
            preview_source_visibility(self._app, persisted.source_visibility)
        self.load_from_app()

    def _reset_section(self, section: str) -> None:
        defaults = self._app._default_settings_factory()
        from .actions_ui import preview_appearance, preview_source_visibility, preview_toolbar_visibility

        if section == "appearance":
            preview_appearance(self._app, defaults.appearance)
        elif section == "toolbar":
            preview_toolbar_visibility(self._app, defaults.toolbar)
        elif section == "sources":
            preview_source_visibility(self._app, defaults.source_visibility)
        self.load_from_app()

    def _reset_settings(self) -> None:
        from .actions_ui import reset_settings

        reset_settings(self._app)
        self.load_from_app()

    def _reset_view_state(self) -> None:
        from .actions_ui import reset_view_state

        reset_view_state(self._app)
