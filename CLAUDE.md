# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

Keine externen Abhängigkeiten – nur Python-Standardbibliothek (`tkinter`, `winreg`, `subprocess`, `pathlib`).

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
- `_find_git_bash()` – findet Git Bash (nicht WSL-Bash)
- `_load_ui_state()` / `_save_ui_state()` – JSON-Persistenz in `%APPDATA%\SSH-Manager\`

**GUI-Klassen:**
- `SessionTree(ttk.Frame)` – der Haupt-Treeview mit Checkboxen, Farben, Kontextmenüs. Kommuniziert mit der App ausschließlich über Callback-Parameter (kein direkter App-Zugriff).
- `SSHManagerApp(tk.Tk)` – Hauptfenster, verdrahtet alle Callbacks, besitzt den App-Zustand.
- Dialog-Klassen: `UserDialog`, `SessionEditDialog`, `MoveSessionDialog`, `SshCopyIdDialog`, `SshRemoveKeyDialog`, `SshConfigInspectDialog`

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

### Windows Terminal / Quoting-Regeln

Kritisch für alle `build_*_command()`-Funktionen:

- WT parst `;` als eigenen Subcommand-Separator – auch innerhalb von `bash -c "..."`. Daher `&&`/`||` statt `;` verwenden.
- `~` muss **unquoted** bleiben – in single oder double quotes findet keine Tilde-Expansion statt.
- `bash` aus dem System-PATH ist unter Windows mit WSL die WSL-Bash, nicht Git Bash. Immer `_find_git_bash()` verwenden.
- Nested double quotes in `bash -c "..."` zerschießen den Befehl. Für Remote-SSH-Befehle single quotes verwenden: `bash -c "ssh host 'remote cmd'"`.
- `subprocess.Popen(cmd, shell=True)` ist nötig (nicht `shell=False`), da `wt.exe` und `code` keine direkten Binaries sind.

### Persistenz

`%APPDATA%\SSH-Manager\ui_state.json` speichert geöffnete Ordner und Session-Farben (Hex-Strings).  
`%APPDATA%\SSH-Manager\app_sessions.json` speichert eigene Sessions und SSH-Alias-Kopien.

### Konfigurierbare Konstanten (oben in der Datei)

- `QUICK_USERS` – Schnellauswahl-Buttons in User-Dialogen
- `DEFAULT_USER` – vorausgewählter Benutzername
- `PALETTE` – 8 Einträge `(Name, "#rrggbb")` für die Farbauswahl
- `_SSH_CONFIG_DEFAULT_FOLDER` – Anzeigename des SSH-Config-Ordners (`"SSH Config"`)
