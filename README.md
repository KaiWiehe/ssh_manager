# SSH-Manager

Öffnet mehrere SSH-Verbindungen gleichzeitig als Tabs in Windows Terminal.

Unterstützte Quellen:
- **WinSCP** aus der Registry
- **SSH Config** aus `~/.ssh/config`
- **FileZilla** aus `sitemanager.xml`
- **eigene App-Verbindungen**

## Voraussetzungen

- Windows 10/11
- Python 3.10+ empfohlen; getestet wird aktuell mit Python 3.14.2 auf Windows
- [Windows Terminal](https://aka.ms/terminal) installiert
- Git Bash-Profil in Windows Terminal vorhanden (Standard bei Git for Windows)
- optional: WinSCP mit gespeicherten Sessions
- optional: FileZilla mit gespeicherten Sites

## Starten

```bat
python ssh_manager.py
```

## Wichtige Features

- portable Windows-EXE mit eigenem Icon baubar; Python-Start bleibt möglich
- mehrere Verbindungen gleichzeitig in **einem** Windows-Terminal-Fenster öffnen
- Sessions aus mehreren Quellen zusammen anzeigen
- Quellen in der Hauptansicht ein- und ausblenden
- Ordner auf- und zuklappen, auch rekursiv per Rechtsklick
- Live-Suche mit Suchverlauf
- Favoriten und „Zuletzt verwendet“-Bereich
- Session-Farben
- Session-Notizen mit eigener Spalte und Tooltip
- fester Benutzer pro Verbindung, Bulk-Benutzer setzen/entfernen und Quickselect-Benutzer
- Toolbar und sichtbare Spalten getrennt konfigurierbar
- Spaltenreihenfolge per Drag & Drop anpassbar
- Themes inkl. Dark Mode und Akzentfarben
- leerer Startscreen mit „Verbindung hinzufügen“
- Einstellungen direkt in der App bearbeiten
- Einstellungen als JSON exportieren / importieren
- JSON-Dateien der App direkt in VS Code öffnen
- SSH-Tunnel öffnen
- Remote-Befehle auf mehrere Hosts ausführen
- Python-/Shell-Skripte per SSH ausführen:
  - lokale Skripte vorher nach `/tmp` hochladen und danach wieder löschen
  - vorhandene Skripte per Remote-Pfad starten
  - optionaler Vor-Befehl, Skript-Argumente und Nach-Befehl
  - Ausführungsreihenfolge und getrennte Output-Header im Terminal
  - Verlauf und Favoriten inkl. Name, Notiz, Bearbeiten, Löschen und Anpinnen
- SSH-Keys verteilen oder entfernen

## Bedienung

1. **Sessions auswählen** – Klick auf eine Zeile setzt/entfernt den Haken. Ordner sind auf-/zuklappbar.
2. **Mehrere auf einmal** – Beliebig viele Haken setzen. Rechtsklick auf einen Ordner bietet u. a. Auswahl-, Farb- und Auf-/Zu-Aktionen.
3. **Suche** – Oben im Suchfeld tippen filtert live nach Name und Hostname. Rechts daneben gibt es einen kleinen Verlauf-Button.
4. **Verbinden** – Auf „Verbinden (N ausgewählt)" klicken.
5. **Benutzernamen wählen** – Falls keine Verbindung einen festen Benutzer hat, im Dialog Quickselect nutzen oder eigenen Namen eingeben.
6. Alle gewählten Server öffnen sich als neue Tabs **in einem Windows Terminal Fenster** und landen direkt unter **Zuletzt verwendet**.

## Remote-Befehle und Skripte

Über **Remote-Befehl ausführen** kann eine Auswahl von Hosts mit einer Befehlskette gestartet werden. Für die komplette Befehlskette wird ein Benutzer verwendet.

Modi:

- **Nur Remote-Befehl** – führt den eingegebenen Befehl direkt per SSH aus. Keine weiteren Skript-Einstellungen nötig.
- **Lokales Skript hochladen** – wählt eine lokale `.py`-/`.sh`-/beliebige Datei, lädt sie per `scp` nach `/tmp`, führt sie mit dem gewählten Interpreter und optionalen Argumenten aus und löscht sie anschließend wieder.
- **Skript liegt auf Server** – führt ein bereits vorhandenes Skript über seinen Remote-Pfad aus.

Für Skript-Modi kann optional ein **Vor-Befehl** und **Nach-Befehl** angegeben werden, z. B. `cd /opt/app`, Service-Stop/Start oder Statusausgaben. Im Bestätigungsdialog und oben im Terminal wird die genaue Reihenfolge angezeigt. Während der Ausführung trennt die App den Output mit klaren Headern, z. B. `Output vom Vor-Befehl`, `Output vom Skript`, `Output vom Nach-Befehl`.

Favoriten speichern komplette Runbooks inkl. Modus, Pfaden, Interpreter, Argumenten, Vor-/Nach-Befehl, Name und Notiz. Favoriten können angelegt, bearbeitet, gelöscht und oben angepinnt werden. Zuletzt verwendete Ausführungen bleiben für schnelles Wiederholen verfügbar.

## Einstellungen

Die Einstellungen liegen direkt im Hauptfenster und enthalten u. a.:

- Quick-User und Standardbenutzer
- Import-Optionen für WinSCP-/FileZilla-Benutzer
- sichtbare Toolbar-Buttons
- sichtbare Quellen in der Hauptansicht inkl. Favoriten und Zuletzt verwendet
- sichtbare Spalten (`Benutzer`, `Hostname`, `Port`, `Notizen`)
- Reihenfolge der sichtbaren Spalten per Drag & Drop, Baumspalte `Name` bleibt immer links
- Design/Theme, Akzentfarbe, Schriftarten und Tree-Zeilenhöhe
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

## Abhängigkeiten

Die App selbst nutzt nur Python-Standardbibliothek (`tkinter`, `winreg`, `subprocess`, `xml.etree.ElementTree` usw.).
Für Tests brauchst du `pytest`. Für den EXE-Build installiert das Build-Script bei Bedarf `PyInstaller`.

## Portable Windows-EXE bauen

Die Python-Variante bleibt weiterhin nutzbar:

```bat
python ssh_manager.py
```

Für eine richtige Windows-App als portable Einzel-EXE:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Das Script nutzt die aktuell aktive Python-Version, installiert bei Bedarf PyInstaller und erzeugt:

```text
dist\SSH Manager.exe
```

Die EXE läuft ohne Terminalfenster, nutzt das App-Icon aus `assets/ssh-manager.ico` und speichert Daten weiterhin unter `%APPDATA%\SSH-Manager\`.
