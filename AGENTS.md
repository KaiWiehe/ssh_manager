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
python -m py_compile ssh_manager.py
```

Keine externen Abhängigkeiten – nur Python-Standardbibliothek (`tkinter`, `winreg`, `subprocess`, `pathlib`, `socket`, `threading`).  
Aus tkinter genutzte Module: `tk`, `ttk`, `messagebox`, `simpledialog`.

## Architektur

Die gesamte App lebt in einer einzigen Datei: `ssh_manager.py`.

### Datenfluss

```
Registry (WinSCP)  ──┐
~/.ssh/config      ──┼──► SSHManagerApp._rebuild_sessions() ──► SessionTree.populate()
app_sessions.json  ──┘
```

`SSHManagerApp` lädt beim Start alle drei Quellen, mischt sie und gibt sie an `SessionTree` weiter. Der "SSH Config"-Ordner wird immer oben sortiert.

### Schichten

**Reine Logik (testbar ohne GUI/Registry):**
- `Session` (dataclass) – Datenmodell
- `parse_session_key()` – URL-Decoding von WinSCP-Registry-Keys
- `build_wt_command()` – erzeugt den `wt.exe`-Befehl für SSH-Verbindungen
- `build_ssh_copy_id_command()` – erzeugt den Befehl für `ssh-copy-id`
- `build_ssh_remove_key_command()` – erzeugt den Befehl zum Entfernen eines Keys aus `authorized_keys`
- `build_ssh_tunnel_command()` – erzeugt den Start für SSH Local Port Forwarding (`-N -L`)
- `build_remote_command_wt_command()` – erzeugt WT-Tabs für Remote-Befehle auf einem oder mehreren Hosts
- `_write_temp_bash_script()` – schreibt temporäre lokale Bash-Skripte für robuste WT/Git-Bash-Starts
- `check_host_reachable()` – TCP-Verbindungstest (socket, kein SSH-Handshake)
- `_find_git_bash()` – findet Git Bash (nicht WSL-Bash)
- `_find_winscp()` – findet WinSCP.exe (`%LOCALAPPDATA%`, Program Files, PATH)
- `_load_ui_state()` / `_save_ui_state()` – JSON-Persistenz in `%APPDATA%\SSH-Manager\`

**GUI-Klassen:**
- `SessionTree(ttk.Frame)` – der Haupt-Treeview mit Checkboxen, Farben, Kontextmenüs. Kommuniziert mit der App ausschließlich über Callback-Parameter (kein direkter App-Zugriff).
- `SSHManagerApp(tk.Tk)` – Hauptfenster, verdrahtet alle Callbacks, besitzt den App-Zustand.
- Dialog-Klassen: `UserDialog`, `SessionEditDialog`, `MoveFolderDialog`, `SshCopyIdDialog`, `SshRemoveKeyDialog`, `SshConfigInspectDialog`, `SshTunnelDialog`, `RemoteCommandDialog`, `RemoteCommandConfirmDialog`

**Datenquellen:**
- `RegistryReader` – liest WinSCP-Sessions aus `HKCU\Software\Martin Prikryl\WinSCP 2\Sessions`
- `_load_ssh_config_sessions()` – parst `~/.ssh/config` manuell (kein Parser-Import)
- `app_sessions.json` – eigene Sessions (source=`app`) und SSH-Alias-Kopien (source=`ssh_alias`)

### Session-Typen (`source`-Feld)

| source | Herkunft | SSH-Befehl |
|---|---|---|
| `winscp` | Registry | `ssh USER@HOST` |
| `app` | app_sessions.json | `ssh USER@HOST` |
| `ssh_config` | ~/.ssh/config (live) | `ssh ALIAS` |
| `ssh_alias` | app_sessions.json (Kopie) | `ssh ALIAS` |

`ssh_config`- und `ssh_alias`-Sessions ignorieren den User-Dialog (`is_ssh_config_session = True`).

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

`%APPDATA%\SSH-Manager\ui_state.json` speichert geöffnete Ordner und Session-Farben (Hex-Strings).  
`%APPDATA%\SSH-Manager\app_sessions.json` speichert eigene Sessions und SSH-Alias-Kopien.

### Konfigurierbare Konstanten (oben in der Datei)

- `QUICK_USERS` – Schnellauswahl-Buttons in User-Dialogen
- `DEFAULT_USER` – vorausgewählter Benutzername
- `PALETTE` – 8 Einträge `(Name, "#rrggbb")` für die Farbauswahl
- `_SSH_CONFIG_DEFAULT_FOLDER` – Anzeigename des SSH-Config-Ordners (`"SSH Config"`)

### SessionTree-Callbacks (Übersicht)

| Callback | Signatur | Beschreibung |
|---|---|---|
| `on_selection_changed` | `(count: int)` | Checkbox-Änderung |
| `on_quick_connect` | `(Session)` | Doppelklick / Verbindung öffnen |
| `on_edit_session` | `(Session)` | Bearbeiten-Dialog |
| `on_delete_session` | `(Session)` | Session löschen |
| `on_delete_folder` | `(list[Session], str)` | Ordner löschen |
| `on_rename_folder` | `(str)` | Ordner umbenennen (folder_key) |
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
