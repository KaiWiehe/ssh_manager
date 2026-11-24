# SSH-Manager installieren – Kais Script-Betrieb

Diese Anleitung beschreibt meinen Start über **Git Bash**, mit einer lokalen
Python-Umgebung und den Kürzeln **`ssh_manager`** und **`sshm`**. Dafür ist kein
EXE-Build nötig. Der optionale EXE-Bau steht ganz am Ende.

Projektordner unter Windows: `C:\dev\New_Git_Work\SSH-Manager`.
In Git Bash ist derselbe Ordner `/c/dev/New_Git_Work/SSH-Manager`.

## 1. Voraussetzungen

- Windows mit **Python 3.14, 64 Bit**, einschließlich `pip`, `venv` und Tkinter.
  Die vorhandene Projektumgebung verwendet Python 3.14.7.
- **Git für Windows**, einschließlich Git Bash und SSH.
- **Windows Terminal** mit einem Profil namens **Git Bash** für die
  Standard-Terminalstarts der grafischen App.
- Optional WinSCP bzw. FileZilla, wenn deren gespeicherte Verbindungen angezeigt
  werden sollen. SSH-Aliase kommen aus `~/.ssh/config`.

Herdr ist als alternatives Terminalziel möglich. Meine lokal gespeicherte
SSH-Manager-Einstellung ist derzeit **Windows Terminal**, Profil **Git Bash**.
Die Shell-Kürzel unten funktionieren auch in Git Bash innerhalb von Herdr.

Alle folgenden Befehle sind für **Git Bash**, bis zum ausdrücklich als
PowerShell gekennzeichneten EXE-Abschnitt. Jeden Schritt nur fortsetzen, wenn
der vorherige erfolgreich war.

## 2. Projekt herunterladen

Nur bei einer neuen Installation:

```bash
mkdir -p /c/dev/New_Git_Work
cd /c/dev/New_Git_Work
git clone https://github.com/KaiWiehe/ssh_manager.git SSH-Manager
cd SSH-Manager
```

Ist der Projektordner schon vorhanden, direkt dorthin wechseln und nicht erneut
klonen:

```bash
cd /c/dev/New_Git_Work/SSH-Manager
```

Alternativ das Repository als ZIP herunterladen und vollständig in diesen Ordner
entpacken. Dort müssen unter anderem `ssh_manager.py`, `sshm.py`,
`requirements.txt` und `ssh_manager_app/` liegen. Die späteren Git-Updates
funktionieren nur bei einem Git-Klon.

## 3. Python-Umgebung einrichten

Bei einer neuen Installation einmalig:

```bash
py -3.14 --version
py -3.14 -m venv .venv
```

Wenn `py` fehlt, aber `python --version` die gewünschte Python-3.14-Installation
zeigt, stattdessen `python -m venv .venv` verwenden. Die vorhandene `.venv` auf
meinem Rechner weiterverwenden; sie muss für diese Anleitung nicht neu angelegt
werden. Auf einem anderen Rechner eine eigene `.venv` erstellen, keine kopieren.

Laufzeit-Abhängigkeiten installieren und prüfen:

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m pip check
./.venv/Scripts/python.exe -c 'import tkinter, ttkbootstrap, PIL, prompt_toolkit, wcwidth; print("Laufzeitimporte OK")'
```

Eine Aktivierung mit `activate` ist nicht erforderlich. Die folgenden Aufrufe
verwenden immer direkt Python aus der Projektumgebung. Für den Script-Betrieb
werden nur die Pakete aus `requirements.txt` benötigt.

## 4. Beide Varianten direkt starten

Grafische Oberfläche:

```bash
./.venv/Scripts/python.exe ssh_manager.py
```

Terminalsuche:

```bash
./.venv/Scripts/python.exe sshm.py
```

Die GUI läuft bis zum Schließen im aufrufenden Terminal. Die CLI öffnet die
Verbindung im aktuellen Terminal und kehrt nach SSH-Ende zur aufrufenden Shell
zurück. Für die interaktive Suche ein normales Terminal verwenden.

## 5. Meine Kürzel dauerhaft einrichten

Die Definitionen stehen in **`C:\Users\Kai\.bashrc`**, in Git Bash **`~/.bashrc`**.
Datei beispielsweise mit VS Code öffnen:

```bash
code ~/.bashrc
```

Alternativ mit einem vorhandenen Texteditor öffnen. Die folgenden Definitionen
einmal eintragen bzw. vorhandene Definitionen dieser beiden Namen gezielt
ersetzen; den übrigen Inhalt der Datei erhalten:

```bash
alias ssh_manager='"/c/dev/New_Git_Work/SSH-Manager/.venv/Scripts/python.exe" "/c/dev/New_Git_Work/SSH-Manager/ssh_manager.py"'

