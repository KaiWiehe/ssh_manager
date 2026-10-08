"""Individual, persistent toolbar choices backed by the existing action menus."""
import json
import tkinter as tk
from tkinter import ttk, messagebox

CONTEXT_ACTIONS = (
    'Verbindung öffnen', 'In WinSCP öffnen', 'Bearbeiten…', 'Als eigene Verbindung übernehmen…',
    'Benutzer setzen…', 'Benutzer entfernen…', 'Hostname kopieren', 'Name kopieren', 'Notiz kopieren',
    'SSH-Befehl kopieren', 'Über Jumphost öffnen…', 'Host prüfen', 'Aus Favoriten entfernen',
    'Zu Favoriten hinzufügen…', 'Duplizieren…', 'In Ordner verschieben…', 'Alias als App-Eintrag übernehmen…',
    'Konfiguration anzeigen (ssh -G)…', 'SSH Config in VS Code öffnen', 'Löschen',
    'Alle auswählen', 'Alle abwählen', 'Unterordner ausklappen', 'Unterordner einklappen',
    'Neue Verbindung hier…', 'Ordner umbenennen…', 'Ordner löschen', 'Farbe entfernen',
    'Verbindung als Markdown kopieren', 'Verbindung als CSV exportieren…', 'Verbindung als Excel exportieren…',
    'Ordner als Markdown kopieren', 'Ordner als CSV exportieren…', 'Ordner als Excel exportieren…',
    'Auswahl als Markdown kopieren', 'Auswahl als CSV exportieren…', 'Auswahl als Excel exportieren…',
    'SSH-Befehle', 'Hostnames', 'Namen', 'Notizen', '✕ Farbe entfernen',
    'Verbindungen im Ordner diagnostizieren…', 'Alle im Ordner verbinden', 'Hosts prüfen',
    'Remote-Befehl ausführen…', 'Server neu starten…', 'Dateien verteilen…', 'Zertifikate ersetzen…',
    'DNS/IP auflösen…', 'SSH Key übertragen…', 'SSH Key entfernen…',
    'Auswahl verbinden', 'Auswahl-Hostnamen kopieren', 'Auswahl-Namen kopieren', 'Auswahl-Notizen kopieren',
    'Auswahl diagnostizieren…', 'Auswahl in WinSCP öffnen', 'Auswahl zu Favoriten hinzufügen…',
    'Ordner für Auswahl ändern…', 'Benutzer für Auswahl setzen…', 'Benutzer für Auswahl entfernen…',
    'Auswahl-SSH-Befehle kopieren', 'Befehl auf Auswahl ausführen…', 'Server aus Auswahl neu starten…',
    'Dateien auf Auswahl übertragen…', 'Zertifikate auf Auswahl ersetzen…', 'DNS/IP für Auswahl auflösen…',
    'Auswahl-Hosts prüfen', 'DNS/IP für Auswahl auflösen… (DNS-Auswahl)', 'DNS/IP auflösen… (DNS-Auswahl)',
    'SSH Key auf Auswahl übertragen…', 'SSH Key aus Auswahl entfernen…',
)


def _entries(menu):
    end = menu.index('end')
    return range(end + 1) if end is not None else ()


def _label(menu, index):
    return menu.entrycget(index, 'label').split(' — ')[0]


def _find(menu, path):
    command = menu.cget('postcommand')
    if command:
        menu.tk.call(command)
    for index in _entries(menu):
        if menu.type(index) == 'separator' or _label(menu, index) != path[0]:
            continue
        if len(path) == 1:
            return menu, index
        if menu.type(index) == 'cascade':
            return _find(menu.nametowidget(menu.entrycget(index, 'menu')), path[1:])
    return None


def _walk(menu, path=()):
    for index in _entries(menu):
        kind = menu.type(index)
        if kind == 'separator':
            continue
        label = _label(menu, index)
        if kind == 'command' and menu.entrycget(index, 'command'):
            yield (*path, label)
        elif kind == 'cascade' and label not in ('App-Werkzeuge', 'Verbindung / Ordner verwalten'):
            yield from _walk(menu.nametowidget(menu.entrycget(index, 'menu')), (*path, label))


def invoke_toolbar_action(app, source_name, path):
    owned = None
    if source_name == 'Verbindung / Ordner':
        tree = app._tree
        iid = tree._tv.focus()
        if iid in tree._item_to_session:
            owned = tree._show_session_menu(iid, return_menu=True)
        elif iid in tree._item_to_folder_key:
            owned = tree._show_folder_menu(iid, return_menu=True)
        if owned is None:
            messagebox.showinfo('Aktion nicht verfügbar', 'Zuerst eine Verbindung oder einen Ordner fokussieren.', parent=app)
            return
        matches = [(menu, index) for menu in _menus(owned) for index in _entries(menu)
                   if menu.type(index) == 'command' and (_label(menu, index).strip() == path[0] or _label(menu, index).startswith(path[0] + ' ('))]
        found = matches[0] if matches else None
    else:
        source = app._actions_menu if source_name == 'Aktionen' else app._app_menu_sources[source_name]
        found = _find(source, path)
    try:
        if found is None or found[0].entrycget(found[1], 'state') == 'disabled':
            messagebox.showinfo('Aktion nicht verfügbar', 'Diese Aktion ist für den aktuellen Fokus oder die Häkchen-Auswahl nicht verfügbar.', parent=app)
            return
        found[0].invoke(found[1])
    finally:
        if owned is not None:
            owned.destroy()


def _menus(menu):
    yield menu
    for index in _entries(menu):
        if menu.type(index) == 'cascade':
            yield from _menus(menu.nametowidget(menu.entrycget(index, 'menu')))


def install_toolbar_actions(app):
    catalog = {}
    sources = {'Aktionen': app._actions_menu, **app._app_menu_sources}
    for name, menu in sources.items():
        for path in _walk(menu):
            key = 'action:' + json.dumps([name, *path], ensure_ascii=False)
            catalog[key] = (' → '.join([name, *path]), lambda n=name, p=path: invoke_toolbar_action(app, n, p))
    from .constants import PALETTE
    for label in (*CONTEXT_ACTIONS, *(name for name, _ in PALETTE)):
        key = 'action:' + json.dumps(['Verbindung / Ordner', label], ensure_ascii=False)
        catalog[key] = ('Verbindung / Ordner → ' + label, lambda p=(label,): invoke_toolbar_action(app, 'Verbindung / Ordner', p))
    app._extra_toolbar_catalog = catalog
    parent = app._toolbar_buttons['show_reload'].master
    for key, (label, command) in catalog.items():
        short = label.rsplit(' → ', 1)[-1]
        app._toolbar_specs[key] = (short, command)
        app._toolbar_buttons[key] = ttk.Button(parent, text=short, style='Quick.TButton', command=command)
