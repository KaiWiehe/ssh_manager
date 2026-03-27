# SSH-Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Einzelne Python-Datei `ssh_manager.py` – ein tkinter GUI-Tool, das WinSCP-Sessions aus der Windows-Registry liest und mehrere SSH-Verbindungen als Tabs in Windows Terminal öffnet.

**Architecture:** `RegistryReader` liest Sessions aus HKCU\...\WinSCP 2\Sessions. `SessionTree` (ttk.Treeview mit Checkbox-Images) zeigt sie gruppiert in Ordnern. `TerminalLauncher` baut einen `wt.exe`-Befehl mit allen gewählten Servern als neue Tabs und startet ihn.

**Tech Stack:** Python 3.8+, tkinter, ttk, winreg, subprocess, urllib.parse – ausschließlich stdlib, keine pip-Pakete, Windows only.

---

## File Structure

```
ssh_manager.py         ← Gesamte Applikation (einzige Deliverable-Datei)
tests/
  test_logic.py        ← Unit-Tests für reine Funktionen (kein GUI, kein winreg)
docs/
  superpowers/
    specs/2026-03-27-ssh-manager-design.md
    plans/2026-03-27-ssh-manager.md  ← diese Datei
```

**Interner Aufbau von `ssh_manager.py` (Reihenfolge der Definitionen):**
```
# 1. Imports + Konstanten
# 2. Session (dataclass)
# 3. parse_session_key() – reine Funktion
# 4. build_wt_command()  – reine Funktion
# 5. RegistryReader
# 6. TerminalLauncher
# 7. UserDialog (tk.Toplevel)
# 8. SessionTree (ttk.Treeview-Wrapper)
# 9. SSHManagerApp (tk.Tk)
# 10. if __name__ == "__main__"
```

---

## Task 1: Projekt-Skeleton + Session-Datenmodell + parse_session_key-Tests

**Files:**
- Create: `ssh_manager.py`
- Create: `tests/test_logic.py`

- [ ] **Step 1: `tests/test_logic.py` anlegen – schlägt fehl (ImportError erwartet)**

```python
# tests/test_logic.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager import Session, parse_session_key


def test_parse_session_key_with_folder():
    folder, name = parse_session_key("Extern/Bundo")
    assert folder == ["Extern"]
    assert name == "Bundo"


def test_parse_session_key_nested():
    folder, name = parse_session_key("Others/Sub/server1")
    assert folder == ["Others", "Sub"]
    assert name == "server1"


def test_parse_session_key_no_folder():
    folder, name = parse_session_key("tool-admin@10.120.67.31")
    assert folder == []
    assert name == "tool-admin@10.120.67.31"


def test_parse_session_key_url_encoded():
    folder, name = parse_session_key("Others/10.120.137.10%20-%20DB")
    assert folder == ["Others"]
    assert name == "10.120.137.10 - DB"


def test_parse_session_key_url_encoded_folder():
    folder, name = parse_session_key("My%20Servers/web-01")
    assert folder == ["My Servers"]
    assert name == "web-01"
```

- [ ] **Step 2: Test ausführen – muss fehlschlagen**

```
python -m pytest tests/test_logic.py -v
```
Erwartetes Ergebnis: `ModuleNotFoundError: No module named 'ssh_manager'`

- [ ] **Step 3: `ssh_manager.py` Skeleton mit Session + parse_session_key anlegen**

```python
"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import messagebox, ttk
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import unquote
import winreg

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------
REGISTRY_PATH = r"Software\Martin Prikryl\WinSCP 2\Sessions"
SKIP_SESSIONS = {"Default Settings"}
QUICK_USERS = ["tool-admin", "dev-sys", "de-nb-statist"]
DEFAULT_USER = "tool-admin"
WINDOW_TITLE = "SSH-Manager"
WINDOW_MIN_SIZE = (600, 450)

# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------
@dataclass
class Session:
    """Repräsentiert eine WinSCP-Session aus der Registry."""
    key: str                        # originaler Registry-Subkey-Name
    display_name: str               # URL-dekodierter Session-Name (letzter Teil)
    folder_path: list[str]          # URL-dekodierte Ordnerpfad-Teile
    hostname: str                   # HostName-Wert aus der Registry
    username: str = ""              # UserName-Wert (optional)
    port: int = 22                  # PortNumber (default 22)

    @property
    def folder_key(self) -> str:
        """Ordner-Pfad als String, z.B. 'Extern/Sub'."""
        return "/".join(self.folder_path)


# ---------------------------------------------------------------------------
# Reine Hilfsfunktionen (testbar ohne GUI/Registry)
# ---------------------------------------------------------------------------
def parse_session_key(key: str) -> tuple[list[str], str]:
    """
    Zerlegt einen WinSCP-Registry-Subkey-Namen in Ordner-Pfad und Session-Name.
    URL-Encoding wird dekodiert.

    Beispiele:
      "Extern/Bundo"                  → (["Extern"], "Bundo")
      "Others/10.120.137.10%20-%20DB" → (["Others"], "10.120.137.10 - DB")
      "tool-admin@10.120.67.31"       → ([], "tool-admin@10.120.67.31")
    """
    parts = key.split("/")
    folder_path = [unquote(p) for p in parts[:-1]]
    name = unquote(parts[-1])
    return folder_path, name
```

