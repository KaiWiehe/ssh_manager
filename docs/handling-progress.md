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
| 4 | Upload und Verteilung | offen |
| 7 | Gespeicherte Filter | offen |
| 9 | Dienstwerkzeuge | offen |
| 10 | Tunnel-Anwendungsfälle | offen |
| 11 | Verbindungsdiagnose | offen |
| 12 | Sammelergebnisse | offen |
| 14 | Quellenstatus | offen |
| 15 | Lokales Undo | offen |
| 16 | Kontextuelle Hilfe | offen |

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
