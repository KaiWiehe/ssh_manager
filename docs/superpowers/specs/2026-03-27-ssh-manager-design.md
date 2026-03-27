# SSH-Manager – Design Spec

**Datum:** 2026-03-27
**Status:** Approved

---

## Kontext

Der User verwaltet viele SSH-Server über WinSCP. WinSCP selbst erlaubt nicht, mehrere SSH-Sessions gleichzeitig in einem Schritt zu öffnen. Diese App liest die vorhandene WinSCP-Sessionliste aus der Windows-Registry und ermöglicht es, mehrere Server gleichzeitig via Windows Terminal (Git Bash) zu öffnen – als Tabs in einem einzigen Terminalfenster.

---

## Anforderungen

- **Plattform:** Windows only
- **Technologie:** Python 3, tkinter, winreg, subprocess – ausschließlich stdlib, keine pip-Pakete
- **Lieferformat:** Einzelne `.py`-Datei (`ssh_manager.py`)
- **Registry-Quelle:** `HKEY_CURRENT_USER\Software\Martin Prikryl\WinSCP 2\Sessions`

---

## Architektur

### Klassen / Module (in einer Datei)

```
SSHManagerApp          ← Hauptfenster (tk.Tk), koordiniert alle Komponenten
  ├── ToolbarFrame     ← Suchfeld + "Alle auswählen / abwählen"-Buttons
  ├── SessionTree      ← ttk.Treeview mit Checkbox-Logik
  └── UserDialog       ← Toplevel-Modal für Benutzernamen-Auswahl

RegistryReader         ← liest Sessions aus winreg
TerminalLauncher       ← baut wt.exe-Kommando und startet es
```

### Datenfluss

1. Start → `RegistryReader.load_sessions()` liest alle Subkeys aus der Registry
2. Jeder Subkey-Name wird URL-decoded und auf `/` gesplittet → Ordner + Session-Name
3. `SessionTree.populate()` baut den Baum rekursiv auf
4. User wählt Sessions per Checkbox aus → klickt "Verbinden"
5. `UserDialog` öffnet sich modal, User bestätigt Benutzernamen
6. `TerminalLauncher.launch(sessions, user)` öffnet einen `wt.exe`-Prozess mit allen Tabs
7. Hauptfenster bleibt offen

---

## UI-Layout

```
┌─────────────────────────────────────────────────────┐
│  SSH-Manager                              [_][□][X] │
├─────────────────────────────────────────────────────┤
│  🔍 [ Suche nach Name oder Hostname...             ] │
│  [Alle auswählen]  [Alle abwählen]                  │
├─────────────────────────────────────────────────────┤
│  Checkbox  Name              Hostname        Port   │
│  ▼ Extern                                           │
│    ☐  Bundo            ftp.5609531...               │
│    ☐  Dialfire         1.2.3.4                      │
│  ▼ Others                                           │
│    ☐  10.120.137.10-DB  10.120.137.10               │
│  ▼ Privat                                           │
│    ☐  Plex             192.168.1.10       2222      │
│  ► Staging             (zugeklappt)                 │
├─────────────────────────────────────────────────────┤
│        [  Verbinden (2 ausgewählt)  ]               │
└─────────────────────────────────────────────────────┘
```

**UserDialog (Modal):**
```
┌────────────────────────────────────────────┐
│  Benutzername auswählen                    │
├────────────────────────────────────────────┤
│  [tool-admin]  [dev-sys]  [de-nb-statist]  │
│                                            │
│  Benutzername: [tool-admin_______________] │
│                                            │
│        [  OK  ]       [Abbrechen]          │
└────────────────────────────────────────────┘
```

---

## Registry-Parsing

**Pfad (verifiziert):** `HKEY_CURRENT_USER\Software\Martin Prikryl\WinSCP 2\Sessions`

**Session-Struktur:**
- Jeder Subkey = eine Session
- Key-Name enthält Ordnerstruktur via `/` (z.B. `Extern/Bundo`, `Others/10.120.137.10%20-%20DB`)
- URL-Decoding: `%20` → Leerzeichen, etc. (via `urllib.parse.unquote`)
- `Default%20Settings` → immer überspringen
- Relevante Werte: `HostName` (REG_SZ), `UserName` (REG_SZ), `PortNumber` (REG_DWORD, nur wenn ≠ 22)
- Sessions ohne `HostName`-Wert werden ignoriert
- Alle Sessions werden angezeigt (kein Protokoll-Filter)

