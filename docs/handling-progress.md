# Handling-Verbesserungen – Auftrag vom 07.10.2026

Kai hat alle 16 Punkte aus der Vault-Notiz „SSH-Manager Feature Ideas“, Abschnitt
07.10.2026, autorisiert. Je Punkt eigener Commit, ein Patch-Versionssprung,
Syntaxprüfung, relevante Tests und Push auf main. Keine echten Remote-Aktionen
zum Testen; bestehende untracked Testordner nicht anfassen.

Reihenfolge: **1, 5, 6, 8, 13, 2, 3, 4, 7, 9, 10, 11, 12, 14, 15, 16**.

## Status

| Punkt | Aufgabe | Stand |
|---|---|---|
| 1 | Drei Remote-Einstiege | fertig, 0.2.45 |
| 5 | Einheitliche Auswahlregeln | fertig, 0.2.46 |
| 6 | Auswahlleiste | fertig, 0.2.47 |
| 8 | Verbindungsdetails | fertig, 0.2.48 |
| 13 | Export und Backup | fertig, 0.2.49 |
| 2 | Runbook-Bibliothek | fertig, 0.2.50 |
| 3 | Runbook-Parameter | fertig, 0.2.51 |
| 4 | Upload und Verteilung | fertig, 0.2.52 |
| 7 | Gespeicherte Filter | fertig, 0.2.53 |
| 9 | Dienstwerkzeuge | fertig, 0.2.54 |
| 10 | Tunnel-Anwendungsfälle | fertig, 0.2.55 |
| 11 | Verbindungsdiagnose | fertig, 0.2.56 |
| 12 | Sammelergebnisse | fertig, 0.2.57 |
| 14 | Quellenstatus | fertig, 0.2.58 |
| 15 | Lokales Undo | fertig, 0.2.59 |
| 16 | Kontextuelle Hilfe | fertig, 0.2.60 |

## Limit und Fortsetzung

Automation: `ssh-manager-handling-auftrag-fortsetzen`, stündlich in diesem Chat.
Unter 25 % verbleibendem Fünf-Stunden- oder Wochenbudget nach sicherem
Zwischenstand pausieren; betroffene Fenster und Resetzeiten hier festhalten.
Erst nach vollständiger Auffüllung der betroffenen Fenster automatisch fortsetzen.
Keine Resetgutschrift verwenden. Aktuell keine Limitpause.

Die Automation nach vollständigem Abschluss beenden, den Chat offen lassen.
Ein fehlendes oder unbekanntes Limit ist keine Freigabe zum Weiterarbeiten.

## Prüfungen und Entscheidungen

- Ausgangsversion 0.2.44; Branch main. Bestehende untracked pytest-Ordner vorhanden.
- Python: `.venv/Scripts/python.exe`; Tests mit `-p no:cacheprovider` und
  eigenem, repo-lokalem `--basetemp`. Fallow entfällt ohne package.json.
- Punkt 1: drei eigene Aufgaben über Aktionen-Menü, Skripte zusätzlich im
  Session-Kontextmenü. Unpassende gespeicherte Einträge wechseln den Modus nicht
  stillschweigend. Favoriten anderer Modi bleiben erhalten. Vor-/Nach-Befehle
  unter „Erweiterter Ablauf“. 211 Tests bestanden (handling, logic, tree),
  Syntax und Versionskonsistenz erfolgreich. Windows-Tk-Dialoge geprüft.
- Punkt 5: F2/Entf und Palette verwenden eine gemeinsame Einzelzielregel:
  genau ein Häkchen, sonst ohne Häkchen die Fokuszeile; mehrere Häkchen ergeben
  kein Einzelziel. Enter/Ctrl+Enter bleiben unverändert. Kontextmenü benennt
  Zeile und Häkchenzahl. 276 Tests inkl. Windows-App-/Hilfeprüfungen bestanden.
