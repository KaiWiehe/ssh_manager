# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Commands

```bash
# App starten
python ssh_manager.py

# Tests ausführen
python -m pytest tests/

# Einzelnen Test ausführen
python -m pytest tests/test_logic.py::test_build_wt_command_single_session

# Syntax prüfen
python -m py_compile ssh_manager.py ssh_manager_app/*.py

# Syntax prüfen unter PowerShell (Wildcard wird sonst nicht expandiert)
$files = @('ssh_manager.py') + (Get-ChildItem -Path ssh_manager_app -Filter *.py | ForEach-Object { $_.FullName }); python -m py_compile @files

# Portable Windows-EXE bauen (auf Windows)
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

App-Laufzeit: keine externen Abhängigkeiten – nur Python-Standardbibliothek (`tkinter`, `winreg`, `subprocess`, `pathlib`, `socket`, `threading`, `xml.etree.ElementTree`).  
Aus tkinter genutzte Module: `tk`, `ttk`, `messagebox`, `simpledialog`, `filedialog`.

## Architektur

Die App war ursprünglich fast komplett in `ssh_manager.py`, wurde inzwischen aber vorsichtig in Module aufgeteilt. `ssh_manager.py` bleibt eine dünne Bootstrap-Shell mit `SSHManagerApp`, Fenster-Icon und zentraler Verdrahtung.

### Datenfluss

```
Registry (WinSCP)      ──┐
~/.ssh/config          ──┼──► storage/core ──► actions_ui.build_visible_sessions(app) ──► SessionTree.populate()
FileZilla sitemanager  ──┤
app_sessions.json      ──┤
notes.json / settings  ──┘
```

`SSHManagerApp` lädt beim Start WinSCP, SSH Config, FileZilla und eigene App-Sessions, filtert sie anhand der Anzeige-Einstellungen und gibt die sichtbaren Sessions an `SessionTree` weiter. Der "SSH Config"-Ordner wird immer oben sortiert, FileZilla landet unter `FileZilla Config`.

### Schichten / Module

**`ssh_manager.py`**
- enthält primär `SSHManagerApp` plus `set_window_icon()`
- zentrale Verdrahtung zwischen UI, Tree, Dialogen, Storage und Terminal-/Registry-Logik
- muss weiter direkt per `python ssh_manager.py` startbar bleiben

**`ssh_manager_app/constants.py`**
- App-Konstanten, Dateipfade, Standardordnernamen

**`ssh_manager_app/models.py`**
- `Session`
- Settings-Dataclasses (`ToolbarSettings`, `WindowsTerminalSettings`, `SourceVisibilitySettings`, `ImportSettings`, `AppearanceSettings`, `AppSettings`)
- `color_tag()`
- `default_settings()` / `settings_to_dict()`

**`ssh_manager_app/storage.py`**
- Laden/Speichern von Settings, UI-State, Notes, App-Sessions
- Loader für FileZilla und SSH Config

**`ssh_manager_app/core.py`**
- `parse_session_key()`
- `build_wt_command()`
- `build_jump_wt_command()`
- `build_remote_command_wt_command()`
- `build_remote_script_wt_command()` für lokale/remote Skript-Runbooks per SSH
- `build_ssh_copy_id_command()`
- `build_ssh_remove_key_command()`
- `build_ssh_tunnel_command()`
- `check_host_reachable()`
- `_create_checkbox_images()`
- `TerminalLauncher`
- `RegistryReader`

**`ssh_manager_app/tree.py`**
- `SessionTree(ttk.Frame)` – Haupt-Treeview mit Checkboxen, Farben, Kontextmenüs und Notes-Tooltip/Info-Anbindung

**`ssh_manager_app/dialogs_base.py`**
- `UserDialog`
- `_build_quickselect_buttons()`
- `resolve_user_dialog_defaults()`

**`ssh_manager_app/dialogs_move_folder.py`**
- `MoveFolderDialog`

**`ssh_manager_app/dialogs_remote.py`**
- `JumpHostDialog`
- `RemoteCommandDialog` für Remote-Befehle und Skript-Runbooks
- `RemoteFavoriteEditDialog` für Runbook-Favoriten mit Name, Notiz und Pin-Status
- `RemoteCommandConfirmDialog`
- `SshCopyIdDialog`
- `SshRemoveKeyDialog`
- `SshTunnelDialog`

**`ssh_manager_app/dialogs_session_edit.py`**
- `SessionEditDialog`

**`ssh_manager_app/dialogs_settings_misc.py`**
- `SettingsView`
- `SshConfigInspectDialog`

**`ssh_manager_app/dialogs_toast.py`**
- `ToastNotification`

**`ssh_manager_app/dialogs.py`**
- nur Kompatibilitäts-Aggregator für bestehende Imports

**`ssh_manager_app/ui.py`**
- `configure_app_styles()` / Theme-Styling inkl. Dark Mode
- `refresh_checkbox_images()`
- `build_main_ui()`

**`ssh_manager_app/themes.py`**
- Theme-Paletten für Light/Dark/Midnight

**`ssh_manager_app/version.py`**
- `APP_NAME` / `APP_VERSION` für App-Name und Packaging

**Packaging**
- `assets/ssh-manager.ico` – App-/EXE-Icon
- `assets/ssh-manager.png` – 256px Runtime-Icon für `iconphoto()`
- `assets/SSH-Logo.svg` – maßgebliche Icon-Quelle, aktuell ein simples schwarzes `>_`-Prompt-Logo
- `assets/SSH-Logo.png` – PNG-Fallback der Icon-Quelle
- `scripts/generate_icon.py` – generiert PNG/ICO-Frames; für das simple Prompt-Logo gibt es einen Pillow-Renderpfad ohne CairoSVG
- `ssh_manager.spec` – PyInstaller-Spec für portable Einzel-EXE
- `scripts/build_windows.ps1` – Windows-Build-Script
- `packaging/ssh_manager_version_info.txt` – Windows-Version-Metadaten

**Datenquellen:**
- `RegistryReader` – liest WinSCP-Sessions aus `HKCU\Software\Martin Prikryl\WinSCP 2\Sessions`
- `load_ssh_config_sessions()` – parst `~/.ssh/config` manuell (kein Parser-Import)
- `load_filezilla_config_sessions()` – liest FileZilla-Sites aus `%APPDATA%\FileZilla\sitemanager.xml`
- `app_sessions.json` – eigene Sessions (source=`app`) und SSH-Alias-Kopien (source=`ssh_alias`)
- `notes.json` – Session-Notizen für alle Quellen, nur app-intern gespeichert

### Session-Typen (`source`-Feld)

| source | Herkunft | SSH-Befehl |
|---|---|---|
| `winscp` | Registry | `ssh USER@HOST` |
| `app` | app_sessions.json | `ssh USER@HOST` |
| `ssh_config` | ~/.ssh/config (live) | `ssh ALIAS` |
| `ssh_alias` | app_sessions.json (Kopie) | `ssh ALIAS` |
| `filezilla_config` | FileZilla `sitemanager.xml` | `ssh USER@HOST` |

`ssh_config`- und `ssh_alias`-Sessions ignorieren den User-Dialog (`is_ssh_config_session = True`). FileZilla-Sessions verhalten sich wie normale Host-basierte Sessions.

Nur `app`- und `ssh_alias`-Sessions sind editierbar (umbenennen, verschieben, löschen, Ordner umbenennen).  
Nur `winscp`-Sessions unterstützen "In WinSCP öffnen".

### Windows Terminal / Quoting-Regeln

Kritisch für alle `build_*_command()`-Funktionen:

- WT parst `;` als eigenen Subcommand-Separator, auch innerhalb von `bash -c "..."`. Daher komplexe Kommandos nicht leichtfertig als verschachtelte Shell-Strings bauen.
- `~` muss **unquoted** bleiben, in single oder double quotes findet keine Tilde-Expansion statt.
- `bash` aus dem System-PATH ist unter Windows mit WSL die WSL-Bash, nicht Git Bash. Immer `_find_git_bash()` verwenden.
- Für einfache Fälle können `bash -c`-Strings funktionieren, aber sobald WT, Git Bash, `ssh`, Here-Docs oder Remote-Shell kombiniert werden, lieber früh auf **temporäre lokale Skriptdateien** wechseln.
- `wt.exe` kann als zusammengesetzter String mit `shell=True` gestartet werden, aber für einzelne direkte Starts ist eine Argumentliste robuster, wenn kein WT-Subcommand-String benötigt wird.
- WinSCP wird mit `subprocess.Popen([winscp_path, session_name])` ohne `shell=True` gestartet (direkte Binary).  
  `session_name` = `"/".join(session.folder_path + [session.display_name])`, z.B. `"TOM/TOM Client/NBB-SVM267"`.
- Bei neuen Features mit Terminal-Startpfaden den kompletten Ausführungspfad Ende-zu-Ende mitdenken: Windows → wt.exe → Git Bash → ssh → Remote-Shell.

### Remote-Befehle und Skript-Runbooks

`RemoteCommandDialog` unterstützt drei Modi:

1. `command` – nur ein Remote-Befehl, keine weiteren Skript-Einstellungen.
2. `local_script` – lokale Datei auswählen, per `scp` nach `/tmp` übertragen, mit Interpreter/Argumenten ausführen und danach wieder löschen.
3. `remote_script` – vorhandenes Skript auf dem Zielhost per Remote-Pfad starten.

Für Skript-Modi gibt es optional `before_command`, `arguments` und `after_command`. Die UI zeigt immer nur die Einstellungen des aktiven Modus; irrelevante Bereiche sollen nicht sichtbar sein. Es gibt keinen Modus „Benutzer pro Host“ mehr: eine komplette Befehlskette nutzt genau einen Benutzer.

Favoriten liegen im UI-State (`remote_command_favorites`) und enthalten das komplette Spec-Dict plus Metadaten wie `name`, `note` und `pinned`. `RemoteFavoriteEditDialog` ist der zentrale Dialog zum Anlegen/Bearbeiten; keine mehreren `simpledialog`-Popups verwenden. Favoriten müssen löschbar und anpinnbar bleiben; angepinnte Einträge stehen oben. History liegt unter `remote_command_history` und ist leichtergewichtig, kann aber ebenfalls Notizen/Labels anzeigen.

`build_remote_script_wt_command()` schreibt lokale temporäre Bash-Dateien und startet diese in Windows Terminal/Git Bash. Der Terminal-Output soll oben die geplante Reihenfolge anzeigen und die tatsächlichen Outputs mit klaren Headern trennen:

- `Output vom Vor-Befehl`
- `Output vom Skript`
- `Output vom Nach-Befehl`

Bei lokalen Skripten zusätzlich den Upload-Schritt sichtbar machen. Änderungen in diesem Bereich müssen Windows → WT → Git Bash → scp/ssh → Remote-Shell Ende-zu-Ende mitdenken.

### SSH-Tunnel (`build_ssh_tunnel_command`)

- `ssh_server`: Server, zu dem SSH sich verbindet (Pflichtfeld)
- `remote_host`: Ziel hinter dem SSH-Server, `"localhost"` = direkter Tunnel (kein Jumphost)
- Befehl: `ssh -N -L localport:remote_host:remoteport user@ssh_server`
- Für Tunnel-Start plus Zusatzinfos im Terminal ist eine **temporäre lokale Bash-Datei** robuster als ein verschachtelter `bash -c`-String.

### Ordner umbenennen (`_rename_folder`)

- Nutzt `simpledialog.askstring` für die Eingabe des neuen Namens
- Ändert `folder_path[depth]` in allen `_app_sessions` deren Pfad-Präfix und alter Name übereinstimmen
- Wirkt rekursiv auf Unterordner (tiefere `folder_path`-Einträge bleiben erhalten)

### Hosts prüfen (`check_host_reachable`)

- TCP-Connect auf Port 22 (oder Session-Port), Timeout 3s
- Läuft in Daemon-Threads, UI-Update via `after(0, ...)`
- Status wird als ✓/✗/⏳-Präfix im Baum-Label angezeigt (`_set_item_status`)
- Status wird beim nächsten `populate()` zurückgesetzt

### Persistenz

`%APPDATA%\SSH-Manager\ui_state.json` speichert geöffnete Ordner, Session-Farben, Suche und Suchverlauf. Änderungen am Baumzustand werden möglichst sofort weggeschrieben, nicht erst beim Beenden.  
`%APPDATA%\SSH-Manager\app_sessions.json` speichert eigene Sessions und SSH-Alias-Kopien.  
`%APPDATA%\SSH-Manager\settings.json` speichert Benutzer-Einstellungen, Toolbar-Sichtbarkeit, Quellenfilter, Windows-Terminal-Optik und Spaltenreihenfolge.  
`%APPDATA%\SSH-Manager\notes.json` speichert Notizen für Sessions aller Quellen.

Wichtige Refactor-Regel: Die Persistenz-Funktionen liegen inzwischen in `ssh_manager_app/storage.py`. Neue Datei- oder JSON-Logik möglichst dort ergänzen, nicht wieder direkt in `ssh_manager.py` verteilen.

Wichtig für den Baumzustand: `SessionTree` hält den vom Benutzer gesetzten Ordnerzustand separat in `_open_folders`. `get_open_folders()` soll diesen stabilen Cache zurückgeben, nicht den gerade sichtbaren Treeview-Zustand während Suche/Rebuild. Programmgesteuerte Rebuilds (`populate`, `refresh`, Suche, Zuletzt verwendet/Favoriten) dürfen keine Treeview-Open/Close-Events persistieren; dafür gibt es `_suppress_open_state_events` und `populate(..., update_open_state=False)` für temporäre Suchansichten.

### Einstellungen / konfigurierbares Verhalten

Früher kamen viele Defaults direkt aus Konstanten. Inzwischen ist das meiste in `settings.json` konfigurierbar und wird in `AppSettings` geladen:

- Quick-Users und Default-User
- Sichtbarkeit der Toolbar-Buttons
- Sichtbarkeit der Quellen in der Hauptansicht (`WinSCP`, `SSH Config`, `FileZilla Config`, `Eigene App-Verbindungen`, `Favoriten`, `Zuletzt verwendet`)
- Import-Optionen für WinSCP-/FileZilla-Benutzer
- Sichtbarkeit der Spalten `Benutzer`, `Hostname`, `Port`, `Notizen`
- Reihenfolge der sichtbaren Spalten per Drag & Drop; `Name` ist die feste Tree-Spalte links
- Themes, Akzentfarbe, UI-/Tree-Schrift und Tree-Zeilenhöhe
- Windows-Terminal-Optik (Profilname, Farben, Titelmodus)

Weiterhin als Konstanten relevant:
- `QUICK_USERS` – Fallback-Defaults für Schnellauswahl
- `DEFAULT_USER` – Fallback-Default
- `PALETTE` – 8 Einträge `(Name, "#rrggbb")` für die Farbauswahl
- `_SSH_CONFIG_DEFAULT_FOLDER` – Anzeigename des SSH-Config-Ordners (`"SSH Config"`)
- `_FILEZILLA_CONFIG_DEFAULT_FOLDER` – Anzeigename des FileZilla-Ordners (`"FileZilla Config"`)

### SessionTree-Callbacks (Übersicht)

| Callback | Signatur | Beschreibung |
|---|---|---|
| `on_selection_changed` | `(count: int)` | Checkbox-Änderung |
| `on_quick_connect` | `(Session)` | Doppelklick / Verbindung öffnen |
| `on_edit_session` | `(Session)` | Bearbeiten-Dialog |
| `on_delete_session` | `(Session)` | Session löschen |
| `on_delete_folder` | `(list[Session], str)` | Ordner löschen |
| `on_rename_folder` | `(str)` | Ordner umbenennen (folder_key) |
| `on_add_session` | `()` | Neue Session ohne Ordner-Preset, u. a. Empty State |
| `on_add_session_in_folder` | `(str)` | Neue Session in Ordner |
| `on_duplicate_ssh_alias` | `(Session)` | SSH-Alias duplizieren |
| `on_duplicate_app_session` | `(Session)` | App-Session duplizieren |
| `on_move_session` | `(Session)` | Einzelne Session verschieben |
| `on_move_sessions` | `(list[Session])` | Mehrere Sessions verschieben |
| `on_inspect_ssh_config` | `(Session)` | `ssh -G` anzeigen |
| `on_open_ssh_config_in_vscode` | `()` | SSH-Config in VS Code |
| `on_deploy_ssh_key` | `(list[Session])` | ssh-copy-id |
| `on_remove_ssh_key` | `(list[Session])` | SSH-Key entfernen |
| `on_open_tunnel` | `(Session \| None)` | Tunnel-Dialog öffnen |
| `on_open_in_winscp` | `(list[Session])` | WinSCP öffnen |
| `on_run_remote_command` | `(list[Session])` | Remote-Befehl auf Hosts ausführen |
| `on_ui_state_changed` | `()` | UI-State sofort persistieren |
| `notes_getter` | `(session_key: str) -> str` | Notizen für Tooltip / Spalte |
| `on_edit_note` | `(Session)` | Notiz bearbeiten |
| `on_set_sessions_username` | `(list[Session])` | festen Benutzer für Auswahl setzen |
| `on_clear_sessions_username` | `(list[Session])` | festen Benutzer für Auswahl entfernen |
| `on_add_favorite` | `(Session, bool)` | einzelne Session zu Favoriten |
| `on_add_favorites` | `(list[Session], bool)` | mehrere Sessions zu Favoriten |
| `on_remove_favorite` | `(Session)` | Favorit entfernen |
| `favorite_keys_getter` | `() -> set[str]` | Favoritenstatus für Kontextmenü |

### Neuere Features / Dinge, die leicht kaputtgehen können

- `SettingsView` wirkt live auf Toolbar, Quellen, Spalten und Appearance. Bei Änderungen an `ToolbarSettings` immer prüfen, ob `SessionTree.update_toolbar_settings()` weiter korrekt verdrahtet ist.
- `displaycolumns` darf **nicht** `"tree"` enthalten. Die Baumspalte bleibt automatisch links, `displaycolumns` enthält nur echte Datenspalten. Ausgeblendete Spalten dürfen nicht in der sichtbaren Reihenfolge auftauchen.
- `SessionTree.populate()` wird auch durch virtuelle Ordner wie `↺ Zuletzt verwendet` ausgelöst. Beim Doppelklick/Quick-Connect darf das Hinzufügen zu Recent keine bestehenden Ordner einklappen oder als geschlossen speichern.
- Während aktiver Suche werden Trefferordner temporär aufgeklappt. Klicks oder Rebuilds in dieser Suchansicht dürfen `_open_folders` nicht überschreiben; beim Leeren der Suche muss der vorherige Benutzerzustand zurückkommen.
- Notizen dürfen **nie** in WinSCP, FileZilla oder `~/.ssh/config` zurückgeschrieben werden. Nur `notes.json` verwenden.
- FileZilla wird nur gelesen, nie geschrieben. Quelle ist `%APPDATA%\FileZilla\sitemanager.xml`.
- Suchverlauf wird live gespeichert. Änderungen an der Suche betreffen auch `ui_state.json`.
- Tooltip für Notizen hängt am `Treeview`-Hover und ist empfindlich. Bei Änderungen an Motion-/Leave-Events vorsichtig sein.
- Leerer Startscreen/Empty State sitzt als Overlay im `SessionTree` und ruft `on_add_session` auf. Er ist bewusst schlicht und zentriert (`EmptyStateContent.TFrame`, `EmptyStateIcon.TLabel`); keine breite Card wieder einführen.
- Session-Favoriten und Zuletzt verwendet sind virtuelle Ordner aus `actions_ui.build_visible_sessions(app)`. Sie dürfen die Original-Quellen nicht verändern.
- Command Palette (`palette.py`): `FocusOut`/`Unmap`-Handling ist empfindlich. Child-Widget-`Unmap`-Events (z.B. Placeholder wird beim Tippen versteckt) dürfen die Palette nicht schließen; nur Unmap des Palette-Toplevels selbst.
- App-Icon: Wenn das Logo geändert wird, immer `assets/SSH-Logo.svg`, `assets/SSH-Logo.png`, `assets/ssh-manager.png` und `assets/ssh-manager.ico` konsistent halten und `scripts/generate_icon.py` ausführen. Kleine 16/20/24px-Frames separat beurteilen, weil das Titelleisten-Icon sonst schnell unlesbar wird.
- Remote-Runner-Favoriten sind davon getrennt und leben als `remote_command_favorites` im UI-State.
- User-Overrides für importierte Quellen werden in `ui_state.json` unter `session_user_overrides` gespeichert, nicht in WinSCP/FileZilla/SSH Config.
- Portable EXE-Build bleibt additive Packaging-Schicht. Python-Start darf dadurch nicht kaputtgehen.

### Arbeitsweise / Abschluss

- Nach abgeschlossenen Änderungen in diesem Repo automatisch gezielt stagen, sinnvoll committen und `main` nach `origin` pushen, sofern der User nicht ausdrücklich etwas anderes sagt.
- Vor dem Commit mindestens Syntax-Check und relevante Tests laufen lassen. Wenn `tests/test_icon_assets.py` wegen fehlendem `PIL` in der System-Python nicht importiert, das im Abschluss nennen oder mit einer Python-Umgebung prüfen, die Pillow enthält.
- Fallow nur ausführen, wenn ein `package.json` vorhanden ist; aktuell ist das Projekt Python-only.

### Refactor-Learnings (sehr wichtig)

- Keine großen Refactor-Sprünge in einem Zug. Lieber kleine Schnitte und danach sofort validieren.
- Nach jedem Split sofort mindestens `python -m py_compile ssh_manager.py ssh_manager_app/*.py` laufen lassen.
- Wenn UI betroffen ist, danach möglichst auf Windows kurz real testen.
- `from package import *` **nicht** für Namen mit führendem Unterstrich verwenden. Private Konstanten wie `_SSH_CONFIG_DEFAULT_FOLDER` müssen explizit importiert werden.
- Bei Modul-Splits immer prüfen:
  - fehlen Imports im neuen Modul?
  - fehlen danach Methoden in `SSHManagerApp`, auf die UI oder Tree noch zugreifen?
  - wurde wirklich ausführbarer Code extrahiert oder versehentlich nur eine innere Funktion definiert?
- UI-Splits können zu stillen Fehlern führen, bei denen nur eine leere App ohne Traceback erscheint. Dann insbesondere `build_main_ui()` / `grid()` / Callback-Verdrahtung prüfen.
- Nach Split von UI-/Dialog-/Core-Code lieber erst stabilisieren und Imports aufräumen, bevor gleich der nächste große Schnitt folgt.

### Empfohlene weitere Richtung

Wenn weiter refactort wird, zuerst die Testbasis ausbauen und erst danach weitere App-Action-Methoden aus `SSHManagerApp` auslagern. Nicht sofort wieder `__init__` oder den kompletten UI-Startpfad groß umbauen.