- [ ] **Step 4: Tests erneut ausführen – müssen bestehen**

```
python -m pytest tests/test_logic.py -v
```
Erwartetes Ergebnis:
```
PASSED tests/test_logic.py::test_parse_session_key_with_folder
PASSED tests/test_logic.py::test_parse_session_key_nested
PASSED tests/test_logic.py::test_parse_session_key_no_folder
PASSED tests/test_logic.py::test_parse_session_key_url_encoded
PASSED tests/test_logic.py::test_parse_session_key_url_encoded_folder
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add ssh_manager.py tests/test_logic.py
git commit -m "feat: add Session dataclass and parse_session_key with tests"
```

---

## Task 2: build_wt_command-Tests + TerminalLauncher

**Files:**
- Modify: `ssh_manager.py` (Funktionen hinzufügen)
- Modify: `tests/test_logic.py` (Tests hinzufügen)

- [ ] **Step 1: Tests für build_wt_command in `tests/test_logic.py` ergänzen**

```python
# Am Ende von tests/test_logic.py anfügen:
from ssh_manager import build_wt_command


def test_build_wt_command_single_session():
    sessions = [Session("k", "srv1", [], "10.0.0.1")]
    cmd = build_wt_command(sessions, "tool-admin")
    assert cmd == 'wt.exe new-tab -p "Git Bash" -- ssh tool-admin@10.0.0.1'


def test_build_wt_command_multiple_sessions():
    sessions = [
        Session("k1", "srv1", [], "10.0.0.1"),
        Session("k2", "srv2", [], "10.0.0.2"),
    ]
    cmd = build_wt_command(sessions, "tool-admin")
    assert cmd == (
        'wt.exe new-tab -p "Git Bash" -- ssh tool-admin@10.0.0.1'
        ' ; new-tab -p "Git Bash" -- ssh tool-admin@10.0.0.2'
    )


def test_build_wt_command_non_standard_port():
    sessions = [Session("k", "srv", [], "10.0.0.1", port=2222)]
    cmd = build_wt_command(sessions, "dev-sys")
    assert cmd == 'wt.exe new-tab -p "Git Bash" -- ssh -p 2222 dev-sys@10.0.0.1'


def test_build_wt_command_mixed_ports():
    sessions = [
        Session("k1", "s1", [], "10.0.0.1", port=22),
        Session("k2", "s2", [], "10.0.0.2", port=2222),
    ]
    cmd = build_wt_command(sessions, "tool-admin")
    assert cmd == (
        'wt.exe new-tab -p "Git Bash" -- ssh tool-admin@10.0.0.1'
        ' ; new-tab -p "Git Bash" -- ssh -p 2222 tool-admin@10.0.0.2'
    )
```

- [ ] **Step 2: Test ausführen – schlägt fehl**

```
python -m pytest tests/test_logic.py::test_build_wt_command_single_session -v
```
Erwartetes Ergebnis: `ImportError: cannot import name 'build_wt_command'`

- [ ] **Step 3: `build_wt_command` und `TerminalLauncher` in `ssh_manager.py` ergänzen**

Nach der `parse_session_key`-Funktion einfügen:

```python
def build_wt_command(sessions: list[Session], user: str) -> str:
    """
    Erzeugt den wt.exe-Befehl, der alle Sessions als neue Tabs öffnet.
    Alle Tabs landen im selben Windows Terminal Fenster.

    Format:
      wt.exe new-tab -p "Git Bash" -- ssh USER@HOST
        ; new-tab -p "Git Bash" -- ssh -p PORT USER@HOST2
        ...
    """
    parts = []
    for i, session in enumerate(sessions):
        if session.port != 22:
            ssh_cmd = f"ssh -p {session.port} {user}@{session.hostname}"
        else:
            ssh_cmd = f"ssh {user}@{session.hostname}"

        if i == 0:
            parts.append(f'wt.exe new-tab -p "Git Bash" -- {ssh_cmd}')
        else:
            parts.append(f'new-tab -p "Git Bash" -- {ssh_cmd}')

    return " ; ".join(parts)


# ---------------------------------------------------------------------------
# TerminalLauncher
# ---------------------------------------------------------------------------
class TerminalLauncher:
    """Startet wt.exe mit mehreren SSH-Tabs."""

    @staticmethod
    def launch(sessions: list[Session], user: str) -> None:
        """
        Öffnet alle Sessions als neue Tabs in einem Windows Terminal Fenster.
        Raises OSError wenn wt.exe nicht gefunden wird.
        """
        if not sessions:
            return
        cmd = build_wt_command(sessions, user)
        # shell=True nötig: wt.exe parst `;` als eigenen Subcommand-Separator,
        # cmd.exe behandelt `;` nicht als Sonderzeichen und reicht es durch.
        subprocess.Popen(cmd, shell=True)
```

- [ ] **Step 4: Alle Tests ausführen – müssen bestehen**

```
python -m pytest tests/test_logic.py -v
```
Erwartetes Ergebnis: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add ssh_manager.py tests/test_logic.py
git commit -m "feat: add build_wt_command and TerminalLauncher with tests"
```

---

## Task 3: RegistryReader

**Files:**
- Modify: `ssh_manager.py`
- Modify: `tests/test_logic.py`

- [ ] **Step 1: Mocked RegistryReader-Tests in `tests/test_logic.py` ergänzen**

```python
# Am Ende von tests/test_logic.py anfügen:
from unittest.mock import patch, MagicMock
import winreg
from ssh_manager import RegistryReader


def _make_mock_registry(sessions: dict[str, dict]) -> MagicMock:
    """
    Erzeugt einen Mock für winreg.OpenKey und winreg.EnumKey/QueryValueEx.
    sessions: {subkey_name: {"HostName": "...", "PortNumber": 22, "UserName": "..."}}
    """
    session_names = list(sessions.keys())

    def enum_key_side_effect(key, index):
        if index < len(session_names):
            return session_names[index]
        raise OSError

    def open_key_side_effect(hive_or_key, subkey, *args, **kwargs):
        mock_key = MagicMock()
        mock_key.__enter__ = lambda s: s
        mock_key.__exit__ = MagicMock(return_value=False)
        return mock_key

    def query_value_side_effect(key, name):
        # Finde welche Session gerade abgefragt wird
        for sname, sdata in sessions.items():
            if name in sdata:
                return (sdata[name], winreg.REG_SZ if isinstance(sdata[name], str) else winreg.REG_DWORD)
        raise FileNotFoundError

    mock_root = MagicMock()
    return mock_root, enum_key_side_effect, open_key_side_effect, query_value_side_effect