sshm() {
  "/c/dev/New_Git_Work/SSH-Manager/.venv/Scripts/python.exe" \
    "C:/dev/New_Git_Work/SSH-Manager/sshm.py" "$@"
}
```

Das sind die lokal vorhandenen Definitionen: `ssh_manager` ist ein Alias,
`sshm` eine Bash-Funktion. Die **Alias-Zeile muss vollständig auf einer Zeile
stehen**. In der Funktion erhält `"$@"` alle Suchargumente, auch mit Leerzeichen.
Durch die absoluten Pfade funktionieren beide Kürzel aus jedem Ordner.
Bei einem anderen Projektordner beide Definitionen entsprechend anpassen.

Meine `~/.bash_profile` lädt `~/.bashrc` bereits. Falls dies auf einem neuen
Rechner fehlt, diese Zeile einmal in `~/.bash_profile` ergänzen:

```bash
test -f ~/.bashrc && . ~/.bashrc
```

Definitionen in der aktuellen Git Bash neu laden und kontrollieren:

```bash
source ~/.bashrc
type ssh_manager
type sshm
sshm --version
```

`type ssh_manager` muss den Alias und `type sshm` die Funktion anzeigen.
`sshm --version` muss die aktuelle Projektversion ausgeben. Die Namen gelten
in Git Bash; eine PowerShell-Sitzung liest diese Bash-Dateien nicht.

## 6. Täglich benutzen

```bash
ssh_manager           # Grafische Oberfläche öffnen
sshm                  # Terminalsuche öffnen
sshm web              # Suche mit Starttext "web"
sshm web produktion   # Suche mit mehreren Suchwörtern
```

Die Suchwörter wählen noch keine Verbindung automatisch aus. Im Picker mit
**Enter** verbinden; **F4** fragt einen Benutzer nur für diese Verbindung ab.
**F5** kopiert den Hostnamen, **Esc** bzw. **Strg+C** beendet die Suche.

Für die GUI unter **Einstellungen → Terminal → SSH-Verbindungen öffnen in**
das gewünschte Terminal wählen. Bei Windows Terminal muss der eingestellte
Profilname zu dessen Git-Bash-Profil passen. `sshm` bleibt unabhängig davon im
aktuellen Terminal und verwendet dessen SSH-Client und Agent-Umgebung.

## 7. Script-Installation aktualisieren

GUI schließen und laufende CLI-/SSH-Aufträge regulär beenden. Danach in Git Bash:

```bash
cd /c/dev/New_Git_Work/SSH-Manager
git pull --ff-only
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m pip check
sshm --version
```

Bei einem Pull-Fehler zunächst die Ursache klären. Die Kürzel müssen bei
unverändertem Projektpfad nicht neu eingerichtet werden. Nach dem Neustart nutzen
sie direkt den aktualisierten Python-Code; ein EXE-Build entfällt.

## 8. Einstellungen, Verbindungen und typische Fehler

GUI und CLI verwenden dieselben App-Daten unter **`%APPDATA%\SSH-Manager`**:
`settings.json`, `ui_state.json`, `app_sessions.json` und `notes.json`.
Updates im Repository ersetzen diese Dateien nicht. Über **Datei → App sichern**
lässt sich ein App-Backup erstellen. WinSCP, FileZilla, SSH Config und
SSH-Schlüssel müssen separat gesichert bzw. auf einem neuen Rechner eingerichtet
werden; sie sind nicht Teil dieses Backups.

- **`ssh_manager` oder `sshm` fehlt:** `source ~/.bashrc` ausführen und mit
  `type ssh_manager` bzw. `type sshm` prüfen. In neuen Login-Shells das Laden
  von `.bashrc` durch `.bash_profile` kontrollieren.
- **`sshm` startet eine EXE:** `type -a sshm` zeigt alle Definitionen. Für diesen
  Script-Betrieb muss die oben gezeigte Bash-Funktion aufgelöst werden.
- **Python-/Modulfehler:** Pfade prüfen und die Pakete mit genau
  `./.venv/Scripts/python.exe -m pip install -r requirements.txt` installieren.
- **SSH fehlt oder verwendet einen anderen Agenten:** In derselben Git Bash
  `command -v ssh` und `ssh -V` prüfen. GUI- und CLI-Terminal können unterschiedliche
  SSH-Umgebungen haben. Hintergrundprüfungen benötigen eine Anmeldung per
  Schlüssel/Agent ohne interaktive SSH-Passwortabfrage.
- **Git-Bash-Profil fehlt:** In Windows Terminal ein Profil für die tatsächlich
  installierte Git-Bash-Datei `bin\bash.exe` einrichten und den Profilnamen in
  SSH-Manager abgleichen. Keine WSL-Bash dafür verwenden.

Technische Quellen: `requirements.txt`, `sshm.py`, `ssh_manager.py`,
`scripts/build_windows.ps1`, `scripts/install_cli.ps1` sowie die lokal gelesenen
Bash-Profile. Stand: 24.11.2026. Die Anleitung ändert keine Shell-Konfiguration.

## 9. Optional ganz zum Schluss: EXEs bauen

Nur wenn ich zusätzlich eigenständige Windows-Programme haben möchte.
**PowerShell im Projektordner** öffnen und ausführen:

```powershell
Set-Location 'C:\dev\New_Git_Work\SSH-Manager'
.\.venv\Scripts\python.exe -c "import struct; print(struct.calcsize('P') * 8)"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

