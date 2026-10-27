# SSH-Manager

Öffnet mehrere SSH-Verbindungen gleichzeitig als Tabs in Windows Terminal oder optional in einem persistenten Herdr-Workspace.

Unterstützte Quellen:
- **WinSCP** aus der Registry
- **SSH Config** aus `~/.ssh/config`
- **FileZilla** aus `sitemanager.xml`
- **eigene App-Verbindungen**

## Voraussetzungen

- Windows 10/11
- Für Quellcode-Start und EXE-Build: Python mit `venv`/`pip`, hier mit Python 3.14 (64-Bit) geprüft, sowie die Pakete aus `requirements.txt`
- Für fertige EXEs: kein separat installiertes Python und keine Python-Pakete nötig
- [Windows Terminal](https://aka.ms/terminal) installiert
- Git Bash-Profil in Windows Terminal vorhanden (Standard bei Git for Windows)
- optional: [Herdr](https://herdr.dev/) für persistente SSH-Tabs; Windows Terminal bleibt der Standard
- optional: WinSCP mit gespeicherten Sessions
- optional: FileZilla mit gespeicherten Sites

## Vom Git-Download zur fertigen Installation

Ein Klonen oder ZIP-Download liefert den **Quellcode**. Dabei werden keine EXEs
gebaut und kein `sshm`-Befehl eingerichtet. Du kannst den Quellcode mit Python
starten oder daraus die beiden portablen Windows-Programme bauen.

### 1. Werkzeuge und Repository vorbereiten

Für einen neuen Windows-x64-Build [Python für Windows](https://www.python.org/downloads/windows/)
in der **64-Bit-Ausführung** installieren; hier ist die Python-3.14-Reihe geprüft.
Für `git clone` wird [Git für Windows](https://git-scm.com/downloads/win) benötigt;
es bringt Git Bash und einen SSH-Client mit. Die folgenden Befehle in **PowerShell**
ausführen, nicht in der Python-Eingabeaufforderung (`>>>`).

```powershell
git clone https://github.com/KaiWiehe/ssh_manager.git SSH-Manager
Set-Location SSH-Manager
python --version
python -m venv .venv
```

Bei einem ZIP-Download stattdessen das ZIP vollständig entpacken und PowerShell
im entpackten Repository-Ordner öffnen. Dort müssen `ssh_manager.py`, `sshm.py`,
`requirements.txt` und der Ordner `scripts` liegen. Die letzten beiden Befehle
oben auch bei einem ZIP-Download ausführen. Ist nur der Python-Launcher `py`
verfügbar, kann `py -3.14 -m venv .venv` die Umgebung anlegen. Die Umgebung muss
nicht aktiviert werden; die Befehle unten verwenden ihren Interpreter direkt.

### 2. Beide EXEs bauen

```powershell
.\.venv\Scripts\python.exe -c "import struct; print(struct.calcsize('P') * 8)"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Die erste Zeile muss für den beschriebenen x64-Build **64** ausgeben. Der Build
läuft unter Windows und übernimmt die Architektur des verwendeten Python;
andere Architekturen sind damit nicht automatisch geprüft. Das Buildskript
verwendet bevorzugt `.venv\Scripts\python.exe`, prüft die Versionsmetadaten und
installiert die festgelegten Laufzeit-/Build-Abhängigkeiten aus
`requirements-dev.txt` einschließlich `requirements.txt`. Eine manuelle
PyInstaller-Installation oder Versionsanhebung ist zum normalen Bauen nicht nötig.

Nach erfolgreichem Build liegen **zwei** eigenständige Programme vor:

| Datei | Zweck und Start |
|---|---|
| `dist\SSH Manager.exe` | Grafische App; per Doppelklick öffnen |
| `dist\sshm.exe` | Terminalsuche; in PowerShell/Git Bash aufrufen |

Beide enthalten ihre Python-Laufzeit. Externe Werkzeuge wie SSH, Windows Terminal
und Git Bash für die jeweiligen Verbindungsaktionen müssen weiterhin vorhanden
sein. Der Build ersetzt `build` und `dist`; eigene Dateien dort nicht ablegen.
Die Benutzerdaten unter `%APPDATA%\SSH-Manager` werden dadurch nicht ersetzt.

### 3. Grafische App portabel nutzen oder ablegen

Direkt aus dem Build starten:

```powershell
& '.\dist\SSH Manager.exe'
```

Oder die EXE in einen festen persönlichen Programmordner kopieren, damit sie
unabhängig vom Repository und dessen nächsten Build erhalten bleibt:

```powershell
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\SSH-Manager'
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Copy-Item -LiteralPath '.\dist\SSH Manager.exe' -Destination $installDir -Force
& (Join-Path $installDir 'SSH Manager.exe')
```

Das ist eine portable Ablage ohne klassischen Setup-Assistenten. Bei Bedarf
über Windows eine Verknüpfung auf diese EXE erstellen. Einstellungen, eigene
Verbindungen und Notizen bleiben unter `%APPDATA%\SSH-Manager`, nicht neben der EXE.

### 4. CLI als Befehl `sshm` einrichten

Nach dem Build **im Repository-Ordner** ausführen:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_cli.ps1 -AddToPath
```

Das Skript kopiert **nur die CLI** nach
`%LOCALAPPDATA%\Programs\SSH-Manager\sshm.exe` und ergänzt diesen Ordner im
persönlichen Benutzer-PATH. `sshm` ist die EXE, kein Alias. Ohne `-AddToPath`
wird nur die EXE kopiert. Die GUI-EXE wird durch dieses Skript nicht installiert.
Shell-Profile und Maschinen-PATH bleiben unverändert; Administratorrechte sind
für die beschriebene persönliche Ablage nicht erforderlich.

Danach ein neues Terminal öffnen. Bereits laufende Terminalhosts oder persistente
Herdr-Sitzungen haben möglicherweise noch den alten PATH; diese bei Bedarf
nach Ende laufender Arbeiten vollständig neu starten. In PowerShell prüfen:

```powershell
Get-Command sshm -All
sshm --version
sshm
```

In Git Bash zeigt `command -v sshm` den gefundenen Starter. Profilbasierte Aliase
oder Funktionen können `sshm` überschatten; der mit `-NoProfile` gestartete Installer
kennt diese Definitionen der aufrufenden Shell nicht. Deshalb nach der Installation
prüfen, ob tatsächlich die gewünschte EXE gefunden wird. Sofortiger Aufruf ohne
PATH-Aktualisierung in PowerShell:

```powershell
& "$env:LOCALAPPDATA\Programs\SSH-Manager\sshm.exe"
```

### Alternative: direkt mit Python starten

Wenn du keine EXEs bauen möchtest, genügen die Laufzeit-Abhängigkeiten:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ssh_manager.py
# CLI stattdessen in einem Terminal starten:
.\.venv\Scripts\python.exe sshm.py web
```

Der Python-Start erzeugt keine EXE und richtet keinen kurzen `sshm`-Befehl ein.

### Nach `git pull` aktualisieren

Die grafische App schließen und laufende CLI-/SSH-Aufträge beenden, bevor ihre
EXEs ersetzt werden. Im vorhandenen Repository mit bestehender `.venv`:

```powershell
git pull --ff-only
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_cli.ps1 -AddToPath
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\SSH-Manager'
Copy-Item -LiteralPath '.\dist\SSH Manager.exe' -Destination $installDir -Force
```

**Jeden Schritt nur fortsetzen, wenn der vorherige erfolgreich war.** Bei lokalen
Git-Änderungen den Pull-Konflikt zuerst klären. `git pull` allein aktualisiert weder
die gebauten noch die installierten EXEs. Das Buildskript installiert auch
geänderte Abhängigkeiten; anschließend die Programme neu starten. Die installierte
CLI-Version kontrollierst du mit `sshm --version`, die grafische App zeigt ihre
Version im Fenster. Installation und Update überschreiben keine App-Benutzerdaten.

### Häufige Einrichtungsprobleme

- **`python` fehlt oder öffnet den Store:** Python-Installation/PATH prüfen;
  falls vorhanden, `py -3.14 -m venv .venv` verwenden.
- **`dist\sshm.exe` fehlt:** Erst den vollständigen Build erfolgreich abschließen.
- **`sshm` wird nicht gefunden:** Benutzer-PATH und gefundenen Pfad prüfen;
  bestehenden Terminalhost gegebenenfalls vollständig neu starten oder den
  vollständigen EXE-Pfad verwenden. Bei einer Namenskollision bricht das
  Installationsskript ab, statt ein anderes gefundenes Programm zu ersetzen.
- **SSH wird nicht gefunden:** `ssh -V` und in PowerShell `Get-Command ssh`, in
  Git Bash `command -v ssh` prüfen. Python ist in der EXE enthalten, SSH nicht.
- **Kopieren scheitert:** Laufende Instanz der zu ersetzenden EXE zuerst schließen.
- **Build schlägt fehl:** Den ersten Fehler beheben und danach neu bauen; eine
  alte EXE ist kein Nachweis eines erfolgreichen neuen Builds.

Diese Anleitung ist auch offline in der App über **F1 → Installation und EXE-Build**,
**CLI: sshm einrichten und verwenden** und **Aktualisierung und Einrichtungsprobleme**
verfügbar. Die Hilfe führt die angezeigten Befehle nicht selbst aus.

## CLI: Verbindungen im aktuellen Terminal öffnen

Der portable Build erzeugt zusätzlich **`dist\sshm.exe`**. Er benötigt kein
installiertes Python und öffnet SSH im aktuellen Tab/Pane. PowerShell und Git Bash
sind die vorgesehenen Shells, in Windows Terminal oder Herdr. Die CLI verwendet
dieselben App-Daten wie die GUI unter `%APPDATA%\SSH-Manager`.

```powershell
# Portable Verwendung
.\dist\sshm.exe
.\dist\sshm.exe web produktion

# Optional: in den persönlichen Programmordner kopieren und Benutzer-PATH ergänzen
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_cli.ps1 -AddToPath
# Danach ein neues Terminal öffnen (bestehenden Terminalhost ggf. vollständig neu starten):
sshm
sshm web
```

Ohne `-AddToPath` kopiert das Installationsskript nur die EXE. Es verändert weder
Shell-Profile noch den Maschinen-PATH und bricht bei einer erkannten Namenskollision
ab. Portable Nutzung in Git Bash: `./dist/sshm.exe web`. Für die Entwicklung:
`.venv\Scripts\python.exe sshm.py web`.

Die Suche berücksichtigt Name, ursprünglichen Ordnerpfad, Host/IP, Benutzer,
Quelle und Notizen. Alle vier Quellen werden durchsucht, auch wenn sie in der GUI
ausgeblendet sind. Treffer erscheinen im gefilterten Originalbaum mit sichtbaren
Elternordnern. Rechts stehen Verbindungsdetails und die vollständige Notiz; in
schmalen Fenstern darunter. Gleichnamige Datensätze behalten ihre eigene Identität.

| Taste | Aktion |
|---|---|
| Tippen im Suchfeld | Fuzzy-Suche; mehrere Wörter dürfen verschiedene Felder treffen |
| ↑ / ↓ im Suchfeld oder Baum | Markierte Baumzeile wechseln |
| Tab / Umschalt+Tab | Zwischen Suchfeld, Baum und Details wechseln |
| ← / → im Baum | Ordner ein-/ausklappen bzw. zu Eltern/Kindern wechseln |
| Enter im Suchfeld oder Baum | Markierte Verbindung starten; Ordner nur umklappen |
| ↑ / ↓, Bild ↑ / ↓ in Details | Vollständige Notizen lesen/scrollen |
| F2 | Quellen, Ordner einschließlich Unterordnern und Ansicht auswählen |
| F3 | Alle Filter zurücksetzen |
| Esc | Filterdialog schließen, sonst Suche beenden |
| Strg+C | Suche abbrechen; während SSH erhält SSH die Eingabe |

Im Filterdialog mit Tab zwischen Bereichen wechseln, mit Pfeilen wählen und mit
Leertaste Quellen an-/abwählen. Quellen wirken untereinander als ODER; Quellen,
Ordner und Ansicht (`Alle`, `Favoriten`, `Zuletzt verwendet`) gemeinsam als UND.
Bei aktiver Suche bleiben Trefferordner automatisch offen; das verändert keinen
gespeicherten GUI-Ordnerzustand. Die GUI bleibt für das Bearbeiten von Favoriten
zuständig. CLI-Starts aktualisieren den gemeinsamen Verlauf (maximal zehn).

Die CLI verwendet die erste ausführbare `ssh`-Datei im geerbten PATH und erhält
deren SSH-Agent-Umgebung. PowerShell und Git Bash können unterschiedliche Clients
verwenden. SSH-Aliase behalten die Konfiguration des Clients, einschließlich
ProxyJump/Include; im Detailbereich werden unaufgelöste Angaben entsprechend
gekennzeichnet. Andere Verbindungen verwenden den festen Benutzer, dann den
konfigurierten Standard. Fehlt dieser, erfolgt eine Terminalabfrage mit
Quick-User-Vervollständigung per Tab; Esc/Strg+C brechen ab.

Bei Git-/MSYS-SSH stellt ein konstanter Bash-`exec`-Aufruf den Vordergrundprozess
für korrekte Terminaleingaben einschließlich Strg+C her. Der gewählte SSH-Client
bleibt derselbe; Verbindungswerte werden als separate Argumente übergeben.

Nach SSH-Ende kehrst du zur Shell zurück. Der SSH-Exitcode wird weitergegeben;
Auswahlabbruch liefert 130, fehlendes interaktives Terminal 2, Lade-/Startfehler 1.
Ein Verlaufseintrag belegt den lokalen Start, keine erfolgreiche Remote-Anmeldung.
Es erfolgen keine automatischen Netzwerkprüfungen beim Suchen. Externe Quellen,
Schlüssel und SSH-Konfigurationen werden nicht geschrieben.

Zur Entfernung die installierte `sshm.exe` löschen und den hinzugefügten Eintrag
`%LOCALAPPDATA%\Programs\SSH-Manager` aus dem persönlichen PATH entfernen; App-Daten
bleiben erhalten. Der normale GUI-Start über `ssh_manager.py` bzw. `SSH Manager.exe`
ist weiterhin verfügbar.

Optionale lokale SSH-/ConPTY-Prüfung der paketierten EXE:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-terminal-test.txt
.venv\Scripts\python.exe scripts\verify_cli_terminal.py
```

Sie verwendet eine lokale Testgegenstelle und isolierte SSH-Dateien. Ergebnisse
stehen unter `.tmp/terminal-qa`. Die ConPTY-Prüfung ersetzt keine zusätzliche
Bedienabnahme direkt in Windows Terminal und Herdr.

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

- **Massen-Neustarts…**: benannte Vorlagen mit direkt editierbaren Benutzern und Service-Sollzuständen je Server, lesender Dienstauswahl, Startvorschau und Fehlerstrategie
- Neustartergebnisse vollständig als Tabelle kopieren; mehrere Zeilen oder einzelne Textausschnitte auswählen, mit Zeilen-Hover und vollständigen Details
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

Standardmäßig werden alle ausgewählten Hosts gleichzeitig gestartet. Mit **Gleichzeitige Neustarts begrenzen** beginnt der nächste Host erst, wenn die Prüfung eines laufenden Hosts endet. Stoppen verhindert noch wartende Neustarts; bereits ausgelöste laufen weiter. Bei mehr als fünf Hosts wird die Anzahl zusätzlich bestätigt.

## Zertifikatsrechte, Pfade und CSV-Export

Bei **Dateien verteilen** wählt **Dateibesitzer und Rechte…** einen Dienstbenutzer für alle Hosts oder je Host, mit konfigurierten Quick-Users und freier Eingabe. Der Dateibesitzer ist unabhängig vom SSH-Anmeldebenutzer; seine primäre Gruppe wird verwendet. Neue Dateien bekommen standardmäßig **0600**. Je Datei sind auch Gruppenrechte oder öffentliche Leserechte wählbar; **0644 nur für öffentliche Zertifikate** verwenden. Vorhandene Besitzer/Rechte bleiben erhalten, außer die Änderung wird ausdrücklich aktiviert. Die Installation bereitet Metadaten vor und ersetzt die Zieldatei atomar; bestehende Symlinks bleiben erhalten.

Zertifikat-Such- und Zielpfade werden normalisiert; Steuerzeichen und `..`-Segmente sind unzulässig. Breite Pfade wie `/etc` bleiben nach einer Warnung erlaubt. Die reine Zertifikatssuche arbeitet standardmäßig mit acht parallelen Hosts; die Begrenzung ist je Lauf änderbar oder abschaltbar. Übertragungs- und Neustartformulare sind bei kleinen Fenstern scrollbar, die Aktionsbuttons bleiben sichtbar.

Der CSV-Export ist standardmäßig **Excel-sicher**: Mögliche Formeln in Zellen und Ordnerüberschriften erhalten ein vorangestelltes Apostroph. Für unveränderte Rohdaten kann die Option deaktiviert werden; beim Öffnen solcher Dateien in Excel können Formeln ausgeführt werden. XLSX verwendet Textzellen.

Beim Umbenennen oder Verschieben in einen vorhandenen Ordner muss das Zusammenführen bestätigt werden. Ein einzelner neuer Ordnername darf keinen `/` enthalten; beim Verschieben bleiben vollständige Ordnerpfade möglich.

## Bedienung

### Integrierte Hilfe

**F1**, **Hilfe → Hilfe öffnen** oder **„Hilfe öffnen“ in der Befehlspalette**
öffnet ein separates, nichtmodales Hilfefenster. Links stehen die Themen, rechts
die Erklärungen; die Suche berücksichtigt Titel und vollständige Hilfetexte.
**Was passiert hier?** in einem Aufgabendialog öffnet direkt dessen Hilfethema.
Bei modalen Dialogen wird nach dem Schließen der Hilfe die Bedienung an den
Dialog zurückgegeben. Gesperrte Aktionen nennen ihre Voraussetzungen.

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

**Runbook-Bibliothek…** trennt Anlegen, Inhalt, Name/Notiz, Parameter, Anpinnen
und Löschen von der Ausführung. Parameterformulare prüfen Text, Zahlen, Ports,
absolute Pfade und Auswahllisten. Das Runbook liest sie über
`"$RUNBOOK_NAME"`; Geheimwerte werden erst für den Lauf eingegeben und weder
in Favoriten noch im Verlauf gespeichert.

Das Aktionen-Menü bietet **Remote-Befehl ausführen**, **Lokales Skript ausführen** und **Serverskript ausführen** als getrennte Aufgaben. Die Häkchen-Auswahl bestimmt die Zielhosts. Für die komplette Befehlskette wird ein Benutzer verwendet; Vor-/Nach-Befehle erscheinen unter **Erweiterter Ablauf**.

Modi:

- **Nur Remote-Befehl** – führt den eingegebenen Befehl direkt per SSH aus. Keine weiteren Skript-Einstellungen nötig.
- **Lokales Skript hochladen** – wählt eine lokale `.py`-/`.sh`-/beliebige Datei, lädt sie per `scp` nach `/tmp`, führt sie mit dem gewählten Interpreter und optionalen Argumenten aus und löscht sie anschließend wieder.
- **Skript liegt auf Server** – führt ein bereits vorhandenes Skript über seinen Remote-Pfad aus.

Für Skript-Modi kann optional ein **Vor-Befehl** und **Nach-Befehl** angegeben werden, z. B. `cd /opt/app`, Service-Stop/Start oder Statusausgaben. Im Bestätigungsdialog und oben im Terminal wird die genaue Reihenfolge angezeigt. Während der Ausführung trennt die App den Output mit klaren Headern, z. B. `Output vom Vor-Befehl`, `Output vom Skript`, `Output vom Nach-Befehl`.

Favoriten speichern komplette Runbooks inkl. Modus, Pfaden, Interpreter, Argumenten, Vor-/Nach-Befehl, Name und Notiz. Favoriten können angelegt, bearbeitet, gelöscht und oben angepinnt werden. Zuletzt verwendete Ausführungen bleiben für schnelles Wiederholen verfügbar.

## Weitere Werkzeuge und Handling

- **Auswahl prüfen** zeigt alle angehakten Ziele, auch ausgeblendete Suchtreffer.
  Ohne Häkchen verwendet F2/Entf die Fokuszeile; bei mehreren Häkchen muss ein
  eindeutiges Einzelziel gewählt werden.
- **Details ein-/ausblenden** erklärt Quelle und Benutzerherkunft der Fokuszeile.
- **Filter / Ansichten** kombiniert Quelle, Ordner, Benutzer und Port mit der
  Hauptsuche; benannte Ansichten und aktive Kriterien werden gespeichert.
- **Datei hochladen…** überträgt eine Datei auf einen Host ohne sudo in einen
  beschreibbaren Ordner. **Dateien verteilen…** bietet mehrere Ziele und
  ausdrücklich gewählte Rechte/Folgebefehle.
- **Dienststatus**, **Dienstneustart** und **Dienstlogs** sind getrennte
  systemd-Aufgaben; ein Dienstneustart startet keinen Server neu.
- **Tunnel öffnen** unterscheidet direkten und internen Zugriff, bietet
  Port-Vorlagen und zeigt den Verbindungsweg.
- **Verbindung diagnostizieren…** trennt DNS, TCP und optional ausdrücklich
  gestartete SSH-Anmeldung. Ein offener Port ist kein erfolgreicher Login.
- **Letzte Sammelergebnisse…** zeigt Rückmeldungen je Host. Terminalstart gilt
  nicht als Remote-Erfolg; nur bestätigte Fehler lassen sich mit erneuter
  Vorschau wieder vorbereiten. Fehlgeschlagene Abläufe können Teilschritte
  bereits verändert haben.
- **Datei → Quellenstatus…** unterscheidet fehlende, leere und fehlerhafte
  Quellen und lädt gezielt neu. WinSCP/FileZilla können als eigene App-Kopie
  übernommen werden; Alias-Einträge bleiben von der SSH-Konfiguration abhängig.
- **Ctrl+Z / Lokale Änderung rückgängig** stellt bis zu 20 lokale Änderungen
  dieser App-Sitzung einschließlich zugehöriger App-Metadaten wieder her.
  Remote-Aktionen und externe Quelldateien sind nicht rückgängig machbar.
- **Verbindungsliste exportieren** bietet Ansicht/Auswahl/alle geladenen
  Verbindungen. **App sichern / App-Backup wiederherstellen** sichert die vier
  App-Datendateien, einschließlich Notizen und UI-State, mit Restore-Vorschau
  und vorherigem Sicherheitsbackup. Externe Quellen und SSH-Schlüssel sind
  separat zu sichern; nach Restore ist ein App-Neustart nötig.

## Parallelität je Lauf

Bei Prüfungen lässt sich **Parallelität begrenzen** direkt je Funktion/Lauf ändern
oder ausschalten. Ohne Häkchen werden alle Ziele dieses Laufs parallel bearbeitet.
Die bisherigen Werte bleiben nur Defaults: Hosts prüfen, Diagnose, Quellserver-Portprüfung,
Zertifikatssuche und Dienststatus jeweils 8, DNS-Auflösung 4. Bei Hosts prüfen und
DNS-Auswahl erscheint die Wahl vor dem Start; die anderen Werkzeuge haben sie im Dialog.
Beim Dienststatus gilt die Auswahl unter **Dienststatus-Prüfung**, unabhängig vom
Neustart-Ablauf der Vorlage. Einstellungen des aktuellen Laufs ändern keine anderen Läufe.

Der TCP-Vollscan trennt **Ziel-IP-Parallelität** (Standard 1), **Portparallelität je IP**
(Standard 64) und **Starts/s je IP** (Standard 50). Jede Begrenzung ist separat
abschaltbar; dann gibt es an dieser Stelle keine künstliche Warte-/Workergrenze.
Timeouts und Abbruch bleiben erhalten. Portprüfungs-Wiederholungen verwenden die
Parallelitätswahl des ursprünglichen Laufs.

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

Der Import liest höchstens **5 MB** und lehnt XML mit DOCTYPE-/ENTITY-Deklarationen ab. Zu große oder ungültige Dateien werden gemeldet und bleiben unverändert. Die neuen IDs unterscheiden Benutzer und gleiche Einträge; das Einfügen anderer Sites verschiebt sie nicht. Alte Notizen, Farben, Favoriten, zuletzt verwendete Sessions und Benutzer-Overrides werden übernommen. Vor dem Speichern entstehen Sicherungen `notes.json.filezilla-v1.bak` und `ui_state.json.filezilla-v1.bak`. Bei ehemals kollidierenden IDs wird die bisher gemeinsame Zuordnung auf alle betroffenen Einträge übertragen.

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

Die App nutzt neben der Python-Standardbibliothek `ttkbootstrap` und `Pillow` für Themes, Icons und skalierbare Widget-Grafiken; die CLI verwendet `prompt_toolkit` und `wcwidth`. Die festgelegten Laufzeitversionen stehen in `requirements.txt`; Test- und Build-Werkzeuge in `requirements-dev.txt`.

Ein direkter Start mit `python ssh_manager.py` bleibt auch ohne installiertes `ttkbootstrap` möglich. In diesem Fall verwendet die App das integrierte ttk-Theme mit der SSH-Manager-Farbpalette; für das vollständige Design einschließlich Bootstrap-Icons wird die Projektumgebung aus den Installationsschritten oben empfohlen.

Eine isolierte Vorschau mit Beispieldaten lässt sich ohne Zugriff auf Registry oder App-Daten öffnen:

```bat
.venv\Scripts\python scripts\ui_preview.py
```

## Massen-Neustarts und Vorlagen

Server im Hauptfenster anhaken und **Aktionen → Massen-Neustarts…** öffnen.
„Aus Auswahl erstellen“ übernimmt die Ziele in eine Tabelle. Vorhandene Benutzer
bleiben vorbelegt; Quick-Access-User und „Leere Benutzer füllen“ ergänzen fehlende
Benutzer. Pro Server Dienste frei eingeben (+), entfernen, den Sollzustand
aktiv/inaktiv wählen oder direkt auf diesem Host mehrere Dienste durchsuchen.
Benutzer gelten nur für die Vorlage, auch bei SSH-Aliasen.

Vorlagen lassen sich später ohne Häkchen-Auswahl öffnen. Geänderte Vorlagen als
Kopie speichern oder ausdrücklich überschreiben. Hostnamen/Ports kommen aus den
aktuellen Verbindungen; fehlende Verbindungen ersetzen oder entfernen. Vorlagen
sind lokal im UI-State gespeichert und im App-Backup enthalten, ohne Passwörter.

Parallel mit einstellbarer Grenze oder nacheinander in Tabellenreihenfolge starten.
Bei Fehlern weiterlaufen, weitere Starts stoppen oder pausieren und nachfragen.
Laufende Neustarts werden während einer Pause weiter überwacht. Separate Fristen
gelten für Neustart/SSH und anschließend die Serviceprüfungen. Erfolg benötigt
Neustartnachweis, SSH-Rückkehr und alle Sollzustände. Inaktiv heißt vorhanden und
sauber gestoppt; `failed` zählt nicht als inaktiv. Dienste werden nur geprüft.
Fehlende Units verhindern den Reboot dieses Ziels bereits in der Vorprüfung.

Mit **Alle parallel durchstarten** werden alle Zielserver ohne Parallelitätsgrenze
und ohne Fehlerpause angestoßen. „Max. gleichzeitig“ und „Bei Fehlern“ sind in diesem
Modus deaktiviert; beim Wechsel zurück bleiben die Werte erhalten. Die SSH-Anmeldung
und Vorprüfung bleiben pro Server erhalten, daher sind die Reboots nicht exakt synchron.

Die Vorschau zeigt alle Ziele und Prüfungen; erst „Server jetzt neu starten“ löst
Neustarts aus. Stoppen verhindert weitere Starts, nimmt ausgelöste Reboots aber
nicht zurück.

Ohne **Passwort je Verbindung** gilt das obere sudo-Passwort für alle Server.
Mit der Checkbox erscheinen verdeckte Passwortfelder je Server unter dem Benutzer.
**Leere Passwörter füllen** übernimmt das obere Passwort nur in leere Felder;
vorhandene Werte bleiben erhalten. Leere Einzelpasswörter bedeuten sudo ohne Passwort,
ohne automatischen Rückgriff auf das gemeinsame Passwort. Der Moduswechsel erhält
die Eingaben; Ersetzen einer Verbindung entfernt deren altes Passwort.
Beim Speichern der Vorlage werden Passwörter mit Windows-DPAPI an dein
Windows-Benutzerkonto gebunden verschlüsselt, auch im App-Backup. Auf einem anderen
Rechner/Konto müssen unlesbare Passwörter neu eingegeben werden (zum Leeren kurz
etwas eingeben und wieder löschen). Unlesbare gespeicherte Werte bleiben erhalten
und blockieren den Start im betroffenen Modus. Änderungen am gemeinsamen Passwort
in der Startvorschau gelten nur für diesen Lauf. Diese Felder dienen sudo;
die SSH-Anmeldung verwendet weiterhin Schlüssel/Agent.

### Massendienststatus mit denselben Vorlagen

**Aktionen → Massendienststatus…** öffnen, vorhandene Neustart-Vorlage auswählen
und öffnen, dann **Dienststatus prüfen** drücken. Derselbe Button steht auch im
Massen-Neustart-Editor. Beide Aktionen verwenden dieselbe Vorlagenbibliothek;
es gibt keinen automatischen Zeitplan. Bei Konflikten zwischen geöffneten Fenstern
die inzwischen geänderte Vorlage erneut öffnen. Änderungen anderer Vorlagen bleiben erhalten.

Der Check liest einmalig `systemctl show` für die eingetragenen Dienste, mit
standardmäßig acht Servern gleichzeitig; die Begrenzung ist je Lauf änderbar oder abschaltbar. Er führt keinen Neustart oder Dienststart/-stopp aus
und benötigt keine sudo-Passwörter. Die nichtmodale Ergebnistabelle enthält Server,
Benutzer, Dienst, Soll, Ist und Ergebnis. Fehlende Dienste, SSH-/Abfragefehler und
Sollabweichungen werden unterschieden. Server ohne Dienste werden ausdrücklich als
nicht geprüft angezeigt. Abbrechen überspringt wartende Abfragen; laufende Abfragen
kehren spätestens nach ihrem SSH-Timeout zurück. Alles, Fehler/Abweichungen und
ausgewählte Ergebnisse sind als Tabelle kopierbar.

Im Ergebnisfenster kopiert „Alle Fehler kopieren“ Fehler und Zeitüberschreitungen,
„Alles kopieren“ alle Tabellenzeilen samt Überschriften. Strg/Umschalt markiert
mehrere Zeilen; Strg+C oder „Auswahl kopieren“ kopiert sie. Textausschnitte unten
oder nach Doppelklick in den vollständigen Details markieren. Lange Meldungen
bleiben beim Kopieren vollständig erhalten.

Fortschritts-/Ergebnisfenster und Vorlagenverwaltung bleiben als unabhängige
Arbeitsfenster offen. Das Hauptfenster ist während laufender und abgeschlossener
Neustarts weiter bedienbar: andere Verbindungen oder Fehler-Server auswählen und
weitere Aktionen ausführen. Nur Eingaben und Startbestätigungen sperren vorübergehend.

## Portable Windows-EXE bauen

Den vollständigen Weg vom Klonen bis zur persönlichen GUI-/CLI-Installation
beschreibt [Vom Git-Download zur fertigen Installation](#vom-git-download-zur-fertigen-installation).
Im vorbereiteten Windows-Repository mit `.venv` genügt:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Das Script nutzt bevorzugt `.venv\Scripts\python.exe`, sonst `python` aus dem PATH, installiert die festgelegten Build-Abhängigkeiten und erzeugt:

```text
dist\SSH Manager.exe
dist\sshm.exe
```

Jeder fehlgeschlagene externe Schritt stoppt den Build mit einem Fehlerexit. Alte Buildausgaben werden erst nach erfolgreicher Python-, Versions- und Abhängigkeitsprüfung entfernt; auch Bereinigungsfehler brechen ab. Die Erfolgsmeldung erscheint nur nach erfolgreichem PyInstaller-Lauf mit beiden neu erzeugten, nicht leeren EXEs.

Die GUI-EXE läuft ohne zusätzliches Konsolenfenster; die CLI nutzt das aufrufende
Terminal. Beide verwenden das App-Icon und Daten unter `%APPDATA%\SSH-Manager\`.
Die Paket-Metadaten einschließlich der Lizenzdateien werden in die jeweiligen
portablen Anwendungen aufgenommen. Die Python-Variante bleibt weiterhin nutzbar.
