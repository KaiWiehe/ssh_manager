"""Launch an isolated preview of the SSH-Manager design system.

No registry, SSH configuration, or application data is read or written.
Use ``--screenshot build/ui-preview.png`` for a visual regression artifact.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ssh_manager_app.core import _create_checkbox_images
from ssh_manager_app.models import AppSettings
from ssh_manager_app.themes import palette_for_theme
from ssh_manager_app.ui import configure_app_styles


def _tree(parent: ttk.Frame) -> ttk.Treeview:
    frame = ttk.Frame(parent, style="TreeSurface.TFrame")
    frame.pack(fill="both", expand=True, padx=18, pady=(8, 0))
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    tree = ttk.Treeview(frame, columns=("user", "host", "port", "note"))
    tree.heading("#0", text="Name", anchor="w")
    tree.heading("user", text="Benutzer", anchor="w")
    tree.heading("host", text="Hostname", anchor="w")
    tree.heading("port", text="Port", anchor="w")
    tree.heading("note", text="Notizen", anchor="w")
    tree.column("#0", width=250)
    tree.column("user", width=135)
    tree.column("host", width=220)
    tree.column("port", width=65)
    tree.column("note", width=220)
    unchecked, checked = _create_checkbox_images(parent, background="#ffffff", border="#d8dee8", check="#2563eb")
    tree._preview_images = (unchecked, checked)  # type: ignore[attr-defined]
    favorites = tree.insert("", "end", text="★ Favoriten", open=True)
    tree.insert(favorites, "end", text="Production API", image=checked, values=("tool-admin", "api.example.net", 22, "Kritisches System"))
    ssh_config = tree.insert("", "end", text="SSH Config", open=True)
    tree.insert(ssh_config, "end", text="Development", image=unchecked, values=("dev-sys", "dev.example.net", 22, ""))
    tree.insert(ssh_config, "end", text="Database", image=unchecked, values=("tool-admin", "db.example.net", 2222, "Wartung sonntags"))
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    return tree


def _main_tab(parent: ttk.Frame) -> None:
    header = ttk.Frame(parent, style="Header.TFrame", padding=(18, 13))
    header.pack(fill="x")
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="SSH-Manager", style="HeaderTitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(header, text="Verbindungen zentral finden, verwalten und öffnen", style="HeaderSubtitle.TLabel").grid(row=1, column=0, sticky="w")
    ttk.Button(header, text="Neue Verbindung").grid(row=0, column=1, rowspan=2, padx=(8, 0))
    ttk.Button(header, text="Einstellungen").grid(row=0, column=2, rowspan=2, padx=(8, 0))

    bar = ttk.Frame(parent, style="CommandBar.TFrame", padding=(18, 10))
    bar.pack(fill="x")
    bar.columnconfigure(1, weight=1)
    palette = palette_for_theme(parent.winfo_toplevel().settings.appearance.theme)
    tk.Label(bar, text="Suche", background=palette.surface_alt, foreground=palette.muted, borderwidth=0).grid(row=0, column=0, padx=(0, 7))
    ttk.Entry(bar).grid(row=0, column=1, sticky="ew", padx=(0, 10))
    ttk.Button(bar, text="Verbinden (1 ausgewählt)", style="Accent.TButton").grid(row=0, column=2, padx=(0, 8))
    for column, label in enumerate(("Auswahl", "Ansicht", "Aktionen"), start=3):
        ttk.Menubutton(bar, text=label).grid(row=0, column=column, padx=(0, 6))
    quick = ttk.Frame(parent, style="QuickBar.TFrame", padding=(18, 8, 12, 2))
    quick.pack(fill="x")
    for label in ("Alle auswählen", "Alle abwählen", "Ausklappen", "Einklappen", "Mehr"):
        ttk.Button(quick, text=label, style="Quick.TButton").pack(side="left", padx=(0, 6))
    _tree(parent)
    status = ttk.Frame(parent, style="StatusBar.TFrame", padding=(18, 6))
    status.pack(fill="x", pady=(8, 0))
    ttk.Label(status, text="1 Verbindung ausgewählt", style="StatusBar.TLabel").pack(side="left")
    ttk.Label(status, text="Enter: verbinden  ·  Ctrl+P: Befehlspalette", style="StatusBar.TLabel").pack(side="right")


def _form_tab(parent: ttk.Frame) -> None:
    panel = ttk.Frame(parent, style="SettingsPanel.TFrame", padding=24)
    panel.pack(fill="both", expand=True, padx=32, pady=28)
    ttk.Label(panel, text="Neue Verbindung", style="SettingsSectionTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(panel, text="Die Verbindung wird nur im SSH-Manager gespeichert.", style="SettingsHint.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 18))
    for row, label in enumerate(("Name", "Hostname", "Benutzer", "Port"), start=2):
        ttk.Label(panel, text=f"{label}:").grid(row=row, column=0, sticky="w", padx=(0, 18), pady=6)
        ttk.Entry(panel, width=42).grid(row=row, column=1, sticky="ew", pady=6)
    panel.columnconfigure(1, weight=1)
    actions = ttk.Frame(panel, style="SettingsPanel.TFrame")
    actions.grid(row=6, column=0, columnspan=2, sticky="e", pady=(22, 0))
    ttk.Button(actions, text="Abbrechen").pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="Verbindung speichern", style="Accent.TButton").pack(side="left")


def _status_tab(parent: ttk.Frame) -> None:
    panel = ttk.Frame(parent, padding=24)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="Serverstatus", style="DialogTitle.TLabel").pack(anchor="w")
    ttk.Label(panel, text="2 von 3 Prüfungen abgeschlossen", style="Muted.TLabel").pack(anchor="w", pady=(4, 16))
    table = ttk.Treeview(panel, columns=("status", "details"), show="headings", height=8)
    table.heading("status", text="Status", anchor="w")
    table.heading("details", text="Details", anchor="w")
    table.column("status", width=180)
    table.column("details", width=520)
    table.insert("", "end", values=("Online", "SSH erreichbar"))
    table.insert("", "end", values=("Wird geprüft…", "Warte auf wildfly.service"))
    table.insert("", "end", values=("Fehlgeschlagen", "Zeitüberschreitung nach 5 Minuten"))
    table.pack(fill="both", expand=True)
    ttk.Button(panel, text="Schließen").pack(anchor="e", pady=(16, 0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--theme", choices=("default", "dark_neutral", "midnight"), default="default")
    parser.add_argument("--geometry", default="980x680")
    args = parser.parse_args()
    root = tk.Tk()
    root.title("SSH-Manager · Designvorschau")
    root.tk.call("tk", "scaling", args.scale)
    root.geometry(args.geometry)
    root.minsize(600, 450)
    root.settings = AppSettings()  # type: ignore[attr-defined]
    root.settings.appearance.theme = args.theme  # type: ignore[attr-defined]
    configure_app_styles(root)
    tabs = ttk.Notebook(root)
    tabs.pack(fill="both", expand=True)
    for label, builder in (("Hauptansicht", _main_tab), ("Formular", _form_tab), ("Status", _status_tab)):
        tab = ttk.Frame(tabs)
        tabs.add(tab, text=label)
        builder(tab)
    root.geometry(args.geometry)
    if args.screenshot:
        def capture() -> None:
            from PIL import ImageGrab

            root.update()
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(window=root.winfo_id()).save(args.screenshot)
            root.destroy()

        root.after(700, capture)
    root.mainloop()


if __name__ == "__main__":
    main()