**Ordner-Aufbau:**
```python
# "Extern/Bundo" → folder=["Extern"], name="Bundo"
# "Others/Sub/server1" → folder=["Others","Sub"], name="server1"
# "tool-admin@10.120.67.31" → folder=[], name="tool-admin@10.120.67.31"
parts = session_key.split("/")
folder_path = parts[:-1]
session_name = parts[-1]
```

---

## Checkbox-Implementierung (ttk.Treeview)

- Zwei kleine Bitmap-Images (16×16px): `img_checked` und `img_unchecked`
- Bitmaps werden inline als XBM-Strings im Code definiert (kein externes Asset)
- Jeder Treeview-Eintrag hat `image=img_checked` oder `img_unchecked`
- Klick auf eine Zeile → toggle Checkbox via `<ButtonRelease-1>`
- Ordner-Zeilen haben kein Checkbox-Bild (oder optional: Tri-State)
- Rechtsklick auf Ordner-Zeile → Kontextmenü: "Alle auswählen / Alle abwählen"

---

## Windows Terminal Befehl

**Alle Tabs in einem Fenster:**
```python
# Erster Tab:
parts = ['wt.exe', '-p', '"Git Bash"', f'ssh {user}@{host1}']

# Weitere Tabs:
for host in remaining_hosts:
    if port != 22:
        parts += [';', 'new-tab', '-p', '"Git Bash"', f'ssh -p {port} {user}@{host}']
    else:
        parts += [';', 'new-tab', '-p', '"Git Bash"', f'ssh {user}@{host}']

subprocess.Popen(' '.join(parts), shell=True)
```

**Wichtig:** `shell=True` nötig, da `wt.exe` das `;`-Chaining nur via Shell-Kontext korrekt interpretiert.

---

## Suchfunktion

- Suchfeld oben filtert den Baum live beim Tippen (`trace` auf `StringVar`)
- Gefiltert wird nach Session-Name UND Hostname (case-insensitive)
- Bei aktivem Filter: alle Ordner die Treffer enthalten bleiben aufgeklappt
- Suchfeld leeren → Originalzustand wiederherstellen (Ordner-Aufklappstatus bleibt)

---

## Verbinden-Button

- Text: `Verbinden` wenn 0 ausgewählt, `Verbinden (N ausgewählt)` wenn N > 0
- Deaktiviert (`state=DISABLED`) wenn 0 Sessions ausgewählt sind
- Öffnet UserDialog modal → bei OK: `TerminalLauncher.launch()` aufrufen

---

## Edge Cases

| Fall | Verhalten |
|------|-----------|
| `Default%20Settings` | Immer überspringen |
| Session ohne HostName | Überspringen (kein `HostName` REG_SZ Wert) |
| 0 Sessions ausgewählt | "Verbinden"-Button deaktiviert |
| UserDialog: Abbrechen | Keine Verbindung wird geöffnet |
| Registry nicht vorhanden | Fehlermeldung als tkinter.messagebox |
| wt.exe nicht gefunden | Fehlermeldung als tkinter.messagebox |

---

## Verifikation

1. `python ssh_manager.py` starten → Fenster öffnet sich mit der WinSCP-Session-Liste
2. Ordner ein-/ausklappen testen
3. Suchfeld eingeben → Filtert Live
4. Rechtsklick auf Ordner → "Alle auswählen" wählt alle Server im Ordner aus
5. "Alle auswählen" / "Alle abwählen" Buttons testen
6. Verbinden-Button zeigt Anzahl an
7. UserDialog öffnet sich, Quickselect-Buttons füllen das Textfeld, OK öffnet wt.exe
8. Mehrere Server → mehrere Tabs in EINEM Windows Terminal Fenster
9. Port != 22 → `-p PORT` im SSH-Befehl
10. Hauptfenster bleibt nach Verbinden offen