- Punkt 6: vollständige Auswahlübersicht mit verborgenen Suchzielen,
  Entfernen einzelner Hosts und Leeren. Mehrere Suchen behalten die Auswahl;
  doppelte virtuelle Zeilen werden gemeinsam umgeschaltet. 223 Tests inkl.
  Windows-Tk-Auswahlablauf/Hilfe bestanden. Beim Test gefundene Endlosschleife
  im Idle-Layout eines noch nicht sichtbaren Baums durch zeitversetzten Retry
  behoben; echte Remote-Aktionen wurden nicht ausgeführt.
- Punkt 8: zuschaltbares Detailpanel folgt der Fokuszeile, zeigt Quelle,
  Benutzerherkunft, Alias, Host/Port/Ordner und app-interne Notizen.
  Editierbare Verbindungen und reine App-Anpassungen sind klar getrennt.
  209 Tests (handling, help, logic) inkl. echtem Windows-Panel bestanden.
- Punkt 13: Tabellenexport mit Ansicht/Auswahl/allen geladenen Verbindungen
  und Anzahl. Separates App-Backup enthält exakt vier App-Datendateien;
  externe Quellen/SSH-Keys nicht enthalten. Restore mit Vorschau, vorheriger
  Sicherung und wiederaufnehmbarem Journal; danach App-Neustart erforderlich.
  231 relevante Tests und vollständige Suite: 531 bestanden, 20 bestehende
  Pillow-Deprecation-Warnungen. Fehler-/Recovery-Tests schreiben nur in Testpfade.
- Punkt 2: separate Bibliothek mit Suche, Inhalts-/Metadateneditor,
  Pin/Delete und Ausführung auf expliziter Häkchen-Auswahl. Neue Ausführungs-
  dialoge zeigen nur Übernahme gespeicherter Einträge, keine Verwaltungsbuttons.
  205 relevante Tests und 9 separate Windows-Hilfetests bestanden. Ein erster
  kombinierter GUI-Lauf hing; isolierte Nachprüfung erfolgreich. Verwaltung
  wird sofort gespeichert, bei Speicherfehler zurückgesetzt.
- Punkt 3: Formularparameter über Bibliothek definierbar (Text/Zahl/Port/Pfad/
  Auswahl, Pflichtfeld, Default, Geheimfeld). Sichere Datenübergabe als
  `RUNBOOK_NAME`-Umgebungsvariablen; keine Template-Ersetzung. Geheimwerte
  nur zur Laufzeit, in Vorschau/Header redigiert, weder History noch Favoriten.
  Bestehende DPAPI-Skriptpayloads schützen temporäre Inhalte. 274 relevante
  Tests inkl. tatsächlichem lokalen Git-Bash-Quoting-Test und Tk-Formen bestanden.
- Punkt 4: einfacher Upload (eine Datei, ein Host, ein beschreibbarer Ordner)
  ohne sudo/Rechteeditor/Folgebefehl; bisheriger Mehrzielablauf als „Dateien
  verteilen“. Einfache Installation atomar, ohne Überschreibfreigabe atomarer
  No-Clobber-Link, bei Überschreiben vorhandene Rechte/Besitzer beibehalten.
  277 Tests inkl. lokal ausgeführtem Bash-Installer für beide Modi bestanden;
  keine SSH-Verbindung/Remote-Änderung ausgelöst.
- Punkt 7: kombinierte Quelle/Ordner/Benutzer/Port-Filter und benannte
  Ansichten, sichtbare Kriterien und Reset. UI-State enthält Ansichten und
  aktive Kriterien. Quellenfilter wirken innerhalb aktivierter Quellen.
  Temporäre Filteransichten verändern den Benutzer-Ordnerzustand nicht;
  Quellen-Rebuild aktualisiert auch verborgene Auswahlobjekte.
  250 relevante Tests sowie 10 separate Windows-App-/Hilfetests bestanden.
