"""Offline, searchable help. Content stays independent of Tk for testing/export."""
from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from .window_policy import AppWindow
from tkinter import ttk

from .shortcuts import DEFAULT_ACTION_ORDER, default_shortcuts
from .themes import palette_for_theme
from .ui_components import build_dialog_header


@dataclass(frozen=True)
class HelpTopic:
    id: str
    title: str
    body: str


TOPICS = (
    HelpTopic("start", "Schnellstart und Auswahl", """Der SSH-Manager sammelt Verbindungen aus mehreren Quellen in einem Baum. Er öffnet SSH-Verbindungen im konfigurierten Terminal; er ist selbst kein SSH-Terminal.

Aktionen und Rechtsklick
Die Diagnose steht direkt im Verbindung- und Ordner-Rechtsklick. ‚Alle Aktionen für diese Verbindung/diesen Ordner‘ enthält dieselben Werkzeuge wie das Hauptmenü und verwendet diese Kontextziele. Oben unter ‚Aktionen → Verbindung / Ordner verwalten‘ sind zusätzlich die Funktionen des fokussierten Baum-Kontexts erreichbar. ‚App-Werkzeuge‘ bietet Datei-, Auswahl-, Ansichts-, Einstellungs- und Hilfeaktionen mit ihrem ursprünglichen App-Geltungsbereich. Nicht anwendbare Zielaktionen bleiben mit einer Begründung deaktiviert. Globale Häkchen-Auswahl, Filter und angezeigte Listen sind in den Beschriftungen ausdrücklich benannt.

Einzelne Verbindung öffnen
Suche nach einem Namen oder Hostnamen, klicke auf eine Verbindung oder navigiere mit den Pfeiltasten. Enter oder ein Doppelklick öffnet diese Verbindung. Falls erforderlich, wähle den SSH-Benutzer im folgenden Dialog.

Zeile und Checkbox sind verschieden
Die hervorgehobene Zeile ist der Tastaturfokus. Häkchen sind die Mehrfachauswahl. Mit Hoch/Runter bewegst du nur den Fokus; vorhandene Häkchen bleiben bestehen. Enter benutzt die fokussierte Zeile, nicht automatisch alle Häkchen.

Mehrere Verbindungen öffnen
Setze Häkchen per Mausklick oder Leertaste. Strg+Enter (Standard) oder Aktionen → Auswahl verbinden öffnet die angehakten Sessions. Ohne Häkchen wird keine Verbindung geöffnet. Eine Ordner-Checkbox wählt auch Sessions in Unterordnern.

Alle auswählen / Alle abwählen / Auswahl umkehren
Diese Aktionen ändern die Checkbox-Auswahl im aktuellen Baum. Nutze sie für gemeinsame Aktionen auf mehreren Hosts. Prüfe vor einer Serveraktion die im Dialog aufgeführten Zielhosts.

Voraussetzungen
Für SSH muss der Zielhost erreichbar sein und eine Anmeldung erlauben. Windows Terminal und Git Bash müssen für den Standard-Startpfad installiert sein. Herdr ist eine optionale Terminalwahl in den Einstellungen."""),
    HelpTopic("installation", "Installation und EXE-Build", r"""Quellcode oder fertige EXE?
Ein Git-Klon oder ZIP-Download enthält den Quellcode. Er baut keine EXEs und richtet keinen sshm-Befehl ein. Die grafische App und die CLI lassen sich direkt mit Python starten oder als zwei portable EXEs bauen. Diese Hilfe ist offline lesbar; sie führt die Befehle nicht aus.

1. Voraussetzungen auf dem Build-PC
Für den hier geprüften Windows-x64-Build: Windows, Python 3.14 in 64-Bit-Ausführung mit venv/pip und für git clone Git für Windows. Download-Adressen: https://www.python.org/downloads/windows/ und https://git-scm.com/downloads/win . Git für Windows enthält Git Bash und SSH. Fertige EXEs benötigen später kein separat installiertes Python. Externe Werkzeuge für Verbindungsaktionen bleiben nötig: für den Standard-GUI-Pfad Windows Terminal und Git Bash; für die CLI ein SSH-Client im PATH der jeweiligen Shell. Herdr ist optional.

2. Repository herunterladen (PowerShell)
git clone https://github.com/KaiWiehe/ssh_manager.git SSH-Manager
Set-Location SSH-Manager
python --version
python -m venv .venv

ZIP-Alternative
ZIP vollständig entpacken und PowerShell im entpackten Repository-Ordner öffnen. Dort müssen ssh_manager.py, sshm.py, requirements.txt und scripts liegen. Auch dann python --version und python -m venv .venv ausführen. Wenn nur der Launcher py verfügbar ist, kann py -3.14 -m venv .venv die Umgebung erstellen. Befehle in PowerShell eingeben, nicht im Python-Prompt >>>. Die Umgebung muss nicht aktiviert werden, da die folgenden Befehle ihren Interpreter direkt aufrufen. Jeden Schritt nur nach Erfolg des vorherigen fortsetzen.

3. Architektur prüfen und beide EXEs bauen
.\.venv\Scripts\python.exe -c "import struct; print(struct.calcsize('P') * 8)"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1

Welche Architektur wird gebaut?
Die Prüfung muss für den beschriebenen x64-Build 64 ausgeben. Unter Windows mit dem passenden Python bauen; dessen Architektur bestimmt die Ausgabe. Andere Architekturen sind nicht automatisch geprüft. Das Buildskript bevorzugt .venv\Scripts\python.exe, prüft die Versionsmetadaten und installiert die festgelegten Abhängigkeiten aus requirements-dev.txt einschließlich requirements.txt. Zum normalen Bauen keine Version erhöhen und PyInstaller nicht separat installieren. Bei einem Fehler zuerst dessen Ursache beheben.

4. Die richtige EXE wählen
dist\SSH Manager.exe ist die grafische App, per Doppelklick startbar. dist\sshm.exe ist die Terminalsuche für PowerShell oder Git Bash. Beide enthalten ihre Python-Laufzeit. Der Build ersetzt build und dist: dort keine eigenen Dateien aufbewahren. Einstellungen und Verbindungen unter %APPDATA%\SSH-Manager werden nicht ersetzt.

5. GUI dauerhaft ablegen (PowerShell im Repository)
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\SSH-Manager'
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Copy-Item -LiteralPath '.\dist\SSH Manager.exe' -Destination $installDir -Force
& (Join-Path $installDir 'SSH Manager.exe')

Portable Installation
Alternativ die GUI direkt aus dist starten. Die feste Ablage bleibt beim nächsten Repository-Build erhalten. Es gibt keinen klassischen Setup-Assistenten; eine Windows-Verknüpfung auf die abgelegte EXE ist optional. Die persönliche Ablage benötigt keine Administratorrechte. Benutzerdaten liegen unter %APPDATA%\SSH-Manager, nicht neben der EXE. Für den CLI-Befehl anschließend das Hilfethema „CLI: sshm einrichten und verwenden“ öffnen; das CLI-Installationsskript kopiert nicht die GUI.

Alternative ohne EXE-Build
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe ssh_manager.py

CLI direkt mit Python
.\.venv\Scripts\python.exe sshm.py web

Python-Start und weitere Hilfe
Direkter Python-Start erzeugt keine EXE und registriert kein sshm im PATH. Für spätere Updates und typische Fehler das Thema „Aktualisierung und Einrichtungsprobleme“ verwenden. Die gleichen Schritte stehen in der README.md des Repositorys."""),
    HelpTopic("cli", "CLI: sshm einrichten und verwenden", r"""Was ist sshm?
sshm ist ein eigenständiges Konsolenprogramm (sshm.exe), kein Shell-Alias und keine Profilfunktion. Es nutzt dieselben Verbindungen und App-Daten wie die grafische App; diese muss nicht laufen. Die benötigte Python-Laufzeit steckt in der EXE, der eigentliche SSH-Client bleibt ein externes Werkzeug.

1. Zuerst bauen
Nach Git-Download zunächst die Schritte im Thema „Installation und EXE-Build“ ausführen. Erst der erfolgreiche Build erzeugt dist\sshm.exe. Ohne EXE ist der Python-Aufruf .\.venv\Scripts\python.exe sshm.py möglich, nachdem die Laufzeit-Abhängigkeiten installiert wurden.

2. CLI installieren (PowerShell im Repository)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_cli.ps1 -AddToPath

Was wird eingerichtet?
Das Skript kopiert nur dist\sshm.exe nach %LOCALAPPDATA%\Programs\SSH-Manager\sshm.exe und ergänzt den Ordner im persönlichen Benutzer-PATH. PATH ist die Ordnerliste, in der die Shell nach Programmen sucht. Ohne -AddToPath wird nur die EXE kopiert. Shell-Profile und Maschinen-PATH bleiben unverändert. Das Skript installiert nicht die GUI-EXE; deren Ablage ist im Installations-Thema beschrieben. Bei einer erkannten Namenskollision bricht es ab.

3. Neues Terminal und Aufruf prüfen (PowerShell)
Get-Command sshm -All
sshm --version
sshm
sshm web produktion

PATH und Git Bash
Nach der Installation ein neues Terminal öffnen. Ein bereits laufender Terminalhost oder persistenter Herdr-Prozess kann den alten PATH behalten; bei Bedarf nach Ende laufender Arbeiten vollständig neu starten. In Git Bash zeigt command -v sshm das gefundene Programm. Profilbasierte Aliase oder Funktionen können den Namen überschatten; der Installer mit -NoProfile kennt diese Definitionen der aufrufenden Shell nicht. Mit den Prüfbefehlen sicherstellen, dass die gewünschte EXE gefunden wird. sshm web produktion füllt nur den Suchtext und verbindet nicht automatisch.

Sofort ohne PATH verwenden (PowerShell)
& "$env:LOCALAPPDATA\Programs\SSH-Manager\sshm.exe"

Portable Verwendung direkt aus dem Repository
PowerShell: .\dist\sshm.exe web
Git Bash: ./dist/sshm.exe web

Suche und Details
Die globale Fuzzy-Suche berücksichtigt Name, Originalordner, Host/IP, Benutzer, Quelle und Notizen. Alle Quellen werden durchsucht, auch GUI-seitig ausgeblendete. Links bleiben die echten Elternordner sichtbar, rechts stehen die Details und vollständigen Notizen; schmal darunter. Bei aktiver Suche bleiben Trefferordner offen. Favoriten und Verlauf filtern den Originalbaum ohne zusätzliche Verbindungskopien. Favoriten werden weiterhin in der GUI bearbeitet.

Tasten der CLI
Tippen im Suchfeld: suchen. Hoch/Runter im Suchfeld oder Baum: markieren. Tab/Umschalt+Tab: zwischen Suchfeld, Baum und Details wechseln. Links/Rechts im Baum: Ordner bedienen. Enter auf einer Verbindung: direkt starten; auf einem Ordner nur umklappen. In Details mit Pfeilen und Bild hoch/runter scrollen. F2 öffnet Quellen-, Ordner- und Ansichtsfilter; F3 setzt alle Filter zurück. Im Filterdialog mit Tab wechseln, mit Pfeilen wählen und Quellen mit Leertaste umschalten. Quellen wirken untereinander als ODER; Quellen, Ordner inklusive Unterordnern und Ansicht (Alle, Favoriten, Zuletzt verwendet) gemeinsam als UND. Esc schließt den Filterdialog oder beendet die Suche. Strg+C bricht die Auswahl ab.

Anmeldung und Rückkehr
SSH-Aliase behalten ihre SSH-Konfiguration. Andere Verbindungen nutzen den festen Benutzer, dann den konfigurierten Standard; falls nötig fragt die CLI im Terminal mit Quick-User-Vervollständigung per Tab nach. Esc/Strg+C brechen diese Abfrage ab. Nach Auswahl wird SSH im aktuellen Tab oder Pane gestartet. Während SSH gehört die Eingabe dem SSH-Client. Nach exit gelangst du zur aufrufenden Shell zurück; der SSH-Exitcode wird weitergegeben. Zuletzt verwendet bedeutet lokalen Start, keine bestätigte Anmeldung.

Terminalumgebung
PowerShell und Git Bash können unterschiedliche SSH-Clients, Agenten und Konfigurationen verwenden; die CLI nimmt den ausführbaren SSH-Client aus dem geerbten PATH. Die vorgesehenen Terminalhosts sind Windows Terminal und Herdr. Die direkte Bedienabnahme in deren vier Shell-/Host-Kombinationen ist noch offen; die paketierte CLI ist gegen beide SSH-Clients in automatisierten lokalen Windows-ConPTY-Tests geprüft. Die Suche selbst startet keine Netzwerkprüfung."""),
    HelpTopic("updates", "Aktualisierung und Einrichtungsprobleme", r"""Update aus dem Repository
Vor dem Ersetzen die grafische App schließen und laufende CLI-/SSH-Aufträge beenden. Die folgenden Schritte einzeln in PowerShell im Repository mit bestehender .venv ausführen; nur bei Erfolg fortsetzen. git pull aktualisiert nur den Quellcode, weder gebaute noch installierte EXEs.

1. Quellcode und Build aktualisieren
git pull --ff-only
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1

2. Installierte CLI ersetzen
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_cli.ps1 -AddToPath

3. Abgelegte GUI ersetzen
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\SSH-Manager'
Copy-Item -LiteralPath '.\dist\SSH Manager.exe' -Destination $installDir -Force

Nach dem Update
Das Buildskript installiert auch geänderte Abhängigkeiten. Programme anschließend neu starten; CLI-Version mit sshm --version prüfen, GUI-Version im Fenster ablesen. Ein erneuter Build ersetzt nicht automatisch die separat abgelegten Programme. Eigene Verbindungen, Einstellungen und Notizen unter %APPDATA%\SSH-Manager bleiben erhalten. Bei lokalen Git-Änderungen einen abgebrochenen Pull zuerst klären; nicht mit einem alten Quellstand weiterbauen.

Python fehlt oder öffnet den Store
Python-Installation und PATH prüfen. Falls vorhanden kann py -3.14 -m venv .venv die Umgebung anlegen. Die direkten .venv\Scripts\python.exe-Aufrufe benötigen keine Aktivierung. Python ist nur zum Bauen oder Quellcode-Start erforderlich, nicht zum Nutzen fertiger EXEs.

dist\sshm.exe fehlt oder Build schlägt fehl
Zunächst den kompletten Build erfolgreich abschließen. Der erste fehlgeschlagene Schritt stoppt das Buildskript. Eine eventuell noch vorhandene alte EXE beweist keinen neuen erfolgreichen Build. Versionsfehler mit .\.venv\Scripts\python.exe scripts\bump_version.py --check untersuchen; zum normalen Bauen keine Version eigenständig erhöhen. Architektur des Build-Python prüfen (64 für Windows x64).

sshm wird nicht gefunden oder startet eine andere Anwendung
In PowerShell Get-Command sshm, in Git Bash command -v sshm prüfen. Installer mit -AddToPath ausführen und neues Terminal öffnen; den bestehenden Terminalhost gegebenenfalls vollständig neu starten, ohne aktive Arbeiten abzubrechen. Alternativ den vollständigen Pfad %LOCALAPPDATA%\Programs\SSH-Manager\sshm.exe aufrufen. Bei Namenskollision die fremde Alias-/Funktions-/Programmdefinition zuerst prüfen; der Installer ersetzt sie nicht.

SSH fehlt oder Anmeldung unterscheidet sich zwischen Shells
ssh -V prüfen. PowerShell: Get-Command ssh. Git Bash: command -v ssh. Die EXE enthält Python, aber kein SSH. SSH-Client, Schlüssel, Agent und Konfiguration der jeweiligen Shell überprüfen. Windows Terminal/Git Bash für GUI-Verbindungen bereitstellen; für Herdr die Terminalwahl in den App-Einstellungen prüfen.

EXE kann nicht kopiert werden
Die laufende Instanz der zu ersetzenden Datei beenden und erneut kopieren. Das Installationsskript installiert nur die CLI. Für die grafische App die GUI-EXE separat kopieren, wie unter „Installation und EXE-Build“ beschrieben.

Persönliche Ablage entfernen
Nicht mehr benötigte abgelegte EXEs gezielt entfernen. Den hinzugefügten Ordner %LOCALAPPDATA%\Programs\SSH-Manager nur dann aus dem Benutzer-PATH entfernen, wenn er nicht mehr benötigt wird. App-Daten unter %APPDATA%\SSH-Manager bleiben getrennt bestehen; nicht als Teil eines Programmupdates löschen."""),
    HelpTopic("keys", "Tastatur und Tastenkürzel", """Im Verbindungsbaum
↑ / ↓: Zur vorherigen/nächsten sichtbaren Zeile wechseln.
→: Geschlossenen Ordner öffnen; im offenen Ordner zum ersten Kind wechseln.
←: Offenen Ordner schließen; sonst zum übergeordneten Ordner wechseln.
Enter (Standard): Fokussierte Verbindung öffnen oder Ordner auf-/zuklappen.
Strg+Enter (Standard): Angekreuzte Verbindungen öffnen.
Shift+Enter: Keine eigene Aktion. Bei der Standardbelegung greift auch hier die Enter-Bindung von Tk; die fokussierte Zeile wird aktiviert. Es ist kein Kürzel für die Checkbox-Auswahl.
Leertaste: Häkchen der Zeile umschalten; bei Ordnern alle enthaltenen Sessions einschließlich Unterordnern auswählen/abwählen.
Shift+F10 / Menütaste: Kontextmenü der fokussierten Zeile öffnen.

Bearbeiten und Löschen
F2 und Bearbeiten in der Palette verwenden genau eine angehakte Session; ohne Häkchen die fokussierte Zeile. Bei mehreren Häkchen wird kein Einzelziel gewählt. Importierte Verbindungen bieten nur die unterstützten App-internen Anpassungen.
Entf und Löschen in der Palette verwenden dieselbe Zielregel und löschen erst nach Bestätigung. Das gilt für eigene Verbindungen und Alias-Kopien, nicht für die externen Originalquellen. Das Kontextmenü bezeichnet ausdrücklich „Diese Verbindung“ und handelt auf der dort angeklickten Zeile.

Eigene Kürzel
Unter Einstellungen → Tastenkürzel ein Feld anklicken und die gewünschte Kombination drücken. Escape bricht die Erfassung ab, Backspace entfernt das Kürzel, Reset stellt den Standard wieder her. Nicht jede feste Baumtaste ist dort konfigurierbar.

Wo gelten Kürzel?
Enter und Auswahl verbinden benötigen Tastaturfokus im Verbindungsbaum. Textfelder behalten ihre vorgesehenen Texteingaben. Modale Dialoge verwenden ihre eigene Bedienung. Im Hilfefenster lösen App-Kürzel keine Aktionen im Hauptfenster aus; Escape schließt die Hilfe.

Aktuelle Belegung und Standards
{shortcuts}"""),
    HelpTopic("folders", "Ordner auf- und zuklappen", """Einzelner Ordner
Klicke auf den kleinen Pfeil am Ordner. Mit der Tastatur: Ordner fokussieren und Enter zum Umschalten, Rechts zum Öffnen oder Links zum Schließen drücken. Ist der Ordner schon geöffnet, wechselt Rechts zum ersten Kind. Links wechselt von einer Verbindung oder einem geschlossenen Ordner zum Elternordner.

Ordner einschließlich Unterordnern
Im Rechtsklick-Menü des Ordners stehen rekursive Aktionen zum Auf- und Zuklappen. Sie betreffen diesen Ordner und seine Unterordner.

Alle Ordner
Ansicht → Ausklappen / Einklappen, die entsprechenden Toolbar-Buttons oder die Palettenaktionen „Ordner ausklappen“ / „Ordner einklappen“ wirken auf den gesamten Baum. Die Toolbar-Buttons können in den Einstellungen ausgeblendet sein.

Ordnerzustand und Suche
Der normale Auf-/Zuklappzustand wird gespeichert. Bei aktiver Suche öffnet die App Trefferordner vorübergehend. Nach dem Leeren der Suche kehrt der gespeicherte Benutzerzustand zurück.

Alle im Ordner verbinden
Diese Kontextmenüaktion verbindet die Sessions des Ordners, ohne zuvor Checkboxen setzen zu müssen. Auswahlaktionen im Ordner-Menü setzen oder entfernen stattdessen nur Häkchen.

Ordner verwalten
Eigene Verbindungen und Alias-Kopien lassen sich in Ordner verschieben. Ordner umbenennen wirkt auch auf zugehörige Unterordner. Löschen ist nur für unterstützte App-Verbindungen verfügbar; externe Quellen werden nicht verändert."""),
    HelpTopic("palette", "Befehlspalette", """Öffnen und suchen
Strg+P (Standard) oder Datei → Befehlspalette öffnet die Palette. Tippe einen Verbindungsnamen, Hostnamen, Benutzer, Ordner oder eine Aktion. Die unscharfe Suche findet Zeichen in derselben Reihenfolge, auch wenn sie nicht direkt nebeneinander stehen. Sie sucht in Namen und Zusatztexten; sie ist keine Volltextsuche über alle Sessiondaten.

Nur Aktionen finden
Ein führendes > beschränkt die Ergebnisse auf Aktionen. Beispiel: „> einklappen“ findet die Aktion zum Schließen aller Ordner. Ohne > werden Sessions und Aktionen gemeinsam angezeigt. Zuletzt genutzte Verbindungen und Aktionen werden bevorzugt einsortiert.

Bedienung
Hoch/Runter wechselt den Treffer, Enter führt ihn aus, Escape schließt die Palette. Ein Session-Treffer öffnet genau diese Verbindung. Ein Aktions-Treffer führt die benannte App-Aktion aus.

Auswahlabhängige Aktionen
„Verbinden mit Auswahl“ verwendet die angehakten Sessions. „Bearbeiten“ und „Löschen“ verwenden wie F2/Entf genau eine angehakte Session, ohne Häkchen die fokussierte Zeile. Bei mehreren Häkchen wird kein Einzelziel gewählt. Löschen ist nur für eigene Sessions und Alias-Kopien erlaubt.

Weitere Aktionen
Neue Verbindung, Einstellungen, Suche fokussieren, neu laden, DNS/IP auflösen, Auswahl ändern, Ordner aus-/einklappen, Zuletzt verwendet umschalten, Einstellungen importieren/exportieren und Hilfe öffnen sind über die Palette erreichbar. Weitere Serverwerkzeuge findest du im Menü Aktionen und in den Kontextmenüs.

Fensterbreite
Die Palette lässt sich in der Breite verändern; die Breite wird gespeichert. Lange Treffer zeigen beim Darüberfahren einen Tooltip."""),
    HelpTopic("sources", "Verbindungen, Quellen und Benutzer", """Neue Verbindung
Datei → Neue Verbindung legt eine eigene App-Verbindung mit Name, Host, Port, Benutzer und Ordner an. Sie wird in app_sessions.json gespeichert. Name und Host sind verschiedene Felder: Der Name ist die Anzeige, der Host das SSH-Ziel.

Quellen
WinSCP: Liest gespeicherte Sessions aus der Windows-Registry. „In WinSCP öffnen“ ist nur für diese Quelle verfügbar und benötigt WinSCP.
SSH Config: Liest ~/.ssh/config. Verbunden wird über den Alias („ssh ALIAS“); Benutzer und weitere SSH-Optionen kommen aus der SSH-Konfiguration.
SSH-Alias-Kopie: Eine App-interne Kopie eines Alias für eigene Ordnerorganisation. Die Verbindung nutzt weiterhin den Alias.
FileZilla Config: Liest Sites aus sitemanager.xml; SSH verbindet zum gespeicherten Host. Die Datei wird nicht zurückgeschrieben.
Eigene App-Verbindungen: Im SSH-Manager angelegt und vollständig dort verwaltbar.

Bearbeiten, Duplizieren, Verschieben und Löschen
Eigene Verbindungen und Alias-Kopien können umbenannt, verschoben und gelöscht werden. Duplizieren erstellt eine weitere App-Verbindung; einen SSH-Config-Alias kannst du als Alias-Kopie in einen eigenen Ordner übernehmen. Importierte Originalquellen lassen sich nicht wie eigene Sessions verändern.

Benutzer wählen und merken
Normale Host-Verbindungen verwenden den festen Benutzer oder die Benutzerwahl mit Schnellauswahl. „Benutzer setzen“ und „Benutzer entfernen“ ändern App-interne Benutzerzuordnungen, auch für eine Auswahl. SSH-Config-Verbindungen verwenden den Alias und überspringen den Benutzer-Dialog. Benutzer-Overrides werden nicht in die externen Quellen geschrieben.

SSH Config ansehen
„Konfiguration anzeigen (ssh -G)“ zeigt die von SSH aufgelösten Optionen für einen Alias. „SSH Config in VS Code öffnen“ öffnet die Konfigurationsdatei im Editor; benötigt VS Code.

Neu laden
F5 (Standard) liest die Verbindungen erneut ein. Nutze es, wenn du WinSCP, FileZilla oder die SSH-Konfiguration außerhalb der App geändert hast. Die Quellenfilter bestimmen, welche Quellen sichtbar sind."""),
    HelpTopic("organize", "Notizen, Farben und Favoriten", """Notizen
Über das Kontextmenü eine Notiz zur Session hinterlegen. Sie erscheint als Tooltip und optional in der Notizen-Spalte. Notizen liegen ausschließlich in notes.json; WinSCP, FileZilla und SSH Config werden nicht geändert. Notiz kopieren übernimmt den Text in die Zwischenablage.

Farben
Das Kontextmenü kann eine Session, eine Checkbox-Auswahl oder die Sessions eines Ordners einfärben. Damit markierst du beispielsweise Umgebungen oder Zuständigkeiten. „Farbe entfernen“ entfernt die einzelne Zuordnung; Ansicht → Farben zurücksetzen entfernt die App-Farbzuordnungen.

Session-Favoriten
„Zu Favoriten hinzufügen“ macht eine Verbindung im virtuellen Favoritenordner erreichbar. Der Dialog steuert auch die Anzeige im Originalbaum. „Favorit entfernen“ entfernt den Favoritenstatus, nicht die Originalverbindung. Mehrere angehakte Verbindungen können gemeinsam hinzugefügt werden.

Zuletzt verwendet
Geöffnete Verbindungen erscheinen im virtuellen Ordner „Zuletzt verwendet“. Das ist eine zusätzliche Ansicht derselben Sessions, keine weitere Datenquelle. Strg+Shift+R (Standard) schaltet diesen Ordner um.

Runbook-Favoriten sind getrennt
Favoriten im Remote-Befehl-Dialog speichern Befehle/Skript-Einstellungen. Sie sind unabhängig von Session-Favoriten."""),
    HelpTopic("network", "Hosts prüfen, DNS, Jumphost und Tunnel", """Hosts prüfen
Parallelität je Lauf
Bei mehreren Zielen fragt „Hosts prüfen“ vor dem Start nach der Parallelität. Default acht; Zahl ändern oder „Parallelität begrenzen“ ausschalten, um alle Ziele dieses Laufs parallel zu prüfen. DNS-Auswahl bietet dieselbe Wahl mit Default vier. Andere Prüfwerkzeuge haben diese Auswahl direkt im Dialog. Die Wahl gilt nur für den aktuellen Lauf und ändert keine anderen Fenster.

Prüft eine TCP-Verbindung zum SSH-Port der Session. Im Baum erscheinen ⏳, ✓ oder ✗. Das prüft Erreichbarkeit, nicht die Anmeldung oder den Zustand eines Dienstes. Kontextmenüaktionen wirken auf den Host, die Auswahl oder den Ordner entsprechend ihrer Beschriftung. Beim Neuaufbau des Baums wird der Status zurückgesetzt.

DNS/IP auflösen
Aktionen → DNS/IP auflösen öffnet eine freie Abfrage. Die Auswahlvarianten lösen die ausgewählten Hostnamen auf; „DNS-Auswahl“ erlaubt einen anderen DNS-Server. Nutze das zur Prüfung von Namensauflösung und IP-Adressen. Die Abfrage verändert keine DNS-Einträge.

Über Jumphost öffnen
Öffnet eine SSH-Verbindung über einen vorgeschalteten SSH-Server. Nützlich, wenn ein Ziel nur aus einem internen Netz erreichbar ist. Trage den Sprungserver und die erforderlichen Zugangsdaten im Dialog ein. Beide SSH-Strecken müssen erreichbar sein.

Tunnel öffnen
Ein lokaler Port wird über SSH an einen Zielhost und Zielport weitergeleitet: ssh -N -L lokalerPort:Zielhost:Zielport Benutzer@SSH-Server. Beispiel: Lokalport 15432, SSH-Server gateway.example, Zielhost localhost, Zielport 5432. Ein Datenbankprogramm verbindet dann lokal zu localhost:15432.
„localhost“ als Zielhost meint den SSH-Server. Ein anderer Zielhost wird vom SSH-Server aus erreicht. Der lokale Port muss frei sein. Das Terminal hält den Tunnel offen; beende den SSH-Prozess, um ihn zu schließen. Die Funktion erstellt lokale Portweiterleitungen, keine Reverse-Tunnel oder SOCKS-Proxys."""),
    HelpTopic("remote", "Remote-Befehle und Skript-Runbooks", """Ziele und Benutzer
„Befehl ausführen“ öffnet den Runner für die im Aufruf benannten Hosts. Kontextmenüs unterscheiden Einzelhost und Auswahl; Toolbar/Menü verwenden die Checkbox-Auswahl. Eine Befehlskette verwendet einen Benutzer, nicht einen Benutzer pro Schritt. SSH-Anmeldung und benötigte Programme auf den Zielhosts müssen funktionieren.

Nur Remote-Befehl
Führt den eingegebenen Befehl per SSH auf den Zielhosts aus. Beispiel: „uname -a“ für Systeminformationen. Jeder Host erhält seinen eigenen Terminal-Output. Prüfe Hostliste und Befehl vor der Bestätigung; ein Befehl kann je nach Inhalt Serverdaten verändern.

Lokales Skript hochladen
Wähle eine lokale Skriptdatei, Interpreter und Argumente. Die App überträgt das Skript per scp nach /tmp, führt es per SSH aus und entfernt die temporäre Remote-Datei danach. Upload und Ausführung sind im Terminal getrennt sichtbar. Lokale Datei, scp und der Remote-Interpreter müssen verfügbar sein.

Skript liegt auf Server
Gib den vorhandenen Remote-Pfad, Interpreter und Argumente an. ‚Server durchsuchen‘ öffnet rechts eine Ordner-/Dateiauswahl mit Suche und explizitem Referenzhost. Nur dieser Host wird gelesen. Bei mehreren Zielen muss der gewählte Pfad überall dasselbe Skript bezeichnen. Die manuelle Eingabe bleibt möglich. Es findet kein Upload statt. Der Benutzer muss das Skript lesen/ausführen dürfen. Beispiel: /opt/tools/check.sh mit bash.

Vor- und Nach-Befehl
In den Skript-Modi können zusätzliche Befehle vor und nach dem Skript eingegeben werden. Der erweiterte Ablauf ist vollständig eingeklappt, bis sein Haken aktiviert wird. Vor- und Nach-Befehl teilen sich dann den Platz gleichmäßig. Beim Abwählen bleiben die Texte im Dialog erhalten, werden aber nicht ausgeführt. Der Terminal-Output zeigt die geplante Reihenfolge und getrennte Bereiche „Output vom Vor-Befehl“, „Output vom Skript“ und „Output vom Nach-Befehl“. Prüfe die Ausgaben jedes Schritts; der Nach-Befehl ist kein garantiertes Rollback.

Favoriten und Verlauf
Ein Runbook-Favorit speichert das vollständige Spec mit Name, Notiz und Pin-Status. Über den Favoriten-Dialog anlegen/bearbeiten, löschen oder anpinnen; angepinnte Einträge stehen oben. Der Verlauf hilft, frühere Einstellungen wiederzuverwenden. Das erneute Auswählen eines Eintrags ersetzt nicht die Prüfung der aktuellen Zielhosts."""),
    HelpTopic("server", "Dateien, Zertifikate und Serverneustart", """Dateien übertragen
Überträgt die ausgewählten lokalen Dateien auf die Zielhosts. Die Dateien werden zunächst nach /tmp hochgeladen und dann mit sudo in den Zielordner kopiert. Wähle den Remote-Zielordner und prüfe die Option „Vorhandene Dateien überschreiben“. Benötigt scp, SSH-Zugriff und passende sudo-Rechte. Es ist ein Upload-Werkzeug, kein allgemeiner bidirektionaler Dateimanager.
Unter „Dateibesitzer und Rechte“ einen Dienstbenutzer für alle Hosts oder je Host wählen. Quickselect und freie Eingabe sind möglich; der Besitzer ist unabhängig vom SSH-Login. Neue Dateien bekommen seine primäre Gruppe und die je Datei gewählten Rechte. 0600 ist der sichere Standard für private Keys/Keystores; 0644 nur für öffentliche Zertifikate verwenden. Vorhandene Dateien behalten ihre Besitzer/Rechte, außer die Änderung ist ausdrücklich angehakt. Die Dateien werden vor dem Einsetzen mit den richtigen Metadaten vorbereitet. Das Formular ist bei kleinen Fenstern scrollbar; die Aktionsbuttons bleiben sichtbar.

Zertifikate ersetzen
Wähle neue lokale Dateien und absolute Whitelist-Suchpfade, beispielsweise /etc/myservice. „Treffer suchen“ sucht ausschließlich in diesen Pfaden nach regulären Dateien mit exakt gleichem Dateinamen. Eine leere Whitelist blockiert die Suche. In der Vorschau bestehende und neue Dateidaten prüfen und die zu ersetzenden Treffer auswählen; erst danach den Austausch bestätigen. Es werden vorhandene Dateien ersetzt, keine beliebigen neuen Zielpfade angelegt.
Such- und Zielpfade dürfen keine '..'-Segmente oder Steuerzeichen enthalten. Breite Pfade wie / oder /etc sind nach einer zusätzlichen Warnung erlaubt; gezielte Unterordner sind empfehlenswert. Die reine Suche startet standardmäßig mit acht parallelen Hosts; „Parallelität begrenzen“ kann je Lauf geändert oder ausgeschaltet werden.
Das optionale Keystore-/P12-Passwort ermöglicht die Prüfung von Zertifikatsdaten in JKS/P12; ohne Passwort werden dort nur Dateizeitstempel angezeigt. Ein optionaler Nach-Befehl (auch aus einem Favoriten) kann anschließend etwa einen Dienst neu starten. „Tab nach Erfolg schließen“ schließt erfolgreiche Terminal-Tabs. Benötigt SSH/scp, passende sudo-Rechte und je nach Format OpenSSL/keytool. Die Aktion verändert Zertifikatsdateien auf den Servern.

Server neu starten
Löst auf den bestätigten Hosts einen Neustart mit sudo aus. Laufende Verbindungen und Dienste werden dabei unterbrochen; ein ausgelöster Neustart lässt sich nicht rückgängig machen. Der Dialog zeigt die Zielhosts und eine maximale Wartezeit. Optional kann eine systemd-Unit angegeben werden, die nach der SSH-Rückkehr geprüft wird. Ohne Unit werden Neustart und SSH-Rückkehr geprüft. Das sudo-Passwort wird für diesen Lauf verwendet und nicht gespeichert.
Standardmäßig starten alle Hosts gleichzeitig. Optional die Anzahl gleichzeitiger Neustarts begrenzen: Ein weiterer Host beginnt erst nach Abschluss oder Timeout der Prüfung eines vorherigen Hosts. „Überwachung stoppen“ verhindert noch wartende Neustarts; bereits ausgelöste Neustarts laufen weiter. Bei mehr als fünf Hosts wird die Anzahl zusätzlich bestätigt. Das Formular ist scrollbar und die Aktionsbuttons bleiben sichtbar.

Einzelhost, Auswahl und Ordner
Die Beschriftung des Kontextmenüs nennt den Geltungsbereich. Im Menü Aktionen und in der Toolbar werden die angehakten Sessions übergeben. Vor dem Start die endgültige Hostliste im jeweiligen Dialog prüfen. Die Hilfe selbst führt keine Serveraktion aus. Neue Fenster dürfen einmal aktiv werden, sperren aber keine anderen App-Fenster. Angezeigten Text mit der Maus ziehen und mit Strg+C kopieren; Esc oder Klick außerhalb beendet die schreibgeschützte Auswahl. Bei verschiebbaren Spaltentiteln Strg beim Ziehen halten."""),
    HelpTopic("restart_templates", "Massen-Neustarts, Dienststatus und Vorlagen", """Vorlagen erstellen
Server links anhaken und Aktionen → Massen-Neustarts öffnen. „Aus Auswahl erstellen“ übernimmt die Server in eine direkt editierbare Tabelle. Benutzer werden aus den aktuellen Verbindungen vorbelegt. Quick-Access-User und „Leere Benutzer füllen“ ergänzen nur fehlende Angaben. Benutzeränderungen gelten ausschließlich für die Vorlage, auch bei SSH-Aliasen.

Serviceprüfungen je Server
Auf einen Dienstnamen oder „Dienste auswählen…“ klicken, auf diesem Server mehrere Dienste lesend durchsuchen und übernehmen. Dienstnamen sind nicht frei editierbar. Sollzustand aktiv/inaktiv wählen; × entfernt einen Dienst. Server oben rechts hinzufügen oder in der Zeile entfernen; Ersetzen und Umsortieren entfallen. Inaktiv bedeutet vorhanden und sauber gestoppt; failed und fehlende Units sind kein erfüllter Sollzustand. Die Prüfung verändert keine Dienste. Eine leere Liste prüft nur Neustart und SSH-Rückkehr.

Speichern und starten
Vorlagen bleiben lokal und sind im App-Backup enthalten. Änderungen lassen sich als neue Vorlage oder durch Überschreiben speichern. Aktuelle Verbindungsdaten werden erneut aufgelöst; fehlende Server entfernen und bei Bedarf neu hinzufügen. Die Startvorschau nennt alle Ziele, Benutzer, Service-Sollzustände und Ablaufoptionen.

sudo-Passwörter
Ohne „Passwort je Verbindung“ gilt das obere sudo-Passwort für alle Server. Mit der Checkbox erscheinen verdeckte Passwortfelder unter den Benutzern. „Leere Passwörter füllen“ übernimmt das obere Passwort ausschließlich in leere Felder; bestehende Einträge bleiben erhalten. Ein leeres Feld bedeutet sudo ohne Passwort, ohne automatischen Rückgriff auf das obere Feld. Beim Wechsel des Modus bleiben die Eingaben erhalten. Beim Entfernen eines Servers wird auch dessen gespeichertes Passwort entfernt.
Passwörter werden beim Speichern der Vorlage mit Windows-DPAPI für dein Windows-Benutzerkonto verschlüsselt. Auch im App-Backup stehen nur verschlüsselte Werte. Auf einem anderen Rechner oder unter einem anderen Konto können die Werte unlesbar sein: betroffene Felder neu eingeben (zum Leeren kurz etwas eingeben und wieder löschen). Unlesbare Werte bleiben beim Laden/Speichern erhalten und blockieren den Start, solange sie im gewählten Modus benötigt werden. Im gemeinsamen Modus kann das Passwort in der Startvorschau nur für diesen Lauf geändert werden. SSH verwendet weiterhin Schlüssel/Agent; die Felder dienen ausschließlich sudo.

Parallel oder nacheinander, mit getrennter Wartezeit für Neustart/SSH und anschließend alle Services eines Servers. Bei Fehlern weiterlaufen, weitere Neustarts stoppen oder pausieren und nachfragen. Eine Pause verhindert weitere Starts; laufende Server werden weiter überwacht. Fehlende Units verhindern bereits vor dem Reboot diesen Server. Nach dem Reboot werden vorübergehend abweichende Zustände bis zum Servicezeitlimit beobachtet.

Alle parallel durchstarten
Die dritte Ablauf-Auswahl startet alle Zielserver ohne Parallelitätsgrenze und ohne Fehlerpause. „Max. gleichzeitig“ und „Bei Fehlern“ sind dabei ausgegraut; ihre Werte bleiben für einen späteren Wechsel erhalten. Die Startvorschau nennt diesen Modus ausdrücklich. Gleichzeitiges Anstoßen bedeutet keine zeitlich exakt synchronen Reboots: SSH-Anmeldung und Vorprüfung benötigen je Server unterschiedlich lange.

Massendienststatus ohne Neustart
Aktionen → Massendienststatus öffnet dieselben gespeicherten Vorlagen mit Servern, Benutzern und Diensten. Alternativ in Massen-Neustarts „Dienststatus prüfen“ drücken. Vorlage auswählen/öffnen, bei Bedarf bearbeiten und speichern, dann per Klick prüfen; es gibt keinen automatischen Zeitplan. Diese Aktion fragt einmalig ausschließlich systemctl show ab. Kein Neustart, kein Dienststart/-stopp, keine sudo-Passwörter und keine Wartephase auf den Sollzustand. Neustartoptionen sind im Statusmanager ausgeblendet.
Die nichtmodale Ergebnistabelle zeigt je Server und Dienst Soll, Ist, Ergebnis und Details. active/inactive/failed und Übergangszustände bleiben unterscheidbar. Abweichungen, fehlende Units und SSH-/Abfragefehler sind gesonderte Ergebnisse. Server ohne Dienste erscheinen als „Keine Dienste hinterlegt“, nicht als erfolgreich geprüft. Alle Dienststatusabfragen laufen ohne künstliche Parallelitätsgrenze gleichzeitig, auch mehrere Dienste desselben Servers. Dies gilt für den Prüfbutton in beiden Vorlagenansichten. „Prüfung abbrechen“ überspringt wartende Abfragen; laufende SSH-Abfragen kehren spätestens nach ihrem Timeout zurück. Ergebnisse bleiben kopierbar offen.
Beide Fenster verwenden dieselbe Vorlagenbibliothek. Änderungen an anderen Vorlagen bleiben erhalten. Wurde die geöffnete Vorlage inzwischen in einem anderen Fenster verändert oder gelöscht, wird Speichern/Prüfen/Neustarten blockiert; unter „Vorlagen“ erneut öffnen. Lokale Änderungen vorher bei Bedarf separat übernehmen.

Ergebnisse
Fortschritts-/Ergebnisfenster und Vorlagenverwaltung sperren das Hauptfenster nicht. Während der Überwachung und nach Abschluss kannst du im SSH-Manager andere Verbindungen oder Fehler-Server auswählen und weitere Aktionen ausführen. Die Ergebnisfenster bleiben dabei offen. Auch Eingaben, Rückfragen und Startbestätigungen bleiben eigenständige Fenster: Das Hauptfenster bleibt bedienbar. Ein Start wartet weiterhin auf die ausdrückliche Bestätigung.
„Alle Fehler kopieren“ enthält Fehler und Zeitüberschreitungen, „Alles kopieren“ die ganze Tabelle mit Überschriften. Strg/Umschalt markiert mehrere Zeilen; „Auswahl kopieren“ oder Strg+C kopiert sie. Einzelne Textstellen unten oder in der vollständigen Detailansicht markieren. Doppelklick öffnet die Details. Hover hebt die ganze Zeile hervor. Nicht gestartete und nicht weiter überwachte Server sind keine bestätigten Erfolge oder Fehler."""),
    HelpTopic("sshkeys", "SSH-Keys übertragen und entfernen", """SSH Key übertragen
Überträgt einen öffentlichen SSH-Key auf die ausgewählten Hosts, damit spätere Anmeldungen mit dem passenden privaten Schlüssel möglich sind. Wähle die öffentliche Schlüsseldatei und den Benutzer im Dialog. Erfordert zunächst eine funktionierende Anmeldung und Schreibrechte auf die SSH-Autorisierung des Benutzers. Ein privater Schlüssel bleibt lokal.

SSH Key entfernen
Entfernt den ausgewählten Schlüssel aus der Autorisierung des Remote-Benutzers. Dadurch kann der zugehörige private Schlüssel den Zugriff verlieren. Prüfe Benutzer, Hosts und Schlüssel; stelle sicher, dass eine andere Anmeldung möglich bleibt. Der lokale private Schlüssel wird durch diese Aktion nicht gelöscht.

Geltungsbereich
Die Kontextmenüs bieten Einzelhost- und Auswahlaktionen entsprechend den unterstützten Sessiontypen. Die Aktion verändert die SSH-Zugangsberechtigung auf den Servern, nicht nur eine Einstellung im SSH-Manager."""),
    HelpTopic("settings", "Suche, Ansicht und Einstellungen", """Toolbar-Schnellauswahl
Unter Einstellungen → Toolbar steht jede Menüaktion als einzelner optionaler Button bereit: Diagnose/Vollscan, beide Skriptmodi, alle Dienstaktionen, Upload, DNS, Exporte, App-Werkzeuge und die Aktionen für den fokussierten Eintrag. Neue Buttons sind zunächst abgewählt. Die Auswahl wirkt sofort; Speichern übernimmt sie dauerhaft. Bei schmalen Fenstern stehen überzählige Buttons unter Mehr. Aktionen verwenden dieselben Zielregeln wie ihr Menü; gesperrte Aktionen erklären den fehlenden Fokus oder die nötige Häkchen-Auswahl.

Suche und Suchverlauf
Das Suchfeld filtert die Hauptansicht live nach Name, Hostname und Ordnerpfad, ohne Beachtung der Groß-/Kleinschreibung. Es sucht nicht nach Port oder Notiztext. Strg+F (Standard) setzt den Fokus hinein. Leeren zeigt wieder die normale Ansicht. Der Verlauf-Button übernimmt frühere Suchbegriffe; „Verlauf leeren“ entfernt den gespeicherten Suchverlauf. Hauptsuche und Befehlspalette sind unterschiedliche Suchoberflächen.

Toolbar und Quellen
Einstellungen steuern sichtbare Toolbar-Aktionen und Datenquellen einschließlich Favoriten/Zuletzt verwendet. Bei wenig Platz liegen Toolbar-Aktionen im „Mehr“-Überlauf. Eine ausgeblendete Quelle wird nicht gelöscht.

Spalten
Benutzer, Hostname, Port und Notizen sind ein-/ausblendbar. Sichtbare Datenspalten können per Drag & Drop umgeordnet werden. Name bleibt als Baumspalte links. Das Ausblenden ändert nur die Ansicht.

Darstellung
Theme, Akzentfarbe, UI-/Baumschrift und Zeilenhöhe passen die Darstellung an. Einstellungen wirken auf die entsprechenden UI-Bereiche live.

Terminal und Benutzer
Windows Terminal ist das Standardziel; Herdr ist optional und muss installiert sein. Die Terminal-Einstellungen steuern unter anderem Profil, Farben und Titel. Schnellauswahl-Benutzer und Standardbenutzer vereinfachen die Anmeldung.

Start, Import und Prüfzeit
Beim Start können Ordner aufgeklappt, eingeklappt oder mit dem gemerkten Zustand angezeigt werden. Die Wartezeit für Hosts prüfen begrenzt den TCP-Verbindungsversuch. Importoptionen steuern die Übernahme von WinSCP-/FileZilla-Benutzern. Die WinSCP-Einstellung bestimmt das Öffnen in Tabs oder Fenstern.

Einstellungen zurücksetzen
Stellt die Einstellungsdefaults wieder her. „Ansicht auf Startzustand zurücksetzen“ leert die Suche und stellt Ordner und Farben vom App-Start wieder her; „Farben zurücksetzen“ entfernt Farbzuordnungen. Diese Aktionen löschen keine Verbindungen.

Hilfe
F1 (Standard), Hilfe → Hilfe öffnen oder „Hilfe öffnen“ in der Palette öffnet dieses Fenster. Du kannst es neben dem Hauptfenster verwenden. Themen und Suchtext bleiben beim erneuten Aufrufen erhalten."""),
    HelpTopic("data", "Kopieren, Export, Import und App-Daten", """Kopieren
Das Kontextmenü kopiert SSH-Befehl, Hostname, Name oder Notiz einer Session. Die Auswahlvarianten kopieren die entsprechenden Werte mehrerer angehakter Sessions; Ordneraktionen die enthaltenen Sessions. „Angezeigte Verbindungen als Markdown kopieren“ im Menü Aktionen kopiert die aktuell dargestellten Verbindungen als Tabelle.

CSV und Excel
„Angezeigte Verbindungen als CSV/Excel exportieren“ exportiert die sichtbaren Verbindungen. Filter und Quellenanzeige beeinflussen den Inhalt. Nutze es für Listen und Dokumentation; es ist kein vollständiges Backup aller Einstellungen und Quellen.
Bei CSV ist „Excel-sicher“ standardmäßig aktiv: Mögliche Formeln werden durch ein vorangestelltes Apostroph als Text exportiert. Für unveränderte Rohdaten den Haken entfernen; solche CSVs können beim Öffnen in Excel Formeln ausführen. XLSX verwendet bereits Textzellen.

Einstellungen exportieren/importieren
Öffne zuerst die Einstellungsansicht: Die Import-/Exportaktionen verwenden diese Ansicht. Export schreibt die App-Einstellungen in eine Datei. Import übernimmt Einstellungen aus einer passenden Datei. Das ist kein Import beliebiger CSV/Excel-Verbindungslisten. Externe WinSCP-, FileZilla- und SSH-Config-Quellen müssen separat gesichert werden.

App-Daten und Backup
Unter %APPDATA%/SSH-Manager liegen settings.json (Einstellungen), ui_state.json (Ansicht, Suchverlauf, Favoriten, Benutzerzuordnungen und Runner-Daten), app_sessions.json (eigene Sessions und Alias-Kopien) und notes.json (Notizen). Für ein vollständiges lokales Backup diese Dateien bei geschlossener App sichern und verwendete externe Quellen zusätzlich sichern.

JSONs in VS Code öffnen
Datei → JSONs in VS Code öffnen öffnet die App-Datendateien im Editor. Benötigt VS Code. Direkte Änderungen erfordern gültiges JSON; vor manuellen Änderungen eine Sicherung erstellen. Repository-Dateien sind nicht die persönlichen Verbindungsdaten."""),
)


