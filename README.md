# SSH-Manager

Öffnet mehrere SSH-Verbindungen gleichzeitig als Tabs in Windows Terminal oder optional in einem persistenten Herdr-Workspace.

Unterstützte Quellen:
- **WinSCP** aus der Registry
- **SSH Config** aus `~/.ssh/config`
- **FileZilla** aus `sitemanager.xml`
- **eigene App-Verbindungen**

## Voraussetzungen

- Windows 10/11
- Python 3.10+ empfohlen; getestet wird aktuell mit Python 3.14.2 auf Windows
- Python-Pakete aus `requirements.txt` (`ttkbootstrap` und `Pillow`)
- [Windows Terminal](https://aka.ms/terminal) installiert
- Git Bash-Profil in Windows Terminal vorhanden (Standard bei Git for Windows)
- optional: [Herdr](https://herdr.dev/) für persistente SSH-Tabs; Windows Terminal bleibt der Standard
- optional: WinSCP mit gespeicherten Sessions
- optional: FileZilla mit gespeicherten Sites

## Starten

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python ssh_manager.py
```

Alternativ mit bereits installierten Abhängigkeiten:

```bat
python ssh_manager.py
```

## Versionierung

Die zentrale App-Version steht in `ssh_manager_app/version.py` und wird im
Fenstertitel sowie oben im App-Header angezeigt. Für jede abgeschlossene Änderung
wird die Patch-Version einmal erhöht:

```bat
python scripts\bump_version.py
```

Das Skript hält dabei die App-Version und die Windows-EXE-Metadaten synchron.
Mit `python scripts\bump_version.py --check` lässt sich die Konsistenz ohne Änderung
prüfen; der Windows-Build führt diese Prüfung automatisch aus.

## Wichtige Features

- portable Windows-EXE mit eigenem Icon baubar; Python-Start bleibt möglich
- mehrere Verbindungen gleichzeitig in **einem** Windows-Terminal-Fenster öffnen
- optional normale SSH-Verbindungen als Tabs im Herdr-Workspace **SSH Manager** öffnen
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
- modernes, kompaktes Light-Design auf Basis von ttkbootstrap; Dark Neutral und Midnight bleiben verfügbar
- responsive Aktionsleiste mit gruppierten Menüs und Überlauf für kleine Fenster
- leerer Startscreen mit „Verbindung hinzufügen“
- Einstellungen direkt in der App bearbeiten
- Einstellungen als JSON exportieren / importieren
- JSON-Dateien der App direkt in VS Code öffnen
- SSH-Tunnel öffnen
- Remote-Befehle auf mehrere Hosts ausführen
- ausgewählte Server parallel per `sudo reboot` neu starten und ihre Rückkehr über SSH sowie optional eine systemd-Unit überwachen
- Python-/Shell-Skripte per SSH ausführen:
  - lokale Skripte vorher nach `/tmp` hochladen und danach wieder löschen
  - vorhandene Skripte per Remote-Pfad starten
  - optionaler Vor-Befehl, Skript-Argumente und Nach-Befehl
  - Ausführungsreihenfolge und getrennte Output-Header im Terminal
  - Verlauf und Favoriten inkl. Name, Notiz, Bearbeiten, Löschen und Anpinnen
- SSH-Keys verteilen oder entfernen

## Server neu starten

Über **Server neu starten…** können einzelne Verbindungen, eine Checkbox-Auswahl oder alle Verbindungen eines Ordners parallel neu gestartet werden. Vor dem Start werden ein gemeinsames sudo-Passwort, optional eine systemd-Unit wie `wildfly.service` und die maximale Wartezeit abgefragt. Das Passwort wird nur für diesen Lauf verwendet, nicht gespeichert und nicht als Prozessargument übergeben; bei passwortlosem sudo kann es leer bleiben.

Die Statusansicht bestätigt zunächst den tatsächlichen Neustart und wartet danach auf eine stabile SSH-Verbindung. Wurde eine systemd-Unit angegeben, erscheint das grüne Häkchen erst, wenn auch diese wieder `active` ist. Fehler und Zeitüberschreitungen werden pro Server angezeigt, ohne die Überwachung der übrigen Server abzubrechen.

## Bedienung

### Integrierte Hilfe

**F1**, **Hilfe → Hilfe öffnen** oder **„Hilfe öffnen“ in der Befehlspalette**
öffnet ein separates, nichtmodales Hilfefenster. Links stehen die Themen, rechts
die Erklärungen; die Suche berücksichtigt Titel und vollständige Hilfetexte.
Die Hilfe erklärt alle Aktionen, Quellen, Einstellungen und die Tastaturbedienung
und zeigt aktuelle sowie voreingestellte App-Kürzel. F1 kann unter
**Einstellungen → Tastenkürzel** geändert werden. **Escape** schließt die Hilfe.
Sie funktioniert offline und benötigt keine zusätzlichen Pakete.

Im Baum aktiviert **Enter** die fokussierte Zeile: Verbindung öffnen oder Ordner
umschalten. **Strg+Enter** verbindet die angehakten Sessions. **Shift+Enter** hat
keine eigene Aktion und aktiviert bei Standardbelegung ebenfalls die fokussierte
Zeile. **Rechts/Links** öffnet/schließt Ordner oder wechselt zu Kind/Elternordner;
**Leertaste** schaltet Checkboxen um. F2 und Entf verwenden eine einzelne
angehakte Session bevorzugt, ansonsten die Kontextzeile.

### Verbindungen bedienen

1. **Sessions auswählen** – Klick auf eine Zeile setzt/entfernt den Haken. Ordner sind auf-/zuklappbar.
2. **Mehrere auf einmal** – Beliebig viele Haken setzen. Rechtsklick auf einen Ordner bietet u. a. Auswahl-, Farb- und Auf-/Zu-Aktionen.
3. **Suche** – Oben im Suchfeld tippen filtert live nach Name und Hostname. Rechts daneben gibt es einen kleinen Verlauf-Button.
4. **Verbinden** – Auf „Verbinden (N ausgewählt)" klicken.
5. **Benutzernamen wählen** – Falls keine Verbindung einen festen Benutzer hat, im Dialog Quickselect nutzen oder eigenen Namen eingeben.
6. Alle gewählten Server öffnen sich als neue Tabs im eingestellten Ziel und landen direkt unter **Zuletzt verwendet**. Standard ist weiterhin ein Windows-Terminal-Fenster; optional nutzt die App den Herdr-Workspace **SSH Manager**.

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
- Ziel für normale SSH-Verbindungen: Windows Terminal (Standard) oder Herdr
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

Die App nutzt neben der Python-Standardbibliothek `ttkbootstrap` und `Pillow` für Themes, Icons und skalierbare Widget-Grafiken. Die festgelegten Laufzeitversionen stehen in `requirements.txt`; Test- und Build-Werkzeuge in `requirements-dev.txt`.

Ein direkter Start mit `python ssh_manager.py` bleibt auch ohne installiertes `ttkbootstrap` möglich. In diesem Fall verwendet die App das integrierte ttk-Theme mit der SSH-Manager-Farbpalette; für das vollständige Design einschließlich Bootstrap-Icons wird die Projektumgebung aus den Installationsschritten oben empfohlen.

Eine isolierte Vorschau mit Beispieldaten lässt sich ohne Zugriff auf Registry oder App-Daten öffnen:

```bat
.venv\Scripts\python scripts\ui_preview.py
```

## Portable Windows-EXE bauen

Die Python-Variante bleibt weiterhin nutzbar:

```bat
python ssh_manager.py
```

Für eine richtige Windows-App als portable Einzel-EXE:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Das Script nutzt die aktuell aktive Python-Version, installiert die festgelegten Build-Abhängigkeiten und erzeugt:

```text
dist\SSH Manager.exe
```

Die EXE läuft ohne Terminalfenster, nutzt das App-Icon aus `assets/ssh-manager.ico` und speichert Daten weiterhin unter `%APPDATA%\SSH-Manager\`.
Die Paket-Metadaten einschließlich der Lizenzdateien von ttkbootstrap und Pillow werden in die portable Anwendung aufgenommen.