- Punkt 9: getrennte Status-/Neustart-/Logaktionen für systemd-Dienste,
  validierte Dienstauswahl und begrenzte Logzeilen, sudo explizit.
  Vorschau nennt Hosts/Befehl; ein Dienstneustart prüft anschließend den
  aktiven Zustand. Serverneustart bleibt getrennt. 232 Tests bestanden,
  keine Dienstaktion auf echten Hosts ausgeführt.

- Punkt 10: direkte/interne Tunneltypen, passende Port-Vorlagen und laufende
  Vorschau PC → SSH-Server → Ziel. Internes Ziel ist ausdrücklich Pflicht;
  scrollbarer Dialog mit stets erreichbaren Buttons. 206 Tests bestanden.

- Punkt 11: separate Diagnose für lokale SSH-Installation, Aliasauflösung,
  DNS und TCP. Anmeldung nur explizit per BatchMode/true, ohne Hostkey-Änderung.
  Proxyziele erhalten keine irreführende direkte TCP-Erfolgsmeldung. Maximal
  acht Worker, Ergebnisse ausschließlich im Tk-Hauptthread. 215 Tests bestanden.

- Punkt 12: pro Host Terminalstart/läuft/Erfolg/Fehler/unbekannt mit atomaren
  lokalen Exit-Rückmeldungen, ohne Befehle/Outputs/Secrets in Ergebnisdateien.
  Remote-Befehle/Skripte, Dienste, Upload/Verteilung, Zertifikatstausch und
  Key-Aktionen angebunden. Rückmeldung vor interaktivem Anschluss; frühe
  Uploadfehler erfasst. Bei Teilstartfehlern unbekannt statt erfundener Fehler.
  Retry nur bestätigte Fehler, erneutes Vorbereiten und Vorschau; Datei-/Key-
  Eingaben erneut prüfen, Dienstparameter bleiben ohne Passwort erhalten.
  Vollständige Suite 568 bestanden, anschließend 221 relevante Tests nach
  Erweiterung auf Keys/Zertifikatstausch. Lokale Bash-Tests, keine echten Hosts.

- Punkt 14: Ladeprotokoll für vier Quellen mit fehlend/leer/teilweise/Fehler,
  Uhrzeit/Lesedauer/Anzahl und Hinweisen. Selektives Neuladen liest keine
  andere Quelle und behält den letzten nutzbaren Stand bei Lesefehlern.
  WinSCP/FileZilla als eigene App-Kopie inklusive App-Notiz übernehmbar;
  Aliasübernahme erklärt die fortbestehende SSH-Config-Abhängigkeit.
  228 Tests bestanden. Externe Quellen bleiben unverändert.

- Punkt 15: Ctrl+Z/Dateimenü für lokale Änderungen, bis zu 20 Schritte in
  der App-Sitzung. Verschieben/Umbenennen/Löschen/Farben, zusätzlich eigene
  Notizen/Favoriten/Benutzeranpassungen. Stapelaktionen bilden einen Schritt.
  Gelöschte eigene Sessions entfernen ihre App-Metadaten; Undo stellt sie
  konsistent wieder her. Delta-Restore bewahrt spätere, unabhängige Nutzung.
  Speicherung über Drei-Dateien-Journal; kein Remote-Undo. 235 relevante
  Tests plus 35 Windows-App-/Dialog-/Undo-Tests bestanden.

- Punkt 16: ‚Was passiert hier?‘ und F1 öffnen gezielt das passende Thema;
  modale Hilfe gibt den Grab danach an den ursprünglichen Dialog zurück.
  Neue Offline-Hilfethemen erklären Bibliothek, Parameter, Filter, Tunnel,
  Diagnose, Dienste und Sammelergebnisse; bestehende Themen ergänzt.
  Gesperrte Menü-/Bibliotheksaktionen nennen ihren Grund; Bibliotheksbuttons
  in zwei Reihen. README aktualisiert. Vollständige Suite: 583 bestanden,
  20 bestehende Pillow-Deprecation-Warnungen. Windows-Tk-Bedienung geprüft.
  Screenshot-Abnahme derzeit nicht möglich: Windows-Desktop ist gesperrt.
  Python-Start und Syntax geprüft; portable EXE nicht neu gebaut.

