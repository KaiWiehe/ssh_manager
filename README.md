# SSH-Manager

Öffnet mehrere WinSCP-Server-Sessions gleichzeitig als SSH-Tabs in Windows Terminal.

## Voraussetzungen

- Windows 10/11
- Python 3.8+
- [Windows Terminal](https://aka.ms/terminal) installiert
- Git Bash-Profil in Windows Terminal vorhanden (Standard bei Git for Windows)
- WinSCP mit gespeicherten Sessions

## Starten

```bat
python ssh_manager.py
```

## Bedienung

1. **Sessions auswählen** – Klick auf eine Zeile setzt/entfernt den Haken. Ordner sind auf-/zuklappbar.
2. **Mehrere auf einmal** – Beliebig viele Haken setzen. Rechtsklick auf einen Ordner → „Alle im Ordner auswählen".
3. **Suche** – Oben im Suchfeld tippen filtert live nach Name und Hostname.
4. **Verbinden** – Auf „Verbinden (N ausgewählt)" klicken.
5. **Benutzernamen wählen** – Im Dialog einen der Schnellauswahl-Buttons klicken oder eigenen Namen eingeben, dann OK.
6. Alle gewählten Server öffnen sich als neue Tabs **in einem Windows Terminal Fenster**.

## Sessions werden aus WinSCP gelesen

Die App liest direkt aus der Windows-Registry:

```
HKEY_CURRENT_USER\Software\Martin Prikryl\WinSCP 2\Sessions
```

Kein Import oder Export nötig – alle in WinSCP gespeicherten Sessions erscheinen automatisch.

## Kein pip erforderlich

Nur Python-Standardbibliothek (`tkinter`, `winreg`, `subprocess`).
