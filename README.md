# SSH-Manager

Öffnet mehrere SSH-Verbindungen gleichzeitig als Tabs in Windows Terminal.

Unterstützte Quellen:
- **WinSCP** aus der Registry
- **SSH Config** aus `~/.ssh/config`
- **FileZilla** aus `sitemanager.xml`
- **eigene App-Verbindungen**

## Voraussetzungen

- Windows 10/11
- Python 3.8+
- [Windows Terminal](https://aka.ms/terminal) installiert
- Git Bash-Profil in Windows Terminal vorhanden (Standard bei Git for Windows)
- optional: WinSCP mit gespeicherten Sessions
- optional: FileZilla mit gespeicherten Sites

## Starten

```bat
python ssh_manager.py
```

## Wichtige Features

- mehrere Verbindungen gleichzeitig in **einem** Windows-Terminal-Fenster öffnen
- Sessions aus mehreren Quellen zusammen anzeigen
- Quellen in der Hauptansicht ein- und ausblenden
- Ordner auf- und zuklappen, auch rekursiv per Rechtsklick
- Live-Suche mit Suchverlauf
- Session-Farben
- Session-Notizen mit eigener Spalte und Tooltip
- Toolbar und sichtbare Spalten konfigurierbar
- Spaltenreihenfolge anpassbar
- Einstellungen direkt in der App bearbeiten
- Einstellungen als JSON exportieren / importieren
- JSON-Dateien der App direkt in VS Code öffnen
- SSH-Tunnel öffnen
- Remote-Befehle auf mehrere Hosts ausführen
- SSH-Keys verteilen oder entfernen

## Bedienung

1. **Sessions auswählen** – Klick auf eine Zeile setzt/entfernt den Haken. Ordner sind auf-/zuklappbar.
2. **Mehrere auf einmal** – Beliebig viele Haken setzen. Rechtsklick auf einen Ordner bietet u. a. Auswahl-, Farb- und Auf-/Zu-Aktionen.
3. **Suche** – Oben im Suchfeld tippen filtert live nach Name und Hostname. Rechts daneben gibt es einen kleinen Verlauf-Button.
4. **Verbinden** – Auf „Verbinden (N ausgewählt)" klicken.
5. **Benutzernamen wählen** – Im Dialog einen der Schnellauswahl-Buttons klicken oder eigenen Namen eingeben, dann OK.
6. Alle gewählten Server öffnen sich als neue Tabs **in einem Windows Terminal Fenster**.

## Einstellungen

Die Einstellungen liegen direkt im Hauptfenster und enthalten u. a.:

- Quick-User und Standardbenutzer
- sichtbare Toolbar-Buttons
- sichtbare Quellen in der Hauptansicht
- sichtbare Spalten (`Hostname`, `Port`, `Notizen`)
- Reihenfolge der Spalten, Default: `Name | Notiz | Hostname | Port`
- Windows-Terminal-Optik (Profilname, Farben, Titel)
- Export / Import der Einstellungen
- Reset von Einstellungen sowie Ansichtszustand

## Quellen

### WinSCP

Die App liest WinSCP direkt aus der Registry:

```
HKEY_CURRENT_USER\Software\Martin Prikryl\WinSCP 2\Sessions
```

### SSH Config

SSH-Aliases werden aus folgender Datei gelesen:

```text
~/.ssh/config
```

### FileZilla

FileZilla-Sites werden aus `sitemanager.xml` gelesen, typischerweise hier:

```text
%APPDATA%\FileZilla\sitemanager.xml
```

## Notizen

Session-Notizen werden **nur app-intern** gespeichert.
Die App schreibt **nichts** zurück nach WinSCP, FileZilla oder `~/.ssh/config`.

## App-Daten

Die App speichert ihre eigenen Dateien unter:

```text
%APPDATA%\SSH-Manager\
```

Dort liegen z. B.:
- `settings.json`
- `ui_state.json`
- `app_sessions.json`
- `notes.json`

## Kein pip erforderlich

Nur Python-Standardbibliothek (`tkinter`, `winreg`, `subprocess`, `xml.etree.ElementTree` usw.).