## Abschluss

Alle 16 autorisierten Punkte umgesetzt, jeweils eigener Commit und Versionssprung.
Syntax, Versionskonsistenz und vollständige Tests erfolgreich; main gepusht.
Die temporäre Fortsetzungsautomation wird nach dem finalen Push deaktiviert.

## Bedienfeedback vom 08.10.2026

Separat vom abgeschlossenen 16-Punkte-Auftrag umgesetzt:

1. **0.2.61 – Diagnose:** zusätzliche TCP-Portliste bzw. kleine Bereiche,
   maximal 64 Ports. SSH-Port automatisch berücksichtigen, zusätzliche Ports
   direkt vom PC testen (auch bei SSH-Proxy). DNS-Name und bereits eingetragene
   IP unterscheiden. Keine UDP-Prüfung und kein automatischer Vollscan;
   Nichterreichbarkeit kann auch an Netzwerkregeln liegen.
2. **0.2.62 – Remote-Layout:** großes Befehlsfeld ohne redundante Blöcke;
   optionalen Skriptablauf vollständig einklappen. Vor-/Nach-Editoren teilen
   sich den verfügbaren Platz gleichmäßig.
3. **0.2.63 – Serverskript-Browser:** lesende SSH-Ordner-/Dateiauswahl in
   einer 50/50-Ansicht; Referenzhost, Suche, Navigation und freie Pfadeingabe.
   Derselbe Skriptpfad muss auf allen Ausführungszielen vorhanden sein und
   dasselbe Skript bezeichnen. Eingegebenen Fallback-Benutzer auch für die
   Ausführung verwenden. Abgewählter Ablauf führt erhaltene Texte nicht aus.
4. **0.2.64 – Dienste:** Referenzhost durchsuchen, Dienste suchen/übernehmen
   und weiterhin Namen frei eingeben. Installierte und laufende systemd-Units
   berücksichtigen. Fehlende Dienste vor Status/Logs/Neustart je Host erkennen
   und im Terminal sowie Sammelergebnis als „Dienst wurde nicht gefunden“
   ausweisen. Hilfe, kompakte Formularhöhe und umbrechende Browserhinweise
   nach echter Windows-Tk-Sichtprüfung nachgebessert.

Abschlussprüfung: **614 Tests bestanden**, 20 bestehende Pillow-Warnungen.
Syntax und Versionskonsistenz geprüft. Windows-Tk-Dialoge mit Testdaten gerendert
und gesichtet; keine echten Serverabfragen oder Remote-Veränderungen ausgelöst.
Lokale Git-Bash-Ausführung prüft fehlende Dienste, Abfragefehler und gemischte
Ergebnisse mit Rückmeldungen je Host. Python-only, daher kein Fallow-Lauf.
Portable EXE nicht neu gebaut. Fortsetzung nach Limit-Reset war nicht nötig.

## Vollständiger TCP-Portscan – 08.10.2026, 0.2.65

Auf ausdrücklichen Wunsch zusätzlich zum begrenzten Diagnose-Portfeld:
„Alle TCP-Ports prüfen (dauert sehr lange)“ öffnet einen eigenen Scan-Dialog.
Erst dessen Startbutton prüft alle Ports 1–65535 je aufgelöster IPv4-/IPv6-IP.
Ziele/IPs nacheinander, direkt vom PC und ohne SSH-Proxy. Keine Nutzdaten,
Anmeldung oder UDP-Prüfung; keine zusätzlichen Laufzeitabhängigkeiten.