def test_registry_reader_loads_sessions(monkeypatch):
    """RegistryReader liest Sessions korrekt aus gemockter Registry."""
    session_data = [
        ("Extern/Bundo", "ftp.example.com", 22, "myuser"),
        ("Privat/Plex", "192.168.1.10", 2222, "plex"),
    ]

    call_count = {"n": 0}

    def mock_open_key(base, path, *a, **kw):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    def mock_enum_key(key, i):
        names = [s[0] for s in session_data]
        if i < len(names):
            return names[i]
        raise OSError

    def mock_query_value(key, name):
        # Bestimme aktuelle Session über call_count (vereinfachter Mock)
        idx = min(call_count["n"] // 2, len(session_data) - 1)
        call_count["n"] += 1
        s = session_data[idx]
        if name == "HostName":
            return (s[1], winreg.REG_SZ)
        if name == "PortNumber":
            return (s[2], winreg.REG_DWORD)
        if name == "UserName":
            return (s[3], winreg.REG_SZ)
        raise FileNotFoundError

    with patch("winreg.OpenKey", side_effect=mock_open_key), \
         patch("winreg.EnumKey", side_effect=mock_enum_key), \
         patch("winreg.QueryValueEx", side_effect=mock_query_value):
        reader = RegistryReader()
        sessions = reader.load_sessions()

    assert len(sessions) == 2
    assert sessions[0].hostname == "ftp.example.com"
    assert sessions[0].display_name == "Bundo"
    assert sessions[0].folder_path == ["Extern"]
    assert sessions[1].hostname == "192.168.1.10"
    assert sessions[1].port == 2222
```

- [ ] **Step 2: Test ausführen – schlägt fehl**

```
python -m pytest tests/test_logic.py::test_registry_reader_loads_sessions -v
```
Erwartetes Ergebnis: `ImportError: cannot import name 'RegistryReader'`

- [ ] **Step 3: `RegistryReader` in `ssh_manager.py` ergänzen**

Nach `TerminalLauncher` einfügen:

```python
# ---------------------------------------------------------------------------
# RegistryReader
# ---------------------------------------------------------------------------
class RegistryReader:
    """Liest WinSCP-Sessions aus der Windows-Registry."""

    REGISTRY_BASE = winreg.HKEY_CURRENT_USER

    def load_sessions(self) -> list[Session]:
        """
        Gibt alle gültigen Sessions aus der Registry zurück.
        Sortiert nach folder_key + display_name.
        Raises OSError wenn der Registry-Pfad nicht existiert.
        """
        sessions: list[Session] = []

        with winreg.OpenKey(self.REGISTRY_BASE, REGISTRY_PATH) as base_key:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(base_key, index)
                    index += 1
                except OSError:
                    break

                # "Default Settings" überspringen
                decoded_name = unquote(subkey_name)
                if decoded_name == "Default Settings":
                    continue

                session = self._read_session(base_key, subkey_name)
                if session is not None:
                    sessions.append(session)

        sessions.sort(key=lambda s: (s.folder_key.lower(), s.display_name.lower()))
        return sessions

    def _read_session(self, base_key, subkey_name: str) -> Optional[Session]:
        """Liest eine einzelne Session. Gibt None zurück wenn kein HostName."""
        full_path = REGISTRY_PATH + "\\" + subkey_name
        try:
            with winreg.OpenKey(self.REGISTRY_BASE, full_path) as session_key:
                try:
                    hostname, _ = winreg.QueryValueEx(session_key, "HostName")
                except FileNotFoundError:
                    return None  # Session ohne Hostname überspringen

                if not hostname:
                    return None

                username = ""
                try:
                    username, _ = winreg.QueryValueEx(session_key, "UserName")
                except FileNotFoundError:
                    pass

                port = 22
                try:
                    port, _ = winreg.QueryValueEx(session_key, "PortNumber")
                except FileNotFoundError:
                    pass

        except OSError:
            return None

        folder_path, display_name = parse_session_key(subkey_name)
        return Session(
            key=subkey_name,
            display_name=display_name,
            folder_path=folder_path,
            hostname=hostname,
            username=username,
            port=port,
        )
```

- [ ] **Step 4: Alle Tests ausführen**

```
python -m pytest tests/test_logic.py -v
```
Erwartetes Ergebnis: `10 passed` (der Registry-Mock-Test kann je nach monkeypatch-Verhalten variieren – mindestens 9 passed erwartet, kein FAILED erlaubt)

- [ ] **Step 5: Commit**

```bash
git add ssh_manager.py tests/test_logic.py
git commit -m "feat: add RegistryReader with registry parsing"
```

---

## Task 4: Hauptfenster-Skeleton + Checkbox-Images

**Files:**
- Modify: `ssh_manager.py`

- [ ] **Step 1: `SSHManagerApp` Skeleton am Ende von `ssh_manager.py` einfügen**

```python
# ---------------------------------------------------------------------------
# Checkbox-Images (werden in SessionTree und SSHManagerApp verwendet)
# ---------------------------------------------------------------------------
def _create_checkbox_images(root: tk.Tk) -> tuple[tk.PhotoImage, tk.PhotoImage]:
    """
    Erzeugt zwei 16×16 PhotoImages für checked/unchecked Checkboxen.
    Gibt (img_unchecked, img_checked) zurück.
    """
    size = 16
    border_color = "#808080"
    bg_color = "#ffffff"
    check_color = "#1a7a3a"

    def make(checked: bool) -> tk.PhotoImage:
        img = tk.PhotoImage(width=size, height=size)
        # Alle Pixel mit Hintergrundfarbe füllen
        row_bg = "{" + " ".join([bg_color] * size) + "}"
        for y in range(size):
            img.put(row_bg, to=(0, y, size, y + 1))
        # Rahmen zeichnen
        border_row = "{" + " ".join([border_color] * size) + "}"
        img.put(border_row, to=(0, 0, size, 1))        # oben
        img.put(border_row, to=(0, size - 1, size, size))  # unten
        for y in range(size):
            img.put("{" + border_color + "}", to=(0, y, 1, y + 1))       # links
            img.put("{" + border_color + "}", to=(size - 1, y, size, y + 1))  # rechts
        if checked:
            # Häkchen: kurzer Abstieg (3,9)→(6,12), dann Aufstieg (6,12)→(13,5)
            check_px = "{" + check_color + "}"
            coords_down = [(3, 9), (4, 10), (5, 11), (6, 12)]
            coords_up = [(7, 11), (8, 10), (9, 9), (10, 8), (11, 7), (12, 6), (13, 5)]
            for x, y in coords_down + coords_up:
                if 0 < x < size and 0 < y < size:
                    img.put(check_px, to=(x, y, x + 1, y + 1))
                    # Doppelt breit für bessere Sichtbarkeit
                    if y + 1 < size:
                        img.put(check_px, to=(x, y + 1, x + 1, y + 2))
        return img

    return make(False), make(True)


# ---------------------------------------------------------------------------
# SSHManagerApp
# ---------------------------------------------------------------------------
class SSHManagerApp(tk.Tk):
    """Hauptfenster der SSH-Manager Applikation."""

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.minsize(*WINDOW_MIN_SIZE)
        self.geometry("750x550")

        # Stil
        style = ttk.Style(self)
        style.theme_use("clam")

        # Registry laden
        try:
            reader = RegistryReader()
            self._sessions = reader.load_sessions()
        except OSError as e:
            messagebox.showerror(
                "Registry-Fehler",
                f"WinSCP-Sessions konnten nicht geladen werden:\n{e}\n\n"
                f"Pfad: HKCU\\{REGISTRY_PATH}"
            )
            self._sessions = []

        # Checkbox-Images (nach Tk-Initialisierung erzeugen!)
        self._img_unchecked, self._img_checked = _create_checkbox_images(self)

        self._build_ui()

    def _build_ui(self) -> None:
        """Erstellt alle UI-Elemente."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Toolbar (Zeile 0)
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="Suche:").grid(row=0, column=0, padx=(0, 4))
        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self._search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        ttk.Button(toolbar, text="Alle auswählen",
                   command=self._select_all).grid(row=0, column=2, padx=2)
        ttk.Button(toolbar, text="Alle abwählen",
                   command=self._deselect_all).grid(row=0, column=3, padx=2)

        # SessionTree (Zeile 1)
        self._tree = SessionTree(
            self,
            sessions=self._sessions,
            img_unchecked=self._img_unchecked,
            img_checked=self._img_checked,
            on_selection_changed=self._on_selection_changed,
        )
        self._tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))

        # Verbinden-Button (Zeile 2)
        bottom = ttk.Frame(self, padding=(8, 6))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self._connect_btn = ttk.Button(
            bottom,
            text="Verbinden",
            command=self._on_connect,
            state=tk.DISABLED,
        )
        self._connect_btn.grid(row=0, column=0)

        # Suche verdrahten
        self._search_var.trace_add("write", lambda *_: self._on_search_changed())

    def _on_selection_changed(self, count: int) -> None:
        """Callback vom SessionTree – aktualisiert den Verbinden-Button."""
        if count > 0:
            self._connect_btn.config(
                text=f"Verbinden ({count} ausgewählt)",
                state=tk.NORMAL,
            )
        else:
            self._connect_btn.config(text="Verbinden", state=tk.DISABLED)

    def _on_search_changed(self) -> None:
        self._tree.filter(self._search_var.get())

    def _select_all(self) -> None:
        self._tree.set_all_checked(True)

    def _deselect_all(self) -> None:
        self._tree.set_all_checked(False)

    def _on_connect(self) -> None:
        selected = self._tree.get_selected_sessions()
        if not selected:
            return
        dialog = UserDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return  # Abbrechen gedrückt
        user = dialog.result
        try:
            TerminalLauncher.launch(selected, user)
        except Exception as e:
            messagebox.showerror("Fehler beim Starten", str(e))


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SSHManagerApp()
    app.mainloop()
```

- [ ] **Step 2: App manuell starten – Fenster soll sich öffnen (mit Fehlermeldung weil SessionTree/UserDialog noch fehlen)**

```
python ssh_manager.py
```
Erwartetes Ergebnis: `NameError: name 'SessionTree' is not defined` (korrekt – kommt in Task 5)

- [ ] **Step 3: Commit (Skeleton)**

```bash
git add ssh_manager.py
git commit -m "feat: add SSHManagerApp skeleton and checkbox image creation"
```

---

## Task 5: SessionTree – Treeview mit Checkboxen

**Files:**
- Modify: `ssh_manager.py` (SessionTree Klasse vor SSHManagerApp einfügen)

- [ ] **Step 1: `SessionTree` Klasse VOR `SSHManagerApp` in `ssh_manager.py` einfügen**

```python
# ---------------------------------------------------------------------------
# SessionTree
# ---------------------------------------------------------------------------
class SessionTree(ttk.Frame):
    """
    ttk.Treeview-Wrapper mit Checkbox-Unterstützung.
    Zeigt Sessions gruppiert nach Ordnern an.
    Unterstützt Live-Filter, Rechtsklick-Kontextmenü, Checkbox-Toggle.
    """

    # Tag-Konstanten
    TAG_SESSION = "session"
    TAG_FOLDER = "folder"

    def __init__(
        self,
        parent: tk.Widget,
        sessions: list[Session],
        img_unchecked: tk.PhotoImage,
        img_checked: tk.PhotoImage,
        on_selection_changed,  # Callable[[int], None]
    ):
        super().__init__(parent)
        self._sessions = sessions
        self._img_unchecked = img_unchecked
        self._img_checked = img_checked
        self._on_selection_changed = on_selection_changed

        # item_id → Session (nur für Session-Zeilen, nicht Ordner)
        self._item_to_session: dict[str, Session] = {}
        # item_id → checked state
        self._checked: dict[str, bool] = {}

        self._build()
        self.populate(sessions)

    def _build(self) -> None:
        """Erstellt Treeview + Scrollbar."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._tv = ttk.Treeview(
            self,
            columns=("hostname", "port"),
            selectmode="none",  # Selektion via Checkboxen, nicht Highlight
        )
        self._tv.heading("#0", text="Name", anchor="w")
        self._tv.heading("hostname", text="Hostname", anchor="w")
        self._tv.heading("port", text="Port", anchor="w")
        self._tv.column("#0", width=260, stretch=True)
        self._tv.column("hostname", width=200, stretch=True)
        self._tv.column("port", width=60, stretch=False)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)

        self._tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Events
        self._tv.bind("<ButtonRelease-1>", self._on_left_click)
        self._tv.bind("<ButtonRelease-3>", self._on_right_click)

    def populate(self, sessions: list[Session]) -> None:
        """Füllt den Baum mit Sessions. Löscht vorherige Inhalte."""
        # Zustand merken (welche Ordner waren offen?)
        open_folders: set[str] = set()
        for item_id in self._tv.get_children():
            if self._tv.item(item_id, "open"):
                open_folders.add(self._tv.item(item_id, "text"))

        # Alles löschen
        self._tv.delete(*self._tv.get_children())
        self._item_to_session.clear()
        self._checked.clear()

        # Ordner-Nodes: folder_key → item_id
        folder_items: dict[str, str] = {}

        for session in sessions:
            # Ordner-Hierarchie aufbauen
            parent_id = ""
            for depth, folder_name in enumerate(session.folder_path):
                folder_key = "/".join(session.folder_path[: depth + 1])
                if folder_key not in folder_items:
                    was_open = folder_name in open_folders
                    folder_id = self._tv.insert(
                        parent_id, "end",
                        text=f"  {folder_name}",
                        open=was_open,
                        tags=(self.TAG_FOLDER,),
                    )
                    folder_items[folder_key] = folder_id
                parent_id = folder_items[folder_key]

            # Session-Zeile
            port_str = str(session.port) if session.port != 22 else ""
            item_id = self._tv.insert(
                parent_id, "end",
                image=self._img_unchecked,
                text=f"  {session.display_name}",
                values=(session.hostname, port_str),
                tags=(self.TAG_SESSION,),
            )
            self._item_to_session[item_id] = session
            self._checked[item_id] = False

    def _on_left_click(self, event: tk.Event) -> None:
        """Checkbox togglen wenn auf eine Session-Zeile geklickt wird."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        if self.TAG_SESSION not in self._tv.item(item_id, "tags"):
            return
        self._toggle(item_id)

    def _toggle(self, item_id: str) -> None:
        """Checkbox-Zustand einer Session-Zeile umschalten."""
        new_state = not self._checked.get(item_id, False)
        self._checked[item_id] = new_state
        self._tv.item(
            item_id,
            image=self._img_checked if new_state else self._img_unchecked,
        )
        self._notify_count()

    def _notify_count(self) -> None:
        count = sum(1 for v in self._checked.values() if v)
        self._on_selection_changed(count)

    def get_selected_sessions(self) -> list[Session]:
        """Gibt alle ausgewählten (gecheckte) Sessions zurück."""
        return [
            self._item_to_session[iid]
            for iid, checked in self._checked.items()
            if checked
        ]

    def set_all_checked(self, state: bool) -> None:
        """Alle sichtbaren Session-Zeilen an-/abhaken."""
        for item_id in self._checked:
            self._checked[item_id] = state
            self._tv.item(
                item_id,
                image=self._img_checked if state else self._img_unchecked,
            )
        self._notify_count()

    def _set_folder_checked(self, folder_item_id: str, state: bool) -> None:
        """Alle Session-Zeilen unter einem Ordner an-/abhaken (rekursiv)."""
        for child_id in self._tv.get_children(folder_item_id):
            tags = self._tv.item(child_id, "tags")
            if self.TAG_SESSION in tags:
                self._checked[child_id] = state
                self._tv.item(
                    child_id,
                    image=self._img_checked if state else self._img_unchecked,
                )
            elif self.TAG_FOLDER in tags:
                self._set_folder_checked(child_id, state)
        self._notify_count()

    def _on_right_click(self, event: tk.Event) -> None:
        """Kontextmenü für Ordner-Zeilen anzeigen."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        if self.TAG_FOLDER not in self._tv.item(item_id, "tags"):
            return

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="Alle im Ordner auswählen",
            command=lambda: self._set_folder_checked(item_id, True),
        )
        menu.add_command(
            label="Alle im Ordner abwählen",
            command=lambda: self._set_folder_checked(item_id, False),
        )
        menu.tk_popup(event.x_root, event.y_root)

    def filter(self, query: str) -> None:
        """
        Filtert sichtbare Sessions nach query (case-insensitive, Name + Hostname).
        Bei leerem query werden alle Sessions wieder angezeigt.
        Checkbox-Zustände bleiben beim Filtern erhalten.
        """
        q = query.strip().lower()

        # Checkbox-Zustände vor dem Neuaufbau sichern (item_id ändert sich)
        checked_keys = {
            self._item_to_session[iid].key
            for iid, v in self._checked.items()
            if v
        }

        if q:
            filtered = [
                s for s in self._sessions
                if q in s.display_name.lower() or q in s.hostname.lower()
            ]
        else:
            filtered = self._sessions

        self.populate(filtered)

        # Checkbox-Zustände wiederherstellen
        for item_id, session in self._item_to_session.items():
            if session.key in checked_keys:
                self._checked[item_id] = True
                self._tv.item(item_id, image=self._img_checked)

        self._notify_count()