def shortcut_table(mapping: dict[str, str]) -> str:
    return "\n".join(
        f"{label}: {mapping.get(action, default) or 'Nicht belegt'}  (Standard: {default or 'Nicht belegt'})"
        for action, label, default in DEFAULT_ACTION_ORDER
    )


TOPIC_ADDITIONS = {
    "start": "Auswahl prüfen\nDie Auswahlleiste nennt auch ausgeblendete Suchziele. ‚Auswahl prüfen‘ zeigt alle angehakten Hosts und erlaubt gezieltes Entfernen. Suche und Filter leeren keine bestehenden Häkchen. ‚Auswahl leeren‘ entfernt auch verborgene Häkchen.",
    "sources": "Quellenstatus und Übernahme\nDatei → Quellenstatus zeigt den letzten Leseversuch, Dauer, Anzahl und Hinweise. Fehlende Quelle, vorhandene leere Quelle und Lesefehler sind verschiedene Zustände. Nur die gewählte Quelle neu laden liest die anderen Quellen nicht erneut. Bei Fehlern bleibt deren letzter nutzbarer Stand sichtbar. WinSCP-/FileZilla-Übernahme erzeugt eine eigene App-Kopie der Verbindungsdaten und App-Notiz; Zugangsdaten werden nicht kopiert. Aliasübernahme bleibt von ~/.ssh/config abhängig.",
    "organize": "Details und Rückgängig\nDas zuschaltbare Detailpanel folgt der Fokuszeile und nennt Quelle sowie Benutzerherkunft. Ctrl+Z (Standard) oder Datei → Lokale Änderung rückgängig stellt lokale Verbindungen, Notizen, Farben und zugehörige App-Metadaten wieder her. Mehrere Änderungen einer Sammelaktion zählen als ein Schritt. Bis zu 20 Schritte bleiben während der App-Sitzung verfügbar; nach Neustart ist der Verlauf leer. Remote-Aktionen und externe Quelldateien werden nicht rückgängig gemacht.",
    "remote": "Drei Aufgaben\nAktionen → Remote-Befehl ausführen, Lokales Skript ausführen und Serverskript ausführen öffnen getrennte Aufgaben. Ein gespeicherter Eintrag wechselt die Aufgabe nicht still. Vor-/Nach-Befehle erscheinen erst unter ‚Erweiterter Ablauf‘. Gespeicherte Runbooks werden in Aktionen → Runbook-Bibliothek verwaltet. Eingabeparameter werden vor der Ausführung abgefragt; Geheimwerte bleiben außerhalb des Verlaufs.",
    "server": "Einfacher Upload und Dienstwerkzeuge\n‚Datei hochladen‘ verwendet genau einen Host, eine Datei und einen beschreibbaren Zielordner, ohne sudo, Rechteeditor oder Folgebefehl. Neue Dateien sind nur für den Benutzer zugänglich; bei Überschreiben bleiben bestehende Besitzer/Rechte erhalten. ‚Dateien verteilen‘ ist der Mehrzielablauf mit expliziten Rechten/sudo. Dienststatus, Dienstneustart und Dienstlogs sind separate Aktionen; ein Dienstneustart startet keinen Server neu.",
    "data": "Verbindungsliste oder App-Backup\nCSV/XLSX exportiert die aktuelle Ansicht, die vollständige Häkchen-Auswahl oder alle geladenen Verbindungen. Ein Listenexport ist kein Backup. Datei → App sichern enthält Einstellungen, eigene Sessions/Alias-Einträge, App-Notizen und UI-State. WinSCP, FileZilla, SSH Config und SSH-Schlüssel sind nicht enthalten. Wiederherstellen zeigt eine Vorschau und legt vorher ein Sicherheitsbackup an. Danach muss die App neu gestartet werden.",
}
TOPICS = tuple(HelpTopic(topic.id, topic.title, topic.body + ("\n\n" + TOPIC_ADDITIONS[topic.id] if topic.id in TOPIC_ADDITIONS else "")) for topic in TOPICS) + (
    HelpTopic("runbooks", "Runbook-Bibliothek", """Verwalten und ausführen
Aktionen → Runbook-Bibliothek öffnet gespeicherte Befehle und Skripte. Suchen, Inhalt bearbeiten, Name/Notiz pflegen, Parameter definieren, anpinnen oder löschen sind lokale Verwaltungsaktionen. ‚Neu‘ bestimmt genau eine Aufgabe. Bis zu 25 Einträge sind möglich.

Ausführen
Zuerst einen Eintrag auswählen und im Hauptfenster Zielhosts anhaken. ‚Ausführen‘ übernimmt das Runbook in den passenden Aufgabendialog. Eingaben, Benutzer und aktuelle Hostliste prüfen; die endgültige Vorschau muss bestätigt werden. Verwalten startet keine Remote-Aktion."""),
    HelpTopic("parameters", "Runbook-Eingabeformulare", """Parameter definieren
In der Bibliothek ‚Parameter‘ öffnen. Jeder Parameter hat einen Namen, eine Beschriftung, einen Typ, optional einen Standard und ein Pflichtfeld. Namen bestehen aus Großbuchstaben, Ziffern und Unterstrichen. Text, ganze Zahl, Port, absoluter Pfad und Auswahlliste werden geprüft.

Im Runbook verwenden
Parameter stehen als Umgebungsvariablen RUNBOOK_NAME zur Verfügung. Beispiel: Name SERVICE wird im Befehl als "$RUNBOOK_SERVICE" gelesen. Werte werden als Daten sicher gequotet, nicht durch Text-Ersetzung in Befehle eingesetzt.

Geheimwerte
Geheimfelder haben keinen gespeicherten Standard. Werte werden erst für diesen Lauf eingegeben, in der Vorschau verborgen und nicht in Favoriten/History gespeichert. Lokal erzeugte Skriptinhalte sind benutzergebunden geschützt. Remote-Befehle müssen selbst vermeiden, Geheimwerte auszugeben."""),
    HelpTopic("filters", "Gespeicherte Filter und Ansichten", """Ansicht eingrenzen
‚Filter / Ansichten‘ kombiniert Quelle, Ordner, Benutzer und Port mit der Hauptsuche. Ordner und Benutzer werden als Teiltext gesucht; Port und Quelle als genaue Werte. Es erscheinen nur bereits aktivierte Quellen.

Ansicht speichern
Einen Namen eingeben und die Kriterien speichern. Laden übernimmt deren Suchtext/Kriterien, Anwenden setzt den Filter im Baum. Eine benannte Ansicht kann gelöscht werden. Aktive Kriterien werden oberhalb des Baums angezeigt; Zurücksetzen entfernt sie. Häkchen für ausgeblendete Ziele bleiben bestehen. Temporär geöffnete Trefferordner verändern den gemerkten normalen Ordnerzustand nicht."""),
    HelpTopic("tunnels", "Tunnel nach Anwendungsfall", """Dienst auf dem SSH-Server
Direkter Zugriff leitet localhost:LOKALPORT auf deinem PC zum Zielport auf localhost des SSH-Servers. Kein interner Zielserver ist nötig.

Interner Dienst über SSH-Server
Der SSH-Server erreicht den eingegebenen internen Zielserver. Dieser ist ausdrücklich erforderlich. Die Vorschau zeigt PC → SSH-Server → Ziel.

Ports und Laufzeit
Vorgaben setzen lokale und Zielports; danach sind beide frei editierbar. Unter Einstellungen → Tunnel / Dienste lassen sich Vorgaben bearbeiten, hinzufügen oder entfernen (Name | lokaler Port | Zielport je Zeile). Der lokale Port muss frei sein. Das Terminal hält den Tunnel offen; beende dessen SSH-Prozess zum Schließen. Es gibt hier keine Reverse-Tunnel oder SOCKS-Proxys."""),
    HelpTopic("diagnosis", "Verbindungsdiagnose", """Getrennte Schritte
Lokaler SSH-Client, Aliasauflösung, DNS und TCP werden unabhängig beurteilt. Ein offener Port bestätigt keine Anmeldung. Bei konfiguriertem Proxy wird ein direkter TCP-Test zum Ziel ausgelassen, weil er den Proxy umgehen würde.

DNS und zusätzliche Ports
Namensauflösung übersetzt einen DNS-Hostnamen in IP-Adressen. Bei einer eingetragenen IP-Adresse ist sie nicht nötig. Zusätzliche TCP-Ports als Liste oder Bereich angeben, z. B. 80,443,8000-8010. Es gibt kein 64-Port-Limit. Je mehr Ports, desto länger dauert die Diagnose. Der SSH-Port bleibt automatisch dabei. Zusätzliche Ports werden direkt von deinem Rechner aus geprüft, auch bei einem SSH-Proxy. Es gibt keinen UDP-Test. Timeout/Ablehnung ist kein sicherer Beleg für einen geschlossenen Port; auch Netzwerkregeln können den Zugriff verhindern.

Diagnose-Ports merken
Gültige Eingaben werden appweit in ui_state.json gespeichert, auch beim Schließen ohne gestartete Diagnose. Sie stehen beim nächsten Host und nach App-Neustart wieder im Feld. Leeren entfernt die Vorgabe. Ungültige/unvollständige Eingaben ersetzen die letzte gültige Vorgabe nicht. Externe Verbindungsquellen bleiben unverändert.

Alle TCP-Ports prüfen – dauert sehr lange
Dieser eigene Einstieg öffnet einen Vollscan für Ports 1–65535. Erst ‚Vollscan starten‘ beginnt die Prüfung. Jede aufgelöste IPv4-/IPv6-Adresse wird separat angezeigt, direkt vom PC und ohne SSH-Proxy. Standardmäßig werden Ziel-IPs nacheinander geprüft; die Zielparallelität ist änderbar oder abschaltbar. Standard: maximal 50 Verbindungsstarts pro Sekunde, 64 gleichzeitige Verbindungen und 1 Sekunde Timeout. Ziel-IP-Parallelität, Portparallelität und Startsrate sind separat je Lauf einstellbar oder abschaltbar. Ohne Häkchen entfällt die jeweilige Begrenzung; der Timeout bleibt bei 0,5–5 Sekunden einstellbar. Bei 50/s dauert ein vollständiger Scan mindestens ca. 22 Minuten je IP, bei Timeouts länger. Fortschritt und offene Ports erscheinen laufend. Abbrechen oder Schließen stoppt neue Prüfungen; laufende enden nach dem Timeout. Abbruch bleibt ausdrücklich ein Teilergebnis.

Der Scan stellt kurze TCP-Verbindungen her, schickt keine Nutzdaten und meldet sich nicht an. Er kann Logeinträge, Sicherheitsalarme oder Sperren auslösen und empfindliche Dienste beeinträchtigen; nur im dafür vorgesehenen Zielnetz verwenden. ‚Offen‘ bedeutet ausschließlich vom eigenen Rechner erreichbar, keine Aussage über Diensttyp oder Anmeldung. Timeouts/Netzwerkfehler sind gesondert gezählt und beweisen keine geschlossenen Ports. UDP und lokale Listener, die vom PC nicht erreichbar sind, werden damit nicht festgestellt.

Fallback-Benutzer und Quickselect
Bei einer normalen Host-Verbindung ohne fest eingetragenen Benutzer nutzt die optionale SSH-Anmeldung den Fallback-Benutzer. Ein fester Benutzer hat Vorrang; ein SSH-Alias verwendet seine SSH-Konfiguration. DNS und TCP benötigen keinen Benutzer. Die in den Einstellungen konfigurierten Quick-Select-Benutzer stehen direkt unter dem Feld als Buttons. Ein Klick ändert nur den Fallback des aktuellen Diagnosedialogs, keine Verbindungsdaten.

Optionale Anmeldung
Die zusätzliche SSH-Anmeldung muss ausdrücklich aktiviert werden. Sie verwendet vorhandene Schlüssel ohne Passwortabfrage, führt nur true aus und verändert keine bekannten Hostschlüssel. Unbekannte Hostschlüssel führen zu Fehlern. Feste Benutzer und SSH-Aliase haben Vorrang vor dem Fallback-Benutzer. Standardmäßig acht Ziele werden parallel geprüft. „Parallelität begrenzen“ ist je Lauf änderbar oder abschaltbar."""),
    HelpTopic("port_checks", "Portfreigabe von Servern prüfen", """Server → Ziel
Quellserver anhaken, dann Aktionen → Portfreigabe prüfen… öffnen. Die vollständige Häkchenauswahl gilt, auch bei aktiver Suche. Jeder Quellserver prüft alle Ziel-IP/Port-Kombinationen direkt von dort aus. Standardmäßig acht Quellserver arbeiten parallel. „Parallelität begrenzen“ lässt sich je Lauf ändern oder ausschalten; Wiederholen verwendet die ursprüngliche Auswahl dieses Laufs. Im Gegensatz zur Verbindungsdiagnose wird nicht vom eigenen PC aus geprüft. Die Quellliste wird beim Öffnen festgehalten; ein neuer Aufruf übernimmt die neue Häkchenauswahl.

Ziele und Prüfvorlagen
Ziel-IP oder Hostname und TCP-Port frei eingeben. „Server suchen…“ durchsucht alle geladenen Verbindungen nach Name, Host/IP, Ordner und Quelle. Übernehmen oder Doppelklick trägt den Zielhost ein; der gewählte TCP-Port und die Quellserver-Häkchen bleiben unverändert. SSH-Aliase werden lokal mit ssh -G ausgewertet; der tatsächliche Host wird übernommen, kein Tunnel. Hostnamen werden erst auf jedem Quellserver aufgelöst. Benannte Vorlagen speichern nur Zieladressen und Ports und sind im App-Backup enthalten. Laden und Speichern starten keine Prüfung.

Startvorschau und Mausrad
Schon vor dem Start zeigt die untere Liste jede geplante Quellserver-/Ziel-Kombination als „Noch nicht geprüft“, einschließlich Benutzer. Ziel-/Port-/Benutzeränderungen und das Laden einer Vorlage aktualisieren die Vorschau ohne SSH; bisherige Ergebnisse werden dabei durch die neue Vorschau ersetzt. Unvollständige Zeilen bleiben sichtbar und müssen vor dem Start vervollständigt werden. Das Mausrad scrollt die obere Zielliste auch über Eingabefeldern und Buttons. Entfernen ist bei jeder Zeile rot mit Papierkorb-Icon.

Quick-Access-Benutzer
Die konfigurierten Quick-Access-Benutzer stehen als Buttons am Fallback-Feld. Ein Klick setzt nur den Benutzer dieses Laufs, verändert keine gespeicherten Verbindungen und überschreibt keine festen Benutzer oder SSH-Aliasregeln. Während der Prüfung sind die Buttons gesperrt; laufende Prüfungen behalten ihre Laufdaten.

Anmeldung und Voraussetzungen
Nur Linux-/Ubuntu-Quellserver mit SSH-Schlüssel/Agent ohne Passwortabfrage. Feste Benutzer haben Vorrang vor dem Fallback, SSH-Aliase verwenden ihre SSH-Konfiguration. Bekannte Hostschlüssel sind erforderlich; unbekannte werden nicht automatisch akzeptiert. Vorhandenes Python 3 wird bevorzugt; sonst OpenBSD-netcat mit timeout, für Hostnamen zusätzlich getent. Nichts wird installiert oder dauerhaft auf den Server geschrieben. Die tatsächliche Quell-IP hinter Routing/NAT kann von der SSH-Verwaltungsadresse abweichen.

Ergebnisse und Abbruch
Erreichbar bestätigt nur den TCP-Verbindungsaufbau, keine Dienstanmeldung. Abgelehnt, Timeout, Netzwerk-/DNS-Fehler und ungeprüfte SSH-/Werkzeugprobleme bleiben getrennt. Kein negatives Ergebnis beweist eine fehlende Firewallregel. Ergebnisse sind nach Ziel aufklappbar; Filter ändern nur die Anzeige. Alles/Fehler kopieren verwendet vollständige Ergebnisse auch außerhalb des Filters; Auswahl kopieren nimmt ausgewählte Zeilen oder die ausgewählte Zielgruppe. Vollständige Details sind unten als markierbarer Text verfügbar. Angezeigte Ziel-IPs stammen vom Quellserver. Abbrechen oder Schließen beendet weitere Prüfungen und laufende lokale SSH-Prozesse; ausstehende Kombinationen werden nicht als Portfehler gezählt. Negative erneut prüfen wiederholt nach Bestätigung nur belegte negative Kombinationen mit den ursprünglichen Laufdaten."""),
    HelpTopic("services", "Dienststatus, Neustart und Logs", """Vorgaben bearbeiten
Unter Einstellungen → Tunnel / Dienste kannst du die Dienstliste bearbeiten, erweitern oder leeren (ein Dienstname je Zeile). Freie Dienstnamen und der Serverbrowser bleiben verfügbar.

Eine Aufgabe pro Aktion
Dienststatus zeigt den systemd-Status; ein inaktiver Dienst ist eine erfolgreich abgefragte Information. Dienstneustart startet ausschließlich die gewählte Unit und prüft danach ihren aktiven Zustand. Dienstlogs zeigt eine begrenzte Zahl der letzten journalctl-Zeilen, ohne dauerhaften Live-Stream.

Ziele und Rechte
Hosts im Hauptfenster anhaken, Dienstnamen und sudo-Bedarf wählen, Vorschau prüfen. sudo ist für Neustarts vorbelegt und explizit änderbar. Ein optionales Passwort gilt nur für diesen Lauf. Die Werkzeuge setzen systemd/journalctl auf dem Zielhost voraus.

Dienst auswählen
Die freie Eingabe bleibt erhalten. ‚Dienste auf einem Host durchsuchen‘ öffnet rechts eine lesende SSH-Abfrage mit Suche. Wähle ausdrücklich den Referenzhost. Nur dieser Host wird durchsucht; dieselbe Unit muss auf allen Zielhosts vorhanden sein. Jede Ausführung prüft das je Host und meldet fehlende Units als ‚Dienst wurde nicht gefunden‘ im Terminal und Sammelergebnis."""),
    HelpTopic("results", "Ergebnisse von Sammelaktionen", """Belegter Abschluss
‚Terminal gestartet‘ bestätigt nur den Start. ‚Läuft‘ stammt aus dem gestarteten Skript. Erfolg/Fehler basiert auf dem Exit-Code des Remote-Aufrufs bzw. Upload-Ablaufs. Der Nachweis erscheint vor einem anschließenden interaktiven Terminal. Ohne Rückmeldung bleibt der Status unbekannt; das Schließen der Übersicht stoppt keine Aufgabe.

Erneut vorbereiten
Nur bestätigte fehlgeschlagene Hosts werden übernommen, nach zusätzlicher Bestätigung und erneuter Vorschau. Erfolgreiche oder unbekannte Hosts sind ausgeschlossen. Auch ein fehlgeschlagener Ablauf kann Teilschritte verändert haben. Dateien, Schlüssel und Rechte erneut wählen/prufen; Geheimwerte erneut eingeben. ‚Letzte Sammelergebnisse‘ öffnet die jüngste unterstützte Aktion dieser App-Sitzung.

Geltungsbereich
Remote-Befehle/Skripte, Dienstaktionen, Upload/Verteilung, Zertifikatstausch und SSH-Key-Aktionen liefern Rückmeldungen. Serverneustarts haben ihre eigene bestehende Überwachung. Interaktive Verbindungen und Tunnel werden nicht als abgeschlossene Remote-Aufträge bewertet."""),
)