Standard: 50 Verbindungsstarts/s, höchstens 64 laufende Verbindungen und
1 Sekunde Timeout. Rate 1–100/s und Timeout 0,5–5 Sekunden einstellbar.
50/s ergeben mindestens etwa 22 Minuten je IP; Timeouts verlängern den Lauf.
Live-Fortschritt/offene Ports, getrennte Zähler für Ablehnung, Timeout und Fehler.
Abbrechen/Schließen stoppt neue Prüfungen; laufende Verbindungen enden mit Timeout.
Teilergebnisse und fehlgeschlagene Zielauflösung werden ausdrücklich benannt.

Der Dialog erklärt mögliche Logeinträge, Sicherheitsalarme, Sperren und
Beeinträchtigung empfindlicher Dienste. Technische Grundlage:
https://nmap.org/book/scan-methods-connect-scan.html und
https://nmap.org/book/man-performance.html (08.10.2026 geprüft).
Keine aktive Diensterkennung: ein offener Port belegt nur PC-Erreichbarkeit.

Vollständige Suite: 628 bestanden, 20 bestehende Pillow-Warnungen. Anschließend
20 gezielte Scantests inklusive sechs zusätzlicher Fälle bestanden (634 Fälle
insgesamt abgedeckt). Mockprüfungen für Rate, Parallelitätsgrenze, Abbruch,
mehrere IPs und Fehler; einziger echter Netzwerkcheck ist ein lokaler
Loopback-Testlistener. Keine echten Server oder vollständigen Netzscans getestet.
Syntax und Versionskonsistenz geprüft; Python-only, kein Fallow/EXE-Build.

## Diagnose-Einstellungen und vollständige Aktionsmenüs – 08.10.2026

1. **0.2.67, 84f8243:** Gültige zusätzliche TCP-Ports werden im UI-State
   gespeichert, auch beim Schließen ohne Diagnose-Start. Sie gelten für andere
   Hosts und bleiben nach App-Neustart erhalten. Leeren entfernt die Vorgabe;
   ungültige Zwischenstände überschreiben keine gültig gespeicherte Portliste.
   Konfigurierte Quick-Select-Benutzer stehen im Diagnose-Dialog bereit.
   Feste Session-Benutzer haben Vorrang, sonst gilt der Fallback-Benutzer für
   die optionale SSH-Anmeldung. SSH-Aliase verwenden ihre SSH-Konfiguration.
   DNS- und TCP-Prüfungen brauchen keinen Benutzer.
2. **0.2.68:** Gemeinsame Aktionsmenüs oben unter Aktionen sowie im Rechtsklick
   auf Verbindungen, Ordner und den leeren Baumbereich. Diagnose steht außerdem
   direkt im Verbindungs- und Ordnermenü. Kontextaktionen benutzen die angeklickte
   Verbindung bzw. alle Hosts im Ordner inklusive Unterordnern; fremde Häkchen
   bleiben erhalten. Einzelhost-Aktionen sind bei mehreren Zielen gesperrt.
   Verbindung / Ordner verwalten enthält die bestehenden Kontextaktionen auch
   im oberen Menü. App-Werkzeuge erschließt Datei, Auswahl, Ansicht,
   Einstellungen und Hilfe mit deren ursprünglichem globalen Wirkungsbereich.

Vollständige Suite: **645 Tests bestanden**, 20 bestehende Pillow-Warnungen.
Syntax geprüft; echte Windows-Tk-Menütests prüfen Zielumfang, wiederholtes Öffnen,
gesperrte Aktionen und Callback-Lebensdauer. Keine echten Remote-Aufrufe.
Python-only, daher kein Fallow; portable EXE nicht neu gebaut.

## Fehler beim Öffnen der Menüleiste – 08.10.2026, 0.2.69

Benutzermeldung nach 0.2.68: Klick auf Aktionen, Ansicht, Auswahl usw. zeigt
„Unerwarteter Fehler“. error.log belegt TclError in action_menus.refresh bei
Menu.delete/deletecommand. Ursache: geklonte Einträge teilten den Tcl-Callback
des Originalmenüs. Tk löscht beim Entfernen eines Eintrags dessen Callback,
auch wenn dieser einem anderen Menü gehört. Beim Neuaufbau entstand damit
eine doppelte Löschung bzw. ein ungültiges Originalkommando.