Die Architekturprüfung muss für den hier beschriebenen x64-Build **64** ausgeben.
Das Buildskript verwendet bevorzugt `.venv`, prüft die Versionsmetadaten und
installiert die Build-Abhängigkeiten aus `requirements-dev.txt` einschließlich
der Laufzeit-Abhängigkeiten. Für einen normalen Build die App-Version nicht erhöhen.
Es ersetzt die Ordner `build` und `dist`; dort keine eigenen Dateien ablegen und
vorher daraus laufende EXEs schließen.

Nach erfolgreichem Build entstehen:

| Datei | Verwendung |
|---|---|
| `dist\SSH Manager.exe` | Grafische Oberfläche per Doppelklick |
| `dist\sshm.exe` | Terminalsuche, beispielsweise `.\dist\sshm.exe web` in PowerShell |

Die EXEs enthalten Python. SSH, Git Bash und das für GUI-Aktionen gewählte
Terminal bleiben externe Voraussetzungen. Die bisherigen Bash-Kürzel verwenden
weiterhin die Scripts; der Build stellt sie nicht auf EXEs um. Zum gezielten
Ausprobieren in Git Bash:

```bash
"/c/dev/New_Git_Work/SSH-Manager/dist/SSH Manager.exe"
/c/dev/New_Git_Work/SSH-Manager/dist/sshm.exe web
```

`scripts/install_cli.ps1 -AddToPath` ist für diesen Script-Betrieb nicht nötig:
Es würde die CLI-EXE separat installieren. Die vorhandene Bash-Funktion `sshm`
hat in Git Bash weiterhin Vorrang. Separat installierte EXEs werden durch
`git pull` und Build nicht automatisch ersetzt.

Sollten Windows bzw. Smart App Control eine selbst gebaute EXE blockieren, ist
der Build allein kein Nachweis ihrer Ausführbarkeit. Für meinen hier beschriebenen
Alltag bleibt der Script-Start mit `ssh_manager` und `sshm` verfügbar.