def topic_body(topic: HelpTopic, mapping: dict[str, str]) -> str:
    return topic.body.replace("{shortcuts}", shortcut_table(mapping))


def search_topics(query: str, mapping: dict[str, str]) -> list[HelpTopic]:
    words = query.casefold().split()
    return [topic for topic in TOPICS if all(
        word in (topic.title + "\n" + topic_body(topic, mapping)).casefold()
        for word in words
    )]


def open_help(app, topic_id=None):
    window = getattr(app, "_help_window", None)
    if window is None or not window.winfo_exists():
        window = HelpWindow(app)
        app._help_window = window
    window.deiconify()
    window.lift()
    window.refresh()
    window.search_entry.focus_set()
    if topic_id is not None:
        window.show_topic(topic_id)
    return window


class HelpWindow(AppWindow):
    """Nonmodal help with a separate shortcut boundary."""
    _blocks_app_shortcuts = True

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("SSH Manager – Hilfe")
        self.geometry("1000x720")
        self.minsize(680, 440)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", self.close)
        self.bind("<FocusIn>", self._on_focus, add="+")
        self.mapping = default_shortcuts()
        self.filtered: list[HelpTopic] = []
        self.selected_id = "start"
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        build_dialog_header(frame, "Hilfe zum SSH-Manager", "Bedienung, Tastatur und Aktionen – offline nachschlagen.")
        search = ttk.Frame(frame)
        search.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="Hilfe durchsuchen:").grid(row=0, column=0, padx=(0, 10))
        self.query = tk.StringVar()
        self.search_entry = ttk.Entry(search, textvariable=self.query)
        self.search_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(search, text="Leeren", command=lambda: self.query.set("")).grid(row=0, column=2, padx=(10, 0))
        pane = ttk.Panedwindow(frame, orient="horizontal")
        pane.grid(row=2, column=0, sticky="nsew")
        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=1)
        pane.add(right, weight=3)
        self.topics = ttk.Treeview(left, show="tree", selectmode="browse", height=12)
        self.topics.column("#0", width=250, minwidth=170)
        topic_scroll = ttk.Scrollbar(left, command=self.topics.yview)
        self.topics.configure(yscrollcommand=topic_scroll.set)
        topic_scroll.pack(side="right", fill="y")
        self.topics.pack(fill="both", expand=True)
        self.text = tk.Text(right, wrap="word", state="disabled", width=60, padx=16, pady=12, relief="flat", borderwidth=0)
        scroll = ttk.Scrollbar(right, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        footer = ttk.Frame(frame)
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.status = ttk.Label(footer, style="Muted.TLabel")
        self.status.pack(side="left")
        ttk.Button(footer, text="Schließen", command=self.close).pack(side="right")
        self.topics.bind("<<TreeviewSelect>>", self._select_topic)
        self.query.trace_add("write", lambda *_: self._filter())
        self.refresh()

    def close(self, _event=None):
        self.app._help_window = None
        self.destroy()
        return "break"

    def show_topic(self, topic_id):
        if topic_id not in {topic.id for topic in TOPICS}:
            raise ValueError("Unbekanntes Hilfethema.")
        self.selected_id = topic_id
        self.query.set("")
        self._filter()
        self.text.yview_moveto(0)

    def _on_focus(self, event):
        if event.widget is self:
            self.refresh()

    def refresh(self):
        manager = getattr(self.app, "_shortcut_manager", None)
        self.mapping = manager.current_mapping() if manager else default_shortcuts()
        appearance = self.app.settings.appearance
        palette = palette_for_theme(appearance.theme)
        self.configure(background=palette.bg)
        font = ttk.Style(self).lookup("TLabel", "font") or "TkDefaultFont"
        self.text.configure(background=palette.surface, foreground=palette.text,
                            selectbackground=palette.selected, selectforeground=palette.text, font=font)
        self.text.tag_configure("title", font=(appearance.ui_font_family, appearance.ui_font_size + 4, "bold"), spacing3=14)
        self.text.tag_configure("heading", font=(appearance.ui_font_family, appearance.ui_font_size, "bold"), spacing1=8, spacing3=5)
        self._filter()

    def _filter(self):
        self.filtered = search_topics(self.query.get(), self.mapping)
        self.topics.delete(*self.topics.get_children())
        for topic in self.filtered:
            self.topics.insert("", "end", iid=topic.id, text=topic.title)
        self.status.configure(text=f"{len(self.filtered)} von {len(TOPICS)} Themen")
        if self.filtered:
            ids = {topic.id for topic in self.filtered}
            selected = self.selected_id if self.selected_id in ids else self.filtered[0].id
            self.topics.selection_set(selected)
            self.topics.focus(selected)
            self._select_topic()
        else:
            self._render("Keine Treffer", "Kein Hilfethema passt zur Suche. Versuche einen anderen Begriff oder leere die Suche.")

    def _select_topic(self, _event=None):
        selected = self.topics.selection()
        if not selected:
            return
        self.selected_id = selected[0]
        topic = next(topic for topic in self.filtered if topic.id == self.selected_id)
        self._render(topic.title, topic_body(topic, self.mapping))

    def _render(self, title: str, body: str):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", title + "\n", "title")
        for paragraph in body.split("\n\n"):
            lines = paragraph.split("\n", 1)
            if len(lines) == 2:
                self.text.insert("end", lines[0] + "\n", "heading")
                self.text.insert("end", lines[1] + "\n\n")
            else:
                self.text.insert("end", paragraph + "\n\n")
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)