Geklonte Einträge registrieren nun eigene Callbacks, die das Originalkommando
aufrufen. Beim Neuaufbau werden Klone vor ihrem ursprünglichen Menü entfernt.
Regressionen zuerst reproduziert, danach erfolgreich geprüft: wiederholter
Neuaufbau aller Menü-Cascades, Entfernen geklonter Einträge ohne Beschädigung
des Originals sowie Originalaufrufe nach erneutem Öffnen der App-Werkzeuge.

Abschluss: **648 Tests bestanden**, 20 bestehende Pillow-Warnungen. Syntax,
Versionskonsistenz und Diff geprüft. Keine echten Remote-Aufrufe; Python-only,
Fallow nicht anwendbar. Portable EXE nicht neu gebaut. App-Neustart erforderlich.

## Weiteres Bedienfeedback – 08.10.2026, 0.2.70–0.2.72

1. **0.2.70, 3b5c30d:** DNS-Eingabe-, DNS-Server- und Ergebnisdialoge verwenden
   für die Hilfeleiste denselben Geometry-Manager wie ihre Inhalte (grid).
   Echte Tk-Dialogtests decken ein und drei Ergebnisse ab. Dienstbefehle setzen
   SSH-Optionen vor `--`/Ziel und starten ausdrücklich `bash -s` für den
   Skriptinhalt auf stdin. Zuvor wurde `-t` nach dem Ziel als Remote-Befehl
   behandelt; dies erklärt den gemeldeten Bash-Fehler. Git-Bash-Tests simulieren
   die SSH-Argumentgrenze und führen alle drei Dienstaktionen lokal aus.
2. **0.2.71, 4217875:** 64-Port-Limit entfernt, explizite Listen/Bereiche von
   1 bis 65535 zulässig. Hinweis: mehr Ports verlängern die Diagnose. Gültige
   Listen bleiben gespeichert. Kontextmenüs bieten Markdown/CSV/Excel direkt
   für Verbindung, Ordner mit Unterordnern oder Häkchen-Auswahl. Der Exportdialog
   fixiert diesen Zielumfang; fremde Hosts können nicht versehentlich hinzukommen.
3. **0.2.72:** Jede Menüaktion einzeln als optionale Toolbar-Schnellauswahl;
   einschließlich Diagnose/Vollscan, Skriptmodi, aller Dienstaktionen, Upload,
   DNS, Exporte, globaler App-Werkzeuge und Funktionen des fokussierten Eintrags.
   Neue Optionen sind abgewählt, bestehende Toolbar bleibt aktiv. Sofortige
   Vorschau, dauerhafte Speicherung und vorhandenes Mehr-Menü bei Platzmangel.
   Einstellungen → Tunnel / Dienste: Tunnel je Zeile `Name | lokal | Ziel`,
   Dienste je Zeile ein Name. Bearbeiten, Ergänzen und Leeren möglich; Ports
   und eindeutige Namen validiert. Freie Eingaben/Serverbrowser bleiben erhalten.
   Vorgaben und Toolbar-Auswahl sind Teil von Einstellungen, Export/Import und
   App-Backup. Gemeinsame SSH-Korrektur auch auf Skript-/Verteilungsabläufe
   angewendet, die denselben Optionsfehler enthielten.

Windows-Tk-Einstellungsseiten mit isolierten Testdaten gerendert und gesichtet.
Keine echten Remote-Aufrufe. Python-only, Fallow nicht anwendbar; EXE nicht gebaut.
Abschluss: **661 Tests bestanden**, 20 bestehende Pillow-Warnungen; Syntax und
Versionskonsistenz geprüft. Zusätzliche Kontext-Toolbar-Auswahlen danach gezielt
mit den Menü-, Settings- und Exporttests geprüft.