```

- [ ] **Step 2: App starten und manuell prüfen**

```
python ssh_manager.py
```
Erwartetes Ergebnis: App startet, Fehler `NameError: name 'UserDialog' is not defined` (korrekt – kommt in Task 6)

- [ ] **Step 3: Commit**

```bash
git add ssh_manager.py
git commit -m "feat: add SessionTree with checkbox toggle, filter, right-click menu"
```

---

## Task 6: UserDialog + vollständige App-Verdrahtung

**Files:**
- Modify: `ssh_manager.py` (UserDialog VOR SSHManagerApp einfügen)

- [ ] **Step 1: `UserDialog` Klasse VOR `SSHManagerApp` in `ssh_manager.py` einfügen**

```python
# ---------------------------------------------------------------------------
# UserDialog
# ---------------------------------------------------------------------------
class UserDialog(tk.Toplevel):
    """
    Modaler Dialog zur Benutzernamen-Auswahl.
    Nach Schließen: self.result = gewählter Username (str) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("Benutzername auswählen")
        self.resizable(False, False)
        self.result: Optional[str] = None

        # Modal machen
        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        # Tastaturkürzel
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Quickselect:").grid(
            row=0, column=0, columnspan=len(QUICK_USERS), sticky="w", pady=(0, 4)
        )

        self._user_var = tk.StringVar(value=DEFAULT_USER)

        # Quickselect-Buttons
        for col, username in enumerate(QUICK_USERS):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=1, column=col, padx=2, pady=(0, 8))

        # Freitext-Eingabe
        ttk.Label(frame, text="Benutzername:").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=3, column=0, columnspan=len(QUICK_USERS), sticky="ew", pady=(0, 12))
        entry.select_range(0, "end")
        entry.focus()

        # OK / Abbrechen
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=len(QUICK_USERS))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(
            side="left", padx=4
        )

    def _on_ok(self) -> None:
        user = self._user_var.get().strip()
        if user:
            self.result = user
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")
```

- [ ] **Step 2: App vollständig starten und testen**

```
python ssh_manager.py
```
Erwartetes Ergebnis:
- Fenster öffnet sich mit vollständiger Session-Liste aus der Registry
- Ordner sind klappbar
- Checkbox-Klick togglet den Zustand
- Suchfeld filtert live
- "Alle auswählen / abwählen" Buttons funktionieren
- Rechtsklick auf Ordner zeigt Kontextmenü
- "Verbinden"-Button aktiviert sich bei Auswahl und zeigt Anzahl
- Klick auf "Verbinden" → UserDialog öffnet sich
- Quickselect-Buttons füllen das Textfeld
- Enter / OK → Dialog schließt sich, Verbindungen öffnen sich in Windows Terminal

- [ ] **Step 3: Alle Tests ausführen**

```
python -m pytest tests/test_logic.py -v
```
Erwartetes Ergebnis: alle Tests bestehen (mindestens 9 passed)

- [ ] **Step 4: Commit**

```bash
git add ssh_manager.py
git commit -m "feat: add UserDialog and complete app wiring"
```

---

## Task 7: Manuelle End-to-End-Verifikation

**Files:** keine Änderungen

- [ ] **Alle Verifikationsschritte aus der Spec durchgehen:**

1. `python ssh_manager.py` → Fenster öffnet sich mit der korrekten WinSCP-Session-Liste
2. Ordner ein-/ausklappen (Klick auf Pfeil) → funktioniert
3. Suchfeld: `"plex"` eingeben → nur Plex-Session sichtbar; Suchfeld leeren → alle wieder da
4. Rechtsklick auf Ordner `Extern` → "Alle im Ordner auswählen" → alle Sessions im Ordner gecheckt
5. `[Alle auswählen]` → alles gecheckt; `[Alle abwählen]` → alles abgehakt
6. 2 Sessions auswählen → Button zeigt `Verbinden (2 ausgewählt)`
7. Auf `Verbinden (2 ausgewählt)` klicken → UserDialog öffnet sich, `tool-admin` vorausgefüllt
8. `[dev-sys]` Button klicken → Textfeld ändert sich auf `dev-sys`
9. `OK` klicken → Dialog schließt sich, Windows Terminal öffnet sich mit 2 Git-Bash-Tabs mit SSH
10. SSH-Verbindungen sind in beiden Tabs aktiv (oder schlagen fehl falls Server nicht erreichbar – korrekt)
11. SSH-Manager-Hauptfenster ist noch offen ✓
12. Session mit Port 2222 auswählen → im wt.exe-Befehl erscheint `-p 2222` (Prüfung per Debugging-Print falls nötig)

- [ ] **Abbrechen testen:**

UserDialog öffnen → `[Abbrechen]` klicken → keine Verbindungen werden geöffnet, Hauptfenster bleibt offen ✓

- [ ] **Final Commit**

```bash
git add ssh_manager.py tests/test_logic.py
git commit -m "feat: complete SSH-Manager v1.0"
```

---

## Spec-Abdeckung

| Anforderung | Task |
|---|---|
| WinSCP Registry lesen | Task 3 |
| Baum mit Ordnerstruktur | Task 5 |
| Hostname anzeigen | Task 5 |
| Checkboxen für Mehrfachauswahl | Task 5 |
| Vollständig verschachtelte Ordner | Task 5 |
| Suchfeld (live) | Task 5 + Task 4 |
| Alle auswählen / abwählen | Task 4 + Task 5 |
| Rechtsklick auf Ordner | Task 5 |
| UserDialog mit Quickselect | Task 6 |
| Default-User: tool-admin | Task 6 |
| wt.exe mit mehreren Tabs | Task 2 |
| Port ≠ 22 → `-p PORT` | Task 2 |
| Hauptfenster bleibt offen | Task 4 |
| Default%20Settings überspringen | Task 3 |
| Fehlermeldung bei Registry-Fehler | Task 4 |
| Fehlermeldung bei wt.exe-Fehler | Task 4 |
| Enter/Escape im Dialog | Task 6 |
| Dialog modal + zentriert | Task 6 |
